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
        print(f"[WARN] Alpaca konnte nicht loaded werden: {e}")
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
    """Setze Auto-Trade Status (file-based)"""
    if enabled:
        with open(AUTO_TRADE_FILE, 'w') as f:
            f.write('1')
    else:
        if os.path.exists(AUTO_TRADE_FILE):
            os.remove(AUTO_TRADE_FILE)

def get_portfolio():
    """Loading immer das aktuellste Portfolio (thread-safe)"""
    with _portfolio_file_lock:
        p = Portfolio()
        p.load_from_file()
        return p

def save_portfolio_safe(portfolio):
    """Speichere Portfolio thread-safe"""
    with _portfolio_file_lock:
        portfolio.save_to_file()

def sync_portfolio_with_alpaca(portfolio):
    """Synchronisiere lokales Portfolio-Balance mit Alpaca"""
    if not alpaca_broker or not alpaca_broker.connected:
        return portfolio

    try:
        acct = alpaca_broker.get_account_info()
        if acct:
            # Uebernehme immer Alpaca Cash, das ist die absolute Wahrheit
            portfolio.current_balance = acct.get('cash', portfolio.current_balance)
            
            # Check if Alpaca positions were closed that we still have open locally
            alpaca_positions = alpaca_broker.get_positions()
            local_symbols = list(portfolio.positions.keys())
            for sym in local_symbols:
                if sym not in alpaca_positions:
                    # Position wurde bei Alpaca (z.B. durch TP/SL) geschlossen
                    # Must close locally too
                    print(f"[SYNC] {sym} closed at Alpaca, closing locally...")
                    trade = portfolio.positions[sym]
                    trade.close_trade(trade.current_price if trade.current_price else trade.entry_price)
                    portfolio.closed_trades.append(trade)
                    del portfolio.positions[sym]
                    save_portfolio_safe(portfolio)

    except Exception as e:
        print(f"[WARN] Alpaca Sync fehlgeschlagen: {e}")

    return portfolio

def alpaca_startup_sync():
    """Einmaliger Startup-Sync: Importiere Alpaca-Positionen und synchronisiere Balance"""
    if not alpaca_broker or not alpaca_broker.connected:
        return

    print("[SYNC] Starte Alpaca-Synchronisation...")

    # 1. Schaue was Alpaca hat
    positions = alpaca_broker.get_positions()
    acct = alpaca_broker.get_account_info()

    if not acct:
        print("[SYNC] Kann Account-Info nicht laden, ueberspringe Sync")
        return

    # 2. Loading lokales Portfolio
    portfolio = get_portfolio()

    # 3. Importiere Alpaca-Positionen, die nicht lokal sind
    imported = 0
    from portfolio import Trade
    for sym, pos_data in positions.items():
        if sym not in portfolio.positions:
            print(f"[SYNC] Importiere Alpaca-Position: {sym} ({pos_data['qty']} shares)")
            qty = pos_data['qty']
            avg_price = pos_data['avg_entry_price']
            
            # Manuell erstellen um Capital-Check in open_trade() zu umgehen
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

    # 5. Aktualisiere Cash und speichere
    equity = acct.get('equity', portfolio.initial_balance)
    cash = acct.get('cash', portfolio.current_balance)
    
    portfolio.current_balance = cash
    
    # Wenn wir gar keine Trades in der Historie haben, setzen wir die Initial Balance
    if len(portfolio.closed_trades) == 0 and len(portfolio.positions) == 0:
        portfolio.initial_balance = equity
        
    portfolio.save_to_file()
    
    print(f"[SYNC] Sync abgeschlossen! {imported} importiert, {closed} geschlossen.")
    print(f"[SYNC] Lokale Balance: ${cash:,.2f}, Alpaca Equity: ${equity:,.2f}")

def is_in_wash_cooldown(symbol):
    """Check if a symbol is in wash-trade cooldown"""
    if symbol in _wash_trade_cooldown:
        elapsed = time.time() - _wash_trade_cooldown[symbol]
        if elapsed < WASH_TRADE_COOLDOWN_SECONDS:
            remaining = int(WASH_TRADE_COOLDOWN_SECONDS - elapsed)
            print(f"[COOLDOWN] {symbol}: Noch {remaining}s Wash-Trade Cooldown")
            return True
        else:
            del _wash_trade_cooldown[symbol]
    return False

def background_trading_loop():
    """Background Loop, der Markt checkt und Trades managt"""
    global _last_equity_record_time
    print("[BOT] Auto-Trade Background-Worker gestartet...")
    
    fetcher = get_data_fetcher()
    strategy = get_strategy_engine()
    
    while True:
        try:
            # 1. Update Portfolio & check offene Positionen
            portfolio = get_portfolio()
            
            # Sync mit Alpaca Balance
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
                    # Wenn Alpaca aktiv, schliesse auch dort
                    if alpaca_broker and alpaca_broker.connected:
                        for trade in closed:
                            side = "sell" if trade.signal_type == "BUY" else "buy"
                            symbol = trade.asset
                            print(f"[ALPACA] Schliesse Position: {side} {symbol}")

                            # Wash-Trade Cooldown setzen
                            _wash_trade_cooldown[symbol] = time.time()

                            # Check if Alpaca actually holds the position
                            try:
                                alpaca_positions = alpaca_broker.get_positions()
                                if symbol in alpaca_positions:
                                    alpaca_broker.close_position(symbol)
                                else:
                                    print(f"[ALPACA] {symbol} not found at Alpaca, skipping close order")
                            except Exception as e:
                                print(f"[ALPACA] Fehler beim Schliessen von {symbol}: {e}")
            
            # Periodische Equity-History Aufzeichnung (auch ohne Trades)
            now = time.time()
            if now - _last_equity_record_time >= EQUITY_RECORD_INTERVAL:
                portfolio._record_equity()
                save_portfolio_safe(portfolio)
                _last_equity_record_time = now
            
            # 2. Wenn Auto-Trade aktiv, generiere Signale
            if is_auto_trade_on():
                assets = STOCKS if TRADING_MODE in ["STOCKS", "HYBRID"] else CRYPTO_PAIRS
                asset_type = "STOCK" if TRADING_MODE in ["STOCKS", "HYBRID"] else "CRYPTO"
                
                print(f"[AUTO-TRADE] Scanne {len(assets)} Assets... (Balance: ${portfolio.current_balance:.2f}, Positionen: {len(portfolio.positions)}/{MAX_POSITIONS})")
                
                for asset in assets:
                    if asset in portfolio.positions:
                        continue
                    
                    # Wash-trade cooldown check
                    if is_in_wash_cooldown(asset):
                        continue
                        
                    print(f"[AUTO-TRADE] Analysiere {asset}...")
                    signal = strategy.analyze_asset(asset, asset_type=asset_type, timeframe="1h")
                    
                    # Signal cachen for Dashboard-API
                    with _cached_signals_lock:
                        _cached_signals[asset] = {
                            'signal': signal,
                            'timestamp': time.time()
                        }
                    
                    if not signal:
                        print(f"[AUTO-TRADE] {asset}: Kein Signal (Confidence zu niedrig)")
                        continue
                    
                    if signal.get('signal') not in ['BUY', 'SELL']:
                        print(f"[AUTO-TRADE] {asset}: Signal ist {signal.get('signal')} (kein Trade)")
                        continue
                    
                    # RISK_PER_TRADE ist schon in % (z.B. 2.0 = 2%)
                    risk_pct = RISK_PER_TRADE
                    # Wenn RISK_PER_TRADE als Dezimalwert angegeben (z.B. 0.02), konvertiere
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
                        print(f"[AUTO-TRADE] {asset}: Position Size ist 0 (Risk zu klein)")
                        continue
                    
                    # Fuer Aktien: mindestens 1 Share, max 25% des Portfolios
                    if asset_type == "STOCK":
                        max_position_value = portfolio.current_balance * 0.25
                        max_shares = int(max_position_value / entry_price)
                        position_size = max(1, min(int(position_size), max_shares))
                        print(f"[AUTO-TRADE] {asset}: Shares nach Cap: {position_size} (Max: {max_shares})")
                    
                    can_open = portfolio.can_open_position(asset, position_size, entry_price)
                    print(f"[AUTO-TRADE] {asset}: can_open={can_open} (benoetigtes Kapital: ${position_size * entry_price:.2f})")
                    
                    if can_open:
                        # Nochmal Portfolio frisch laden (gegen Race Conditions)
                        portfolio = get_portfolio()
                        if asset in portfolio.positions:
                            print(f"[AUTO-TRADE] {asset}: Already opened (race condition avoided)")
                            continue
                        
                        # 1. Lokales Portfolio updaten
                        portfolio.open_trade(
                            asset, 
                            signal.get('signal'),
                            entry_price,
                            stop_loss,
                            signal.get('take_profit'),
                            position_size
                        )
                        save_portfolio_safe(portfolio)
                        
                        # 2. Alpaca Order senden (wenn aktiv)
                        if alpaca_broker and alpaca_broker.connected:
                            side = "buy" if signal.get('signal') == 'BUY' else "sell"
                            qty = max(1, int(position_size))
                            print(f"[ALPACA] Sende Order: {side} {qty}x {asset} @ market")
                            result = alpaca_broker.submit_order(
                                symbol=asset,
                                qty=qty,
                                side=side,
                                order_type='market'
                            )
                            if result:
                                print(f"[ALPACA] Order erfolgreich: {result.get('order_id', 'N/A')}")
                            else:
                                print(f"[ALPACA] Order fehlgeschlagen fuer {asset}!")
                        
                        print(f"[AUTO-TRADE] === TRADE EROEFFNET: {signal.get('signal')} {position_size} {asset} @ ${entry_price:.2f} ===")
                        time.sleep(2)  # Pause zwischen Trades
                    else:
                        print(f"[AUTO-TRADE] {asset}: Trade konnte nicht eroeffnet werden (Kapital/Limit)")
                            
        except Exception as e:
            print(f"[AUTO-TRADE ERROR] {e}")
            import traceback
            traceback.print_exc()
            
        # Warte vor dem naechsten Durchlauf
        wait_time = 60 if is_auto_trade_on() else 120
        if is_auto_trade_on():
            print(f"[AUTO-TRADE] Naechster Scan in {wait_time}s... (Positionen: {len(portfolio.positions)})")
        time.sleep(wait_time)

@app.route('/')
def dashboard():
    """Hauptseite des Dashboards"""
    return render_template('index.html')

@app.route('/api/portfolio')
def get_portfolio_data():
    """API: Portfolio Daten - nutzt Alpaca wenn verfuegbar"""
    portfolio = get_portfolio()
    
    # Wenn Alpaca aktiv, hole echte Account-Daten
    alpaca_info = None
    if alpaca_broker and alpaca_broker.connected:
        alpaca_info = alpaca_broker.get_account_info()
    
    # Bereite aktuelle Preise vor
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
            'unrealized_pnl_percent': upnl_pct
        })
    
    # Wenn Alpaca verbunden, auch Alpaca-Positionen einfliessen lassen
    if alpaca_broker and alpaca_broker.connected and alpaca_info:
        # Alpaca hat das echte Equity
        alpaca_equity = alpaca_info.get('equity', stats['total_equity'])
        alpaca_cash = alpaca_info.get('cash', portfolio.current_balance)
    else:
        alpaca_equity = stats['total_equity']
        alpaca_cash = portfolio.current_balance
        
    # Extrahiere Equity History fuer den Chart
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
    """API: Letzte Trade History"""
    portfolio = get_portfolio()
    trades = []
    for trade in portfolio.closed_trades[-50:]:  # Letzte 50 Trades
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
    """API: Live Trading Signals - nutzt gecachte Signale vom Background-Thread"""
    # Verwende gecachte Signale statt neue AI-Aufrufe
    signals = []
    
    with _cached_signals_lock:
        for asset in STOCKS[:5]:
            cached = _cached_signals.get(asset)
            if cached and cached['signal'] and (time.time() - cached['timestamp']) < 300:
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
    """API: Detaillierte Signals mit News-Kontext - nutzt gecachte Signale"""
    news_fetcher = get_news_fetcher()
    signals = []

    assets = STOCKS if TRADING_MODE in ["STOCKS", "HYBRID"] else CRYPTO_PAIRS
    asset_type = "STOCK" if TRADING_MODE in ["STOCKS", "HYBRID"] else "CRYPTO"

    for asset in assets:
        # Verwende gecachte Signale statt neue AI-Aufrufe
        signal = None
        with _cached_signals_lock:
            cached = _cached_signals.get(asset)
            if cached and (time.time() - cached['timestamp']) < 300:
                signal = cached['signal']
        
        # Hole News fuer jedes Asset
        news = []
        sentiment = None
        current_price = 0
        if asset_type == "STOCK":
            try:
                news = news_fetcher.get_company_news(asset, days_back=3, max_articles=5)
                sentiment = news_fetcher.get_market_sentiment(asset)
            except Exception:
                pass
            # Hole aktuellen Preis auch wenn kein Signal
            try:
                fetcher = get_data_fetcher()
                current_price = fetcher.get_current_price(asset) or 0
            except Exception:
                pass

        # Bestimme den richtigen Status-Text
        if signal:
            reason_text = signal.get('reason', 'Signal generiert')
        else:
            reason_text = 'Kein starkes Signal erkannt (Confidence zu niedrig oder HOLD)'

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
    """API: Aktuelle Nachrichten fuer ein bestimmtes Symbol"""
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
    """API: Market Informationen"""
    fetcher = get_data_fetcher()
    market_data = []

    for symbol in STOCKS[:8]:  # Top 8 Assets im Dashboard
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
    print(f"[AUTO-TRADE] Status geaendert: {status_msg}")
    return jsonify({
        'status': 'success',
        'enabled': enabled,
        'message': f"Auto-Trade is now {status_msg}"
    })

@app.route('/api/alpaca/info')
def alpaca_info():
    """API: Alpaca Account Info"""
    if not alpaca_broker or not alpaca_broker.connected:
        return jsonify({'connected': False, 'message': 'Alpaca nicht verbunden'})
    
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
    # Einmaliger Startup-Sync mit Alpaca
    alpaca_startup_sync()

    # Starte Background Trading Loop - mit Guard gegen doppeltes Starten
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        with _thread_lock:
            if not _thread_started:
                _thread_started = True
                auto_trade_thread = threading.Thread(target=background_trading_loop, daemon=True)
                auto_trade_thread.start()
    
    print("[START] Dashboard laeuft auf http://localhost:5000")
    print(f"[CONFIG] Max Positionen: {MAX_POSITIONS}, Assets: {len(STOCKS)}")
    if alpaca_broker and alpaca_broker.connected:
        print("[ALPACA] Paper Trading verbunden - Trades werden an Alpaca gesendet!")
        print("[ALPACA] Daten werden von Alpaca geholt (Yahoo als Fallback)")
    else:
        print("[INFO] Alpaca nicht verbunden - nutze lokales Paper Trading + Yahoo Daten")
    app.run(debug=True, port=5000, use_reloader=False)
