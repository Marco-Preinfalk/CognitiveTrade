"""Backtesting engine for validating strategies on historical data."""

from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from data_fetcher import get_data_fetcher
from strategy import get_strategy_engine, TechnicalAnalyzer
from portfolio import Portfolio
from config import BACKTEST_DAYS, BACKTEST_INTERVAL, DEBUG_MODE, RISK_PER_TRADE
from utils import print_success, print_info, print_warning, format_currency, format_percent

class BacktestEngine:

    def __init__(self):
        self.fetcher = get_data_fetcher()
        self.analyzer = TechnicalAnalyzer()
        self.strategy = get_strategy_engine()

    def backtest_asset(self, asset, asset_type="CRYPTO", days=BACKTEST_DAYS, interval=BACKTEST_INTERVAL):
        """
        Backtest a strategy on a single asset.

        Args:
            asset: e.g. "BTCUSDT" or "AAPL"
            asset_type: "CRYPTO" or "STOCK"
            days: how many days back
            interval: timeframe for bars

        Returns:
            Dict with backtest results.
        """
        print_info(f"\nStarting backtest for {asset} ({days} days, interval: {interval})...")


        if asset_type == "CRYPTO":
            df = self.fetcher.get_crypto_klines(asset, interval=interval, limit=min(days * 24, 1000))
        else:
            interval_map = {"1h": "1h", "4h": "4h", "1d": "1d"}
            df = self.fetcher.get_stock_data(asset, days=days, interval=interval_map.get(interval, "1h"))

        if df is None or df.empty:
            print_warning(f"No data for backtest of {asset}")
            return None


        df = self.analyzer.calculate_indicators(df)

        if df.empty:
            print_warning(f"Not enough data after indicator calculation for {asset}")
            return None


        portfolio = Portfolio()


        current_position = None
        trades_generated = 0

        current_prices = {}

        for idx in range(len(df) - 1):
            current_row = df.iloc[idx:idx+1]
            current_price = float(current_row['close'].iloc[0])
            current_prices[asset] = current_price
            

            portfolio.update_open_positions(current_prices)

            # Check if SL/TP closed the trade
            if current_position and asset not in portfolio.positions:
                current_position = None

            if not current_position and idx > max(50, 26):
                indicators = self.analyzer.get_latest_indicators(df.iloc[:idx+1])
                
                if indicators:
                    score, details = self.analyzer.get_technical_score(indicators)
                    
                    # Simplified signal based on tech score (avoids thousands of LLM calls)
                    signal_dict = None
                    if score >= 20.0:
                        signal_dict = {'signal': 'BUY', 'confidence': min(0.9, 0.5 + score/200.0)}
                    elif score <= -20.0:
                        signal_dict = {'signal': 'SELL', 'confidence': min(0.9, 0.5 + abs(score)/200.0)}
                    
                    if signal_dict:
                        entry_price = current_price
                        signal_dict['entry_price'] = entry_price
                        
                        # ATR-based SL/TP via strategy engine
                        enhanced_signal = self.strategy._enhance_signal(signal_dict, indicators)
                        
                        stop_loss = enhanced_signal['stop_loss']
                        take_profit = enhanced_signal['take_profit']


                        position_size = self.strategy.calculate_position_size(
                            portfolio.current_balance, 
                            RISK_PER_TRADE * 100,
                            entry_price,
                            stop_loss
                        )

                        if position_size > 0 and portfolio.can_open_position(asset, position_size, entry_price):
                            trade = portfolio.open_trade(
                                asset,
                                enhanced_signal['signal'],
                                entry_price,
                                stop_loss,
                                take_profit,
                                position_size
                            )
                            if trade:
                                current_position = enhanced_signal['signal']
                                trades_generated += 1

        # Close any remaining position at end of backtest
        if current_position and asset in portfolio.positions:
            final_price = float(df.iloc[-1]['close'])
            portfolio.close_trade(asset, final_price)

        stats = portfolio.get_portfolio_stats()

        result = {
            'asset': asset,
            'initial_balance': portfolio.initial_balance,
            'final_balance': portfolio.current_balance,
            'total_pnl': stats['total_pnl'],
            'total_return_percent': stats['return_percent'],
            'total_trades': stats['total_trades'],
            'winning_trades': stats['winning_trades'],
            'losing_trades': stats['losing_trades'],
            'win_rate': stats['win_rate'],
            'profit_factor': stats['profit_factor'],
            'sharpe_ratio': stats['sharpe_ratio'],
            'max_drawdown': stats['max_drawdown'],
            'max_drawdown_pct': stats['max_drawdown_pct'],
            'portfolio': portfolio
        }

        return result

    def backtest_multiple(self, assets, asset_type="CRYPTO"):
        results = []

        print_info(f"\n{'='*60}")
        print_info(f"BACKTEST - {len(assets)} Assets ({asset_type})")
        print_info(f"{'='*60}\n")

        for asset in assets:
            result = self.backtest_asset(asset, asset_type=asset_type)
            if result:
                results.append(result)

        return results

    def print_backtest_results(self, results):
        if not results:
            return

        print("\n" + "="*100)
        print("BACKTEST RESULTS")
        print("="*100)

        total_combined_return = 0
        total_combined_trades = 0

        for result in results:
            print(f"\n{result['asset']}:")
            print(f"  Initial capital: {format_currency(result['initial_balance'])}")
            print(f"  Final capital:   {format_currency(result['final_balance'])}")
            print(f"  Total P&L:       {format_currency(result['total_pnl'])} ({format_percent(result['total_return_percent'])})")
            print(f"  Trades:       {result['total_trades']} ({result['winning_trades']}W/{result['losing_trades']}L)")
            print(f"  Win Rate:     {format_percent(result['win_rate'])}")
            print(f"  Profit Factor:{result['profit_factor']:.2f}")
            print(f"  Sharpe Ratio: {result['sharpe_ratio']:.2f}")
            print(f"  Max Drawdown: -{result['max_drawdown_pct']:.2f}% ({format_currency(result['max_drawdown'])})")

            total_combined_return += result['total_return_percent']
            total_combined_trades += result['total_trades']

        print(f"\n{'='*100}")
        print(f"Average return: {format_percent(total_combined_return / len(results))}")
        print(f"Total trades: {total_combined_trades}")
        print("="*100 + "\n")


# Singleton
_backtest_engine = None

def get_backtest_engine():
    global _backtest_engine
    if _backtest_engine is None:
        _backtest_engine = BacktestEngine()
    return _backtest_engine
