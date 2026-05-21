"""Flask web dashboard for real-time portfolio monitoring and auto-trading."""

from flask import Flask, render_template, jsonify, request
import json
from datetime import datetime
from portfolio import Portfolio
from strategy import get_strategy_engine
from data_fetcher import get_data_fetcher
from news_fetcher import get_news_fetcher
from config import (STOCKS, TRADING_MODE, RISK_PER_TRADE, CRYPTO_PAIRS, MAX_POSITIONS,
                    ALPACA_ENABLED, ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER)
from utils import format_currency, format_percent
import threading
import time
import os

# Alpaca Broker (optional)
alpaca_broker = None
if ALPACA_ENABLED:
    try:
        from alpaca_broker import AlpacaBroker
        alpaca_broker = AlpacaBroker(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=ALPACA_PAPER)
        if not alpaca_broker.connected:
            print("[WARN] Alpaca connection failed, using local portfolio")
            alpaca_broker = None
    except Exception as e:
        print(f"[WARN] Alpaca could not be loaded: {e}")
        alpaca_broker = None

# Auto-trade state (file-based for cross-process compat with Flask debug reloader)
AUTO_TRADE_FILE = os.path.join(os.path.dirname(__file__), '.auto_trade_state')
auto_trade_thread = None
_thread_started = False
_thread_lock = threading.Lock()

# Wash-trade cooldown: prevent re-opening immediately after closing
_wash_trade_cooldown = {}
WASH_TRADE_COOLDOWN_SECONDS = 120

# Cached signals (avoids duplicate LLM calls from dashboard API)
_cached_signals = {}
_cached_signals_lock = threading.Lock()

_portfolio_file_lock = threading.Lock()

_last_equity_record_time = 0
EQUITY_RECORD_INTERVAL = 300

app = Flask(__name__, template_folder='templates', static_folder='static')

def is_auto_trade_on():
    return os.path.exists(AUTO_TRADE_FILE)

def set_auto_trade(enabled):
    """Set auto-trade status (file-based)."""
    if enabled:
        with open(AUTO_TRADE_FILE, 'w') as f:
            f.write('1')
    else:
        if os.path.exists(AUTO_TRADE_FILE):
            os.remove(AUTO_TRADE_FILE)

def get_portfolio():
    """Load the latest portfolio from disk (thread-safe)."""
    with _portfolio_file_lock:
        p = Portfolio()
        p.load_from_file()
        return p

def save_portfolio_safe(portfolio):
    """Save portfolio to disk (thread-safe)."""
    with _portfolio_file_lock:
        portfolio.save_to_file()

def sync_portfolio_with_alpaca(portfolio):
    """Sync local portfolio balance with Alpaca."""
    if not alpaca_broker or not alpaca_broker.connected:
        return portfolio

    try:
        acct = alpaca_broker.get_account_info()
        if acct:
            # Always adopt Alpaca cash as the source of truth
            portfolio.current_balance = acct.get('cash', portfolio.current_balance)
            
            # Check if Alpaca positions were closed that we still have open locally
            alpaca_positions = alpaca_broker.get_positions()
            local_symbols = list(portfolio.positions.keys())
            for sym in local_symbols:
                if sym not in alpaca_positions:
                    # Position was closed at Alpaca (e.g. by TP/SL)
                    # Must close locally too
                    print(f"[SYNC] {sym} closed at Alpaca, closing locally...")
                    trade = portfolio.positions[sym]
                    trade.close_trade(trade.current_price if trade.current_price else trade.entry_price)
                    portfolio.closed_trades.append(trade)
                    del portfolio.positions[sym]
                    save_portfolio_safe(portfolio)

    except Exception as e:
        print(f"[WARN] Alpaca sync failed: {e}")

    return portfolio

def alpaca_startup_sync():
    """One-time startup sync: import Alpaca positions and synchronize balance."""
    if not alpaca_broker or not alpaca_broker.connected:
        return

    print("[SYNC] Starting Alpaca synchronization...")

    # 1. Check what Alpaca has
    positions = alpaca_broker.get_positions()
    acct = alpaca_broker.get_account_info()

    if not acct:
        print("[SYNC] Cannot load account info, skipping sync")
        return

    # 2. Load local portfolio
    portfolio = get_portfolio()

    # 3. Import Alpaca positions that are not tracked locally
    imported = 0
    from portfolio import Trade
    for sym, pos_data in positions.items():
        if sym not in portfolio.positions:
            print(f"[SYNC] Importing Alpaca position: {sym} ({pos_data['qty']} shares)")
            qty = pos_data['qty']
            avg_price = pos_data['avg_entry_price']
            
            # Create manually to bypass capital check in open_trade()
            portfolio.trade_counter += 1
            trade_id = f"TRD_{portfolio.trade_counter:05d}"
            trade = Trade(
                trade_id=trade_id,
                asset=sym,
                signal_type="BUY",
                entry_price=avg_price,
                stop_loss=avg_price * 0.95,  # Dummy SL: 5%
                take_profit=avg_price * 1.10, # Dummy TP: 10%
                position_size=qty
            )
            portfolio.positions[sym] = trade
            imported += 1

    # 4. Close local positions that are missing at Alpaca
    closed = 0
    local_symbols = list(portfolio.positions.keys())
    for sym in local_symbols:
        if sym not in positions:
            print(f"[SYNC] Local position {sym} not found at Alpaca, closing...")
            trade = portfolio.positions[sym]
            trade.close_trade(trade.current_price if trade.current_price else trade.entry_price)
            portfolio.closed_trades.append(trade)
            del portfolio.positions[sym]
            closed += 1

    # 5. Update cash and save
    equity = acct.get('equity', portfolio.initial_balance)
    cash = acct.get('cash', portfolio.current_balance)
    
    portfolio.current_balance = cash
    
    # If there are no trades in history, set initial balance to current equity
    if len(portfolio.closed_trades) == 0 and len(portfolio.positions) == 0:
        portfolio.initial_balance = equity
        
    portfolio.save_to_file()
    
    print(f"[SYNC] Sync complete! {imported} imported, {closed} closed.")
    print(f"[SYNC] Local balance: ${cash:,.2f}, Alpaca equity: ${equity:,.2f}")

def is_in_wash_cooldown(symbol):
    """Check if a symbol is in wash-trade cooldown"""
    if symbol in _wash_trade_cooldown:
        elapsed = time.time() - _wash_trade_cooldown[symbol]
        if elapsed < WASH_TRADE_COOLDOWN_SECONDS:
            remaining = int(WASH_TRADE_COOLDOWN_SECONDS - elapsed)
            print(f"[COOLDOWN] {symbol}: {remaining}s wash-trade cooldown remaining")
            return True
        else:
            del _wash_trade_cooldown[symbol]
    return False

def background_trading_loop():
    """Background loop that monitors the market and manages trades."""
    global _last_equity_record_time
    print("[BOT] Auto-trade background worker started...")
    
    fetcher = get_data_fetcher()
    strategy = get_strategy_engine()
    
    while True:
        try:
            # 1. Update portfolio & check open positions
            portfolio = get_portfolio()
            
            # Sync with Alpaca balance
            portfolio = sync_portfolio_with_alpaca(portfolio)
            
            current_prices = {}
            for asset in list(portfolio.positions.keys()):
                price = fetcher.get_current_price(asset)
                if price:
                    current_prices[asset] = price
            
            if current_prices:
                closed = portfolio.update_open_positions(current_prices)
                if closed:
                    save_portfolio_safe(portfolio)
                    # If Alpaca is active, close position there too
                    if alpaca_broker and alpaca_broker.connected:
                        for trade in closed:
                            side = "sell" if trade.signal_type == "BUY" else "buy"
                            symbol = trade.asset
                            print(f"[ALPACA] Closing position: {side} {symbol}")

                            # Set wash-trade cooldown
                            _wash_trade_cooldown[symbol] = time.time()

                            # Check if Alpaca actually holds the position
                            try:
                                alpaca_positions = alpaca_broker.get_positions()
                                if symbol in alpaca_positions:
                                    alpaca_broker.close_position(symbol)
                                else:
                                    print(f"[ALPACA] {symbol} not found at Alpaca, skipping close order")
                            except Exception as e:
                                print(f"[ALPACA] Error closing {symbol}: {e}")
            
            # Periodic equity history recording (even without trades)
            now = time.time()
            if now - _last_equity_record_time >= EQUITY_RECORD_INTERVAL:
                portfolio._record_equity()
                save_portfolio_safe(portfolio)
                _last_equity_record_time = now
            
            # 2. If auto-trade is active, generate signals
            if is_auto_trade_on():
                assets = STOCKS if TRADING_MODE in ["STOCKS", "HYBRID"] else CRYPTO_PAIRS
                asset_type = "STOCK" if TRADING_MODE in ["STOCKS", "HYBRID"] else "CRYPTO"
                
                print(f"[AUTO-TRADE] Scanning {len(assets)} assets... (Balance: ${portfolio.current_balance:.2f}, Positions: {len(portfolio.positions)}/{MAX_POSITIONS})")
                
                for asset in assets:
                    if asset in portfolio.positions:
                        continue
                    
                    # Wash-trade cooldown check
                    if is_in_wash_cooldown(asset):
                        continue
                        
                    signal = strategy.analyze_asset(asset, asset_type=asset_type, timeframe="1h")
                    raw_signal = strategy.last_raw_signals.get(asset) if hasattr(strategy, 'last_raw_signals') else signal
                    
                    # Signal cachen for Dashboard-API
                    with _cached_signals_lock:
                        _cached_signals[asset] = {
                            'signal': raw_signal,
                            'timestamp': time.time()
                        }
                    
                    if not signal:
                        print(f"[AUTO-TRADE] {asset}: No signal (confidence too low)")
                        continue
                    
                    if signal.get('signal') not in ['BUY', 'SELL']:
                        print(f"[AUTO-TRADE] {asset}: Signal is {signal.get('signal')} (no trade)")
                        continue
                    
                    # RISK_PER_TRADE is already in % (e.g. 2.0 = 2%)
                    risk_pct = RISK_PER_TRADE
                    # If RISK_PER_TRADE is given as decimal (e.g. 0.02), convert
                    if risk_pct < 1:
                        risk_pct = risk_pct * 100  # 0.02 -> 2.0
                    
                    entry_price = signal.get('entry_price', 0)
                    stop_loss = signal.get('stop_loss', 0)
                    
                    if entry_price <= 0 or stop_loss <= 0:
                        print(f"[AUTO-TRADE] {asset}: Invalid entry/SL price")
                        continue
                    
                    position_size = strategy.calculate_position_size(
                        portfolio.current_balance, 
                        risk_pct,
                        entry_price,
                        stop_loss
                    )
                    
                    print(f"[AUTO-TRADE] {asset}: Signal={signal.get('signal')} Conf={signal.get('confidence'):.2f} Entry=${entry_price:.2f} SL=${stop_loss:.2f} Size={position_size:.4f}")
                    
                    if position_size <= 0:
                        print(f"[AUTO-TRADE] {asset}: Position size is 0 (risk too small)")
                        continue
                    
                    # For stocks: minimum 1 share, max 25% of portfolio
                    if asset_type == "STOCK":
                        max_position_value = portfolio.current_balance * 0.25
                        max_shares = int(max_position_value / entry_price)
                        position_size = max(1, min(int(position_size), max_shares))
                        print(f"[AUTO-TRADE] {asset}: Shares after cap: {position_size} (Max: {max_shares})")
                    
                    can_open = portfolio.can_open_position(asset, position_size, entry_price)
                    print(f"[AUTO-TRADE] {asset}: can_open={can_open} (required capital: ${position_size * entry_price:.2f})")
                    
                    if can_open:
                        # Reload portfolio fresh (guard against race conditions)
                        portfolio = get_portfolio()
                        if asset in portfolio.positions:
                            print(f"[AUTO-TRADE] {asset}: Already opened (race condition avoided)")
                            continue
                        
                        # 1. Update local portfolio
                        portfolio.open_trade(
                            asset, 
                            signal.get('signal'),
                            entry_price,
                            stop_loss,
                            signal.get('take_profit'),
                            position_size
                        )
                        save_portfolio_safe(portfolio)
                        
                        # 2. Send Alpaca order (if active)
                        if alpaca_broker and alpaca_broker.connected:
                            side = "buy" if signal.get('signal') == 'BUY' else "sell"
                            qty = max(1, int(position_size))
                            print(f"[ALPACA] Submitting order: {side} {qty}x {asset} @ market")
                            result = alpaca_broker.submit_order(
                                symbol=asset,
                                qty=qty,
                                side=side,
                                order_type='market'
                            )
                            if result:
                                print(f"[ALPACA] Order successful: {result.get('order_id', 'N/A')}")
                            else:
                                print(f"[ALPACA] Order failed for {asset}!")
                        
                        print(f"[AUTO-TRADE] === TRADE OPENED: {signal.get('signal')} {position_size} {asset} @ ${entry_price:.2f} ===")
                        time.sleep(2)  # Pause zwischen Trades
                    else:
                        print(f"[AUTO-TRADE] {asset}: Trade could not be opened (capital/limit)")
                            
        except Exception as e:
            print(f"[AUTO-TRADE ERROR] {e}")
            import traceback
            traceback.print_exc()
            
        # Wait before next scan cycle
        wait_time = 60 if is_auto_trade_on() else 120
        if is_auto_trade_on():
            print(f"[AUTO-TRADE] Next scan in {wait_time}s... (Positions: {len(portfolio.positions)})")
        time.sleep(wait_time)

@app.route('/')
def dashboard():
    """Serve the main dashboard page."""
    return render_template('index.html')

@app.route('/api/portfolio')
def get_portfolio_data():
    """API: Portfolio data — uses Alpaca when available."""
    portfolio = get_portfolio()
    
    # If Alpaca is active, fetch real account data
    alpaca_info = None
    if alpaca_broker and alpaca_broker.connected:
        alpaca_info = alpaca_broker.get_account_info()
    
    # Prepare current prices
    fetcher = get_data_fetcher()
    current_prices = {}
    for asset in portfolio.positions.keys():
        price = fetcher.get_current_price(asset)
        if price:
           current_prices[asset] = price
           
    if current_prices:
        portfolio.update_open_positions(current_prices)

    stats = portfolio.get_portfolio_stats()

    positions = []
    for asset, trade in portfolio.positions.items():
        upnl, upnl_pct = trade.get_unrealized_pnl()
        positions.append({
            'asset': asset,
            'type': trade.signal_type,
            'qty': trade.position_size,
            'entry_price': trade.entry_price,
            'current_price': trade.current_price,
            'stop_loss': trade.stop_loss,
            'take_profit': trade.take_profit,
            'unrealized_pnl': upnl,
            'unrealized_pnl_percent': upnl_pct,
            'entry_time': trade.entry_time.isoformat() if hasattr(trade, 'entry_time') and trade.entry_time else None
        })
    
    # If Alpaca is connected, incorporate Alpaca positions
    if alpaca_broker and alpaca_broker.connected and alpaca_info:
        # Alpaca hat das echte Equity
        alpaca_equity = alpaca_info.get('equity', stats['total_equity'])
        alpaca_cash = alpaca_info.get('cash', portfolio.current_balance)
    else:
        alpaca_equity = stats['total_equity']
        alpaca_cash = portfolio.current_balance
        
    # Extract equity history for the chart
    equity_history = portfolio.equity_history[-500:] if portfolio.equity_history else []

    return jsonify({
        'balance': alpaca_cash,
        'initial_balance': portfolio.initial_balance,
        'total_equity': alpaca_equity,
        'total_pnl': stats['total_pnl'],
        'unrealized_pnl': stats['unrealized_pnl'],
        'return_percent': stats['return_percent'],
        'positions': positions,
        'trades_count': stats['total_trades'],
        'win_rate': stats['win_rate'],
        'profit_factor': stats['profit_factor'],
        'max_drawdown': stats['max_drawdown_pct'],
        'sharpe_ratio': stats['sharpe_ratio'],
        'equity_history': equity_history,
        'alpaca_connected': alpaca_broker is not None and alpaca_broker.connected,
    })

@app.route('/api/trades')
def get_trades():
    """API: Recent trade history."""
    portfolio = get_portfolio()
    trades = []
    for trade in portfolio.closed_trades[-50:]:  # Last 50 trades
        trades.append({
            'id': trade.id,
            'asset': trade.asset,
            'type': trade.signal_type,
            'entry_price': trade.entry_price,
            'exit_price': trade.exit_price,
            'pnl': trade.pnl,
            'pnl_percent': trade.pnl_percent,
            'entry_time': trade.entry_time.isoformat(),
            'exit_time': trade.exit_time.isoformat() if trade.exit_time else None,
        })
    return jsonify(list(reversed(trades)))

@app.route('/api/signals')
def get_signals():
    """API: Live trading signals — uses cached signals from the background thread."""
    # Use cached signals instead of new AI calls
    signals = []
    
    assets = STOCKS if TRADING_MODE in ["STOCKS", "HYBRID"] else CRYPTO_PAIRS
    with _cached_signals_lock:
        for asset in assets:
            cached = _cached_signals.get(asset)
            if cached and cached['signal'] and (time.time() - cached['timestamp']) < 900:
                signal = cached['signal']
                signals.append({
                    'asset': asset,
                    'signal': signal.get('signal'),
                    'confidence': signal.get('confidence'),
                    'entry_price': signal.get('entry_price'),
                    'stop_loss': signal.get('stop_loss'),
                    'take_profit': signal.get('take_profit'),
                    'risk_reward': signal.get('risk_reward_ratio'),
                    'reason': signal.get('reason', ''),
                })

    return jsonify(signals)

@app.route('/api/signals/detailed')
def get_signals_detailed():
    """API: Detailed signals with news context — uses cached signals."""
    news_fetcher = get_news_fetcher()
    signals = []

    assets = STOCKS if TRADING_MODE in ["STOCKS", "HYBRID"] else CRYPTO_PAIRS
    asset_type = "STOCK" if TRADING_MODE in ["STOCKS", "HYBRID"] else "CRYPTO"

    for asset in assets:
        # Use cached signals instead of new AI calls
        signal = None
        with _cached_signals_lock:
            cached = _cached_signals.get(asset)
            if cached and (time.time() - cached['timestamp']) < 900:
                signal = cached['signal']
        
        # Fetch news for each asset
        news = []
        sentiment = None
        current_price = 0
        if asset_type == "STOCK":
            try:
                news = news_fetcher.get_company_news(asset, days_back=3, max_articles=5)
                sentiment = news_fetcher.get_market_sentiment(asset)
            except Exception:
                pass
            # Fetch current price even when there is no signal
            try:
                fetcher = get_data_fetcher()
                current_price = fetcher.get_current_price(asset) or 0
            except Exception:
                pass

        portfolio = get_portfolio()
        
        # Determine the correct status text
        if signal:
            reason_text = signal.get('reason', 'Signal generated')
        elif asset in portfolio.positions:
            reason_text = 'Asset is currently held in portfolio (Analysis paused)'
        else:
            reason_text = 'No strong signal detected (Confidence too low or HOLD)'

        entry = {
            'asset': asset,
            'signal': signal.get('signal') if signal else 'HOLD',
            'confidence': signal.get('confidence', 0) if signal else 0,
            'entry_price': signal.get('entry_price', current_price) if signal else current_price,
            'stop_loss': signal.get('stop_loss', 0) if signal else 0,
            'take_profit': signal.get('take_profit', 0) if signal else 0,
            'risk_reward': signal.get('risk_reward_ratio', 0) if signal else 0,
            'reason': reason_text,
            'news': news,
            'sentiment': sentiment,
        }
        signals.append(entry)

    return jsonify(signals)

@app.route('/api/news/<symbol>')
def get_news(symbol):
    """API: Current news for a specific symbol."""
    news_fetcher = get_news_fetcher()
    
    days = request.args.get('days', 3, type=int)
    limit = request.args.get('limit', 10, type=int)
    
    news = news_fetcher.get_company_news(symbol, days_back=days, max_articles=limit)
    sentiment = news_fetcher.get_market_sentiment(symbol)
    
    return jsonify({
        'symbol': symbol,
        'news': news,
        'sentiment': sentiment,
        'count': len(news),
    })

@app.route('/api/market-info')
def get_market_info():
    """API: Market information."""
    fetcher = get_data_fetcher()
    market_data = []

    for symbol in STOCKS[:8]:  # Top 8 assets in the dashboard
        info = fetcher.get_stock_info(symbol)
        if info and info.get('price'):
            market_data.append({
                'symbol': symbol,
                'name': info.get('name', symbol),
                'price': float(info.get('price', 0)),
                'change': float(info.get('change', 0) or 0),
            })

    return jsonify(market_data)

@app.route('/api/health')
def health_check():
    """API: Health Check"""
    portfolio = get_portfolio()
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'portfolio_value': portfolio.current_balance,
        'auto_trade': is_auto_trade_on(),
        'alpaca_connected': alpaca_broker is not None and alpaca_broker.connected,
    })

@app.route('/api/autotrade/status')
def autotrade_status():
    return jsonify({'enabled': is_auto_trade_on()})

@app.route('/api/autotrade/toggle', methods=['POST'])
def autotrade_toggle():
    currently_on = is_auto_trade_on()
    set_auto_trade(not currently_on)
    enabled = is_auto_trade_on()
    status_msg = "ON" if enabled else "OFF"
    print(f"[AUTO-TRADE] Status changed: {status_msg}")
    return jsonify({
        'status': 'success',
        'enabled': enabled,
        'message': f"Auto-Trade is now {status_msg}"
    })

@app.route('/api/alpaca/info')
def alpaca_info():
    """API: Alpaca Account Info"""
    if not alpaca_broker or not alpaca_broker.connected:
        return jsonify({'connected': False, 'message': 'Alpaca not connected'})
    
    info = alpaca_broker.get_account_info()
    positions = alpaca_broker.get_positions()
    
    return jsonify({
        'connected': True,
        'account': info,
        'positions': positions,
    })

@app.route('/api/portfolio/reset', methods=['POST'])
def reset_portfolio():
    """API: Reset portfolio and sync with Alpaca"""
    try:
        if alpaca_broker and alpaca_broker.connected:
            acct = alpaca_broker.get_account_info()
            initial = float(acct.get('equity', 100000))
            cash = float(acct.get('cash', 100000))
        else:
            initial = 100000
            cash = 100000

        portfolio = Portfolio(initial_balance=initial)
        portfolio.current_balance = cash
        save_portfolio_safe(portfolio)

        return jsonify({
            'status': 'success',
            'initial_balance': initial,
            'cash': cash,
            'message': f'Portfolio reset to ${initial:,.2f}'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    # One-time startup sync with Alpaca
    alpaca_startup_sync()

    # Start background trading loop — guarded against double-start
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        with _thread_lock:
            if not _thread_started:
                _thread_started = True
                auto_trade_thread = threading.Thread(target=background_trading_loop, daemon=True)
                auto_trade_thread.start()
    
    print("[START] Dashboard running on http://localhost:5000")
    print(f"[CONFIG] Max positions: {MAX_POSITIONS}, Assets: {len(STOCKS)}")
    if alpaca_broker and alpaca_broker.connected:
        print("[ALPACA] Paper trading connected — trades will be sent to Alpaca!")
        print("[ALPACA] Data fetched from Alpaca (Yahoo as fallback)")
    else:
        print("[INFO] Alpaca not connected — using local paper trading + Yahoo data")
    app.run(debug=True, port=5000, use_reloader=False)
