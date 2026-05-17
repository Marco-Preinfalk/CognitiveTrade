"""Main application - CLI interface for the trading bot."""

import json
from datetime import datetime
from config import (
    TRADING_MODE, CRYPTO_PAIRS, STOCKS, DEBUG_MODE,
    INITIAL_BALANCE, MAX_POSITIONS, TELEGRAM_ENABLED,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, RISK_PER_TRADE
)
from data_fetcher import get_data_fetcher
from ai_engine import get_ai_engine
from strategy import get_strategy_engine
from portfolio import Portfolio
from backtest import get_backtest_engine
from telegram_alerts import get_telegram_alerter
from utils import (
    print_divider, print_success, print_error, print_info,
    print_warning, format_currency, format_percent, format_trade_signal
)


class TradingBot:
    """CLI trading bot with AI-powered signal generation and paper trading."""

    def __init__(self):
        print_divider()
        print_success("AI Trading Bot v2.0")
        print_divider()

        self.fetcher = get_data_fetcher()
        self.ai_engine = get_ai_engine()
        self.strategy = get_strategy_engine()
        

        self.portfolio = Portfolio(initial_balance=INITIAL_BALANCE)
        self.portfolio.load_from_file()

        self.backtest_engine = get_backtest_engine()
        self.running = False

        # Initialisiere Telegram Alerts
        if TELEGRAM_ENABLED and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            is_placeholder = (
                not TELEGRAM_BOT_TOKEN
                or TELEGRAM_BOT_TOKEN.startswith("DEIN_")
                or "dein_" in TELEGRAM_BOT_TOKEN.lower()
                or len(TELEGRAM_BOT_TOKEN) < 20
            )
            if not is_placeholder:
                self.telegram_alerter = get_telegram_alerter(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
                if self.telegram_alerter:
                    import time
                    time.sleep(1)
                    if self.telegram_alerter.connected:
                        self.telegram_alerter.send_portfolio_update(self.portfolio.get_portfolio_stats())
            else:
                print_info("Telegram disabled (placeholder token)")
                self.telegram_alerter = None
        else:
            print_info("Telegram disabled")
            self.telegram_alerter = None

    def menu(self):

        try:
            while True:
                print_divider()
                print("🎯 HAUPTMENÜ")
                print_divider()
                print("1. Fetch live trading signals")
                print("2. Paper trading update (check prices)")
                print("3. Run backtest")
                print("4. Show portfolio")
                print("5. Show market info")
                print("6. DeepSeek test")
                print("7. Clear cache")
                print("0. Exit")
                print_divider()

                choice = input("Choose an option (0-7): ").strip()

                if choice == "1":
                    self.show_live_signals()
                elif choice == "2":
                    self.run_paper_trading()
                elif choice == "3":
                    self.run_backtest()
                elif choice == "4":
                    self.portfolio.print_summary()
                    self.portfolio.print_trade_history()
                elif choice == "5":
                    self.show_market_info()
                elif choice == "6":
                    self.test_deepseek()
                elif choice == "7":
                    self.fetcher.clear_cache()
                    print_success("Cache cleared")
                elif choice == "0":
                    print_success("Saving portfolio and exiting...")
                    self.portfolio.save_to_file()
                    if self.telegram_alerter:
                        self.telegram_alerter.stop()
                    break
                else:
                    print_error("Invalid option")
        except KeyboardInterrupt:
            print_success("\nSaving portfolio and exiting (Ctrl+C)...")
            self.portfolio.save_to_file()
            if self.telegram_alerter:
                self.telegram_alerter.stop()

    def show_live_signals(self):

        print_info("\nFetching live signals...\n")

        if not self.ai_engine.connected:
            print_error("Ollama is not reachable. Cannot generate signals.")
            return

        if TRADING_MODE in ["CRYPTO", "HYBRID"]:
            print_info(f"CRYPTO ({len(CRYPTO_PAIRS)} assets)")
            self._analyze_assets(CRYPTO_PAIRS, "CRYPTO")

        if TRADING_MODE in ["STOCKS", "HYBRID"]:
            print_info(f"STOCKS ({len(STOCKS)} assets)")
            self._analyze_assets(STOCKS, "STOCK")

    def _analyze_assets(self, assets, asset_type):

        signals = []

        for asset in assets:
            print_info(f"  Analyzing {asset}...")
            import time
            time.sleep(0.5)
            signal = self.strategy.analyze_asset(asset, asset_type=asset_type, timeframe="1h")

            if signal and signal.get('signal') in ['BUY', 'SELL']:
                signal_display = format_trade_signal(signal)
                print_success(f"  Signal for {asset}:{signal_display}")

                if self.telegram_alerter:
                    self.telegram_alerter.send_signal_alert(asset, signal)

                signals.append(signal)
            else:
                print_warning(f"  No clear signal for {asset} (confidence below threshold)")

        print_divider()
        if signals:
            print_success(f"{len(signals)} valid signals found")

            choice = input("\nOpen trades from these signals? (y/n): ").lower()
            if choice in ("j", "y", "ja", "yes"):
                for signal in signals:
                    self._open_trade_from_signal(signal)
                
                self.portfolio.save_to_file()

        else:
            print_warning("No valid signals at this time")

    def _open_trade_from_signal(self, signal):

        asset = signal.get('asset')
        
        if self.portfolio.current_balance <= 0:
            print_warning(f"Not enough capital to open trade for {asset}. Skipping.")
            return

        risk_pct = RISK_PER_TRADE
        if risk_pct < 1:
            risk_pct = risk_pct * 100  # 0.02 -> 2.0
        
        position_size = self.strategy.calculate_position_size(
            self.portfolio.current_balance, 
            risk_pct,
            signal.get('entry_price', 1),
            signal.get('stop_loss', 1)
        )
        
        if position_size <= 0:
            print_warning(f"Could not calculate position size for {asset}. Skipping.")
            return

        trade = self.portfolio.open_trade(
            asset,
            signal.get('signal'),
            signal.get('entry_price'),
            signal.get('stop_loss'),
            signal.get('take_profit'),
            position_size
        )

        if trade:
            if self.telegram_alerter:
                self.telegram_alerter.send_trade_open_alert(
                    trade.id,
                    asset,
                    signal.get('signal'),
                    signal.get('entry_price'),
                    position_size
                )

    def run_paper_trading(self):

        print_info("\nPAPER TRADING UPDATE")
        print_divider()
        
        if not self.portfolio.positions:
            print_info("No open positions to check.")
            return

        print_info(f"Checking {len(self.portfolio.positions)} open positions...")
        current_prices = {}
        
        for asset in self.portfolio.positions:
            price = self.fetcher.get_current_price(asset)
            if price:
                current_prices[asset] = price
            import time
            time.sleep(0.2)

        if current_prices:
            closed_trades = self.portfolio.update_open_positions(current_prices)
            
            if self.telegram_alerter:
                for t in closed_trades:
                    reason = "Stop Loss" if t.pnl < 0 else "Take Profit"
                    self.telegram_alerter.send_trade_close_alert(t.id, t.asset, t.pnl, t.pnl_percent, reason)
            
            if closed_trades:
                self.portfolio.save_to_file()
                
        self.portfolio.print_summary()

    def run_backtest(self):
        print_info("\nBACKTEST MODE")
        print_divider()

        if TRADING_MODE in ["CRYPTO", "HYBRID"]:
            print_info("Backtesting crypto...")
            crypto_results = self.backtest_engine.backtest_multiple(CRYPTO_PAIRS, "CRYPTO")
            if crypto_results:
                self.backtest_engine.print_backtest_results(crypto_results)

        if TRADING_MODE in ["STOCKS", "HYBRID"]:
            print_info("Backtesting stocks...")
            stock_results = self.backtest_engine.backtest_multiple(STOCKS, "STOCK")
            if stock_results:
                self.backtest_engine.print_backtest_results(stock_results)

    def show_market_info(self):
        print_info("\nMARKET INFO")
        print_divider()

        if TRADING_MODE in ["CRYPTO", "HYBRID"]:
            print_info("\nCRYPTO (24h stats)")
            for symbol in CRYPTO_PAIRS:
                stats = self.fetcher.get_crypto_24h_stats(symbol)
                if stats:
                    change_color = "🟢" if stats['change'] >= 0 else "🔴"
                    print(f"  {symbol:<10}: {format_currency(stats['price'], '')} {change_color} {format_percent(stats['change'])}")

        if TRADING_MODE in ["STOCKS", "HYBRID"]:
            print_info("\nSTOCKS (Yahoo Info)")
            for symbol in STOCKS:
                info = self.fetcher.get_stock_info(symbol)
                if info and info.get('price') is not None:
                    change_color = "🟢" if (info.get('change', 0) or 0) >= 0 else "🔴"
                    print(f"  {symbol:<10}: {format_currency(float(info.get('price', 0)))} {change_color} {format_percent(float(info.get('change', 0) or 0))}")
                    if detail_name := info.get('name'):
                        print(f"      {detail_name}")
                else:
                    print_warning(f"  {symbol}: Data unavailable")

    def test_deepseek(self):
        print_info("\nDEEPSEEK TEST")
        print_divider()


        model_info = self.ai_engine.get_model_info()
        if model_info:
            print_success("DeepSeek connected")
            print_info(f"Model: {self.ai_engine.model}")
            print_info(f"Temperature: {self.ai_engine.temperature}")
        else:
            print_error("Ollama not responding to show request.")
            return

        print_info("\nTesting AI with Bitcoin data...")

        df = self.fetcher.get_crypto_klines("BTCUSDT", interval="1h", limit=100)
        if df is not None and not df.empty:
            from strategy import TechnicalAnalyzer
            analyzer = TechnicalAnalyzer()
            df_ind = analyzer.calculate_indicators(df)
            tech_data = analyzer.get_latest_indicators(df_ind)
            tech_score, score_details = analyzer.get_technical_score(tech_data)
            
            tech_data['tech_score'] = tech_score

            print_info("\nTechnical indicators (latest):")
            print(f"  Close: {format_currency(tech_data['close'])}")
            print(f"  RSI: {tech_data['RSI']:.2f}")
            print(f"  MACD: {tech_data['MACD']:.6f}")
            print(f"  Tech Score: {tech_score:+.2f}")

            print_info("\nAsking DeepSeek for trading signal...")
            signal = self.ai_engine.analyze_market("BTCUSDT", "1h", tech_data)

            if signal:
                print_success("DeepSeek response:")
                print(json.dumps(signal, indent=2, ensure_ascii=False))
            else:
                print_error("No valid signal received")
        else:
            print_error("Cannot load Bitcoin data")

def main():

    bot = TradingBot()
    bot.menu()


if __name__ == "__main__":
    main()
