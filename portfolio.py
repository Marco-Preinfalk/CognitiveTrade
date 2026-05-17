"""Portfolio management with JSON persistence, P&L tracking, and slippage simulation."""

import json
import os
from datetime import datetime
from enum import Enum
import pandas as pd
from utils import print_success, print_error, print_info, print_warning, format_currency, format_percent
from config import INITIAL_BALANCE, RISK_PER_TRADE, MAX_POSITIONS, SLIPPAGE_PERCENT, COMMISSION_PER_TRADE

PORTFOLIO_FILE = "portfolio_data.json"

class TradeStatus(Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"

class Trade:

    def __init__(self, trade_id, asset, signal_type, entry_price, stop_loss, take_profit, position_size):
        self.id = trade_id
        self.asset = asset
        self.signal_type = signal_type  # BUY, SELL
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.position_size = position_size
        self.entry_time = datetime.now()
        self.exit_time = None
        self.exit_price = None
        self.status = TradeStatus.OPEN
        self.pnl = 0
        self.pnl_percent = 0
        self.current_price = entry_price  # Für unrealized P&L Tracking

    def close_trade(self, exit_price):
        """Close trade, applying slippage and commission."""
        slippage_factor = SLIPPAGE_PERCENT / 100
        if self.signal_type == "BUY":
            effective_exit = exit_price * (1 - slippage_factor)
        else:
            effective_exit = exit_price * (1 + slippage_factor)

        self.exit_price = round(effective_exit, 4)
        self.exit_time = datetime.now()
        self.status = TradeStatus.CLOSED

        if self.signal_type == "BUY":
            self.pnl = (self.exit_price - self.entry_price) * self.position_size
        else:  # SELL
            self.pnl = (self.entry_price - self.exit_price) * self.position_size

        # Commission on entry + exit notional
        notional = self.entry_price * self.position_size
        commission = notional * (COMMISSION_PER_TRADE / 100) * 2
        self.pnl -= commission

        self.pnl_percent = (self.pnl / notional) * 100 if notional > 0 else 0

        return self.pnl

    def get_unrealized_pnl(self, current_price=None):
        if current_price is None:
            current_price = self.current_price

        if self.signal_type == "BUY":
            pnl = (current_price - self.entry_price) * self.position_size
        else:
            pnl = (self.entry_price - current_price) * self.position_size

        notional = self.entry_price * self.position_size
        pnl_percent = (pnl / notional) * 100 if notional > 0 else 0
        return pnl, pnl_percent

    def update_current_price(self, price):
        self.current_price = price

    def to_dict(self):
        return {
            'id': self.id,
            'asset': self.asset,
            'signal_type': self.signal_type,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'position_size': self.position_size,
            'entry_time': self.entry_time.isoformat(),
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'exit_price': self.exit_price,
            'status': self.status.value,
            'pnl': self.pnl,
            'pnl_percent': self.pnl_percent,
        }

    @classmethod
    def from_dict(cls, data):
        trade = cls(
            data['id'], data['asset'], data['signal_type'],
            data['entry_price'], data['stop_loss'], data['take_profit'],
            data['position_size']
        )
        trade.entry_time = datetime.fromisoformat(data['entry_time'])
        trade.exit_time = datetime.fromisoformat(data['exit_time']) if data.get('exit_time') else None
        trade.exit_price = data.get('exit_price')
        trade.status = TradeStatus(data['status'])
        trade.pnl = data.get('pnl', 0)
        trade.pnl_percent = data.get('pnl_percent', 0)
        return trade

    def __repr__(self):
        return f"Trade({self.asset} {self.signal_type} @ {self.entry_price})"


class Portfolio:

    def __init__(self, initial_balance=INITIAL_BALANCE):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.trades = []
        self.closed_trades = []
        self.positions = {}  # {asset: Trade}
        self.trade_counter = 0
        self.equity_history = []

    def can_open_position(self, asset, position_size, entry_price):
        required_capital = position_size * entry_price

        if required_capital > self.current_balance:
            print_error(f"Not enough capital! Required: {format_currency(required_capital)}, Available: {format_currency(self.current_balance)}")
            return False

        if len(self.positions) >= MAX_POSITIONS:
            print_error(f"Max positions ({MAX_POSITIONS}) reached")
            return False

        if asset in self.positions:
            print_warning(f"Position for {asset} already exists")
            return False

        max_capital_per_trade = self.initial_balance * 0.25
        if required_capital > max_capital_per_trade:
            print_warning(f"Position too large! Max {format_currency(max_capital_per_trade)} per trade")
            return False

        return True

    def open_trade(self, asset, signal_type, entry_price, stop_loss, take_profit, position_size):
        """Open a new trade, adjusting entry price for slippage."""
        if not self.can_open_position(asset, position_size, entry_price):
            return None

        self.trade_counter += 1
        trade_id = f"TRD_{self.trade_counter:05d}"

        slippage_factor = SLIPPAGE_PERCENT / 100
        if signal_type == "BUY":
            effective_entry = entry_price * (1 + slippage_factor)
        else:
            effective_entry = entry_price * (1 - slippage_factor)
        effective_entry = round(effective_entry, 4)

        trade = Trade(trade_id, asset, signal_type, effective_entry, stop_loss, take_profit, position_size)

        self.trades.append(trade)
        self.positions[asset] = trade

        capital_used = position_size * effective_entry
        self.current_balance -= capital_used

        print_success(f"Trade opened: {trade_id} - {asset} {signal_type} {position_size:.4f} @ {format_currency(effective_entry)}")
        print_info(f"(Market price: {format_currency(entry_price)}, Slippage: {SLIPPAGE_PERCENT}%)")
        print_info(f"SL: {format_currency(stop_loss)} | TP: {format_currency(take_profit)}")
        print_info(f"Available capital: {format_currency(self.current_balance)}")

        # Equity History tracken
        self._record_equity()

        return trade

    def close_trade(self, asset, exit_price):
        if asset not in self.positions:
            print_error(f"No open position for {asset}")
            return None

        trade = self.positions[asset]
        pnl = trade.close_trade(exit_price)

        capital_returned = trade.position_size * trade.entry_price + pnl
        self.current_balance += capital_returned

        del self.positions[asset]
        self.closed_trades.append(trade)

        color = "[+]" if pnl >= 0 else "[-]"
        print_success(f"{color} Trade closed: {trade.id} - P&L: {format_currency(pnl)} ({format_percent(trade.pnl_percent)})")

        # Equity History tracken
        self._record_equity()

        return trade

    def _record_equity(self):
        total_equity = self.current_balance
        for asset, trade in self.positions.items():
            total_equity += trade.position_size * trade.current_price
        self.equity_history.append({
            'timestamp': datetime.now().isoformat(),
            'equity': total_equity,
            'balance': self.current_balance,
            'positions': len(self.positions)
        })

    def update_open_positions(self, current_prices_dict):
        """
        Aktualisiere offene Positionen und überprüfe auf Stop Loss / Take Profit

        Args:
            current_prices_dict: {asset: current_price}

        Returns:
            List von Trades die geschlossen wurden
        """
        closed_trades = []
        assets_to_close = []

        for asset, trade in self.positions.items():
            if asset not in current_prices_dict:
                continue

            current_price = current_prices_dict[asset]

            # Skip prices that deviate >10% from entry (likely stale/wrong data)
            price_deviation = abs(current_price - trade.entry_price) / trade.entry_price
            if price_deviation > 0.10:
                print_warning(
                    f"Suspicious price for {asset}: ${current_price:.2f} "
                    f"(Entry: ${trade.entry_price:.2f}, deviation: {price_deviation:.1%}) - skip"
                )
                continue

            trade.update_current_price(current_price)

            # Check SL/TP
            if trade.signal_type == "BUY":
                if current_price <= trade.stop_loss:
                    assets_to_close.append((asset, current_price, "Stop Loss"))
                elif current_price >= trade.take_profit:
                    assets_to_close.append((asset, current_price, "Take Profit"))
            else:  # SELL
                if current_price >= trade.stop_loss:
                    assets_to_close.append((asset, current_price, "Stop Loss"))
                elif current_price <= trade.take_profit:
                    assets_to_close.append((asset, current_price, "Take Profit"))

        for asset, price, reason in assets_to_close:
            print_info(f"{reason} for {asset} @ {format_currency(price)}")
            closed_trade = self.close_trade(asset, price)
            if closed_trade:
                closed_trades.append(closed_trade)

        return closed_trades

    def get_portfolio_stats(self):
        total_trades = len(self.closed_trades)
        winning_trades = [t for t in self.closed_trades if t.pnl >= 0]
        losing_trades = [t for t in self.closed_trades if t.pnl < 0]

        total_pnl = sum(t.pnl for t in self.closed_trades)
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

        # Durchschnittlicher Gewinn / Verlust
        avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0

        # Profit Factor
        gross_profit = sum(t.pnl for t in winning_trades) if winning_trades else 0
        gross_loss = abs(sum(t.pnl for t in losing_trades)) if losing_trades else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0 if gross_profit > 0 else 0

        # Max Drawdown berechnen
        max_drawdown, max_drawdown_pct = self._calculate_max_drawdown()

        # Berechne unrealized P&L von offenen Positionen
        unrealized_pnl = 0
        for asset, trade in self.positions.items():
            pnl, _ = trade.get_unrealized_pnl()
            unrealized_pnl += pnl

        # Total Equity
        total_equity = self.current_balance + sum(
            t.position_size * t.current_price for t in self.positions.values()
        )

        # Sharpe Ratio (vereinfacht)
        sharpe_ratio = self._calculate_sharpe_ratio()

        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'unrealized_pnl': unrealized_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            'sharpe_ratio': sharpe_ratio,
            'current_balance': self.current_balance,
            'total_equity': total_equity,
            'available_balance': self.current_balance,
            'open_positions': len(self.positions),
            'return_percent': (total_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0,
        }

    def _calculate_max_drawdown(self):
        if not self.equity_history:
            return 0, 0

        equities = [e['equity'] for e in self.equity_history]
        peak = equities[0]
        max_dd = 0
        max_dd_pct = 0

        for equity in equities:
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0
            if drawdown > max_dd:
                max_dd = drawdown
                max_dd_pct = drawdown_pct

        return max_dd, max_dd_pct

    def _calculate_sharpe_ratio(self, risk_free_rate=0.02):
        if len(self.closed_trades) < 2:
            return 0

        returns = [t.pnl_percent / 100 for t in self.closed_trades]
        avg_return = sum(returns) / len(returns)
        std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5

        if std_return == 0:
            return 0

        # Annualize (~250 trading days)
        sharpe = (avg_return - risk_free_rate / 250) / std_return
        return round(sharpe, 2)

    def print_summary(self):
        stats = self.get_portfolio_stats()

        print("\n" + "=" * 60)
        print("PORTFOLIO SUMMARY")
        print("=" * 60)
        print(f"Initial balance:      {format_currency(self.initial_balance)}")
        print(f"Available capital:    {format_currency(self.current_balance)}")
        print(f"Total Equity:         {format_currency(stats['total_equity'])}")
        print(f"In trades:            {format_currency(self.initial_balance - self.current_balance)}")
        print(f"Realized P&L:         {format_currency(stats['total_pnl'])} ({format_percent(stats['return_percent'])})")
        print(f"Unrealized P&L:       {format_currency(stats['unrealized_pnl'])}")
        print(f"\nClosed Trades:")
        print(f"  Total:        {stats['total_trades']}")
        print(f"  Winners:      {stats['winning_trades']}")
        print(f"  Losers:       {stats['losing_trades']}")
        print(f"  Win Rate:     {format_percent(stats['win_rate'])}")
        print(f"  Avg Win:      {format_currency(stats['avg_win'])}")
        print(f"  Avg Loss:     {format_currency(stats['avg_loss'])}")
        print(f"  Profit Factor: {stats['profit_factor']:.2f}")
        print(f"  Sharpe Ratio:  {stats['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown:  {format_currency(stats['max_drawdown'])} ({format_percent(-stats['max_drawdown_pct'])})")
        print(f"\nOpen Positions: {stats['open_positions']}")
        if stats['open_positions'] > 0:
            for asset, trade in self.positions.items():
                upnl, upnl_pct = trade.get_unrealized_pnl()
                emoji = "[+]" if upnl >= 0 else "[-]"
                print(f"  {emoji} {asset}: {trade.signal_type} {trade.position_size:.4f} @ {format_currency(trade.entry_price)} | P&L: {format_currency(upnl)} ({format_percent(upnl_pct)})")
        print("=" * 60 + "\n")

    def print_trade_history(self, limit=10):
        trades_to_show = self.closed_trades[-limit:]

        if not trades_to_show:
            print_info("No closed trades yet")
            return

        print(f"\nLast {len(trades_to_show)} trades:")
        print("-" * 90)
        print(f"{'ID':<12} {'Asset':<10} {'Type':<5} {'Entry':>12} {'Exit':>12} {'P&L':>12} {'%':>8} {'Dauer':<10}")
        print("-" * 90)

        for trade in trades_to_show:
            color = "WIN" if trade.pnl >= 0 else "LOSS"
            duration = ""
            if trade.exit_time and trade.entry_time:
                delta = trade.exit_time - trade.entry_time
                hours = delta.total_seconds() / 3600
                if hours < 1:
                    duration = f"{delta.total_seconds()/60:.0f}m"
                elif hours < 24:
                    duration = f"{hours:.1f}h"
                else:
                    duration = f"{hours/24:.1f}d"

            print(f"{color} {trade.id:<10} {trade.asset:<10} {trade.signal_type:<5} "
                  f"{format_currency(trade.entry_price):>12} "
                  f"{format_currency(trade.exit_price) if trade.exit_price else 'N/A':>12} "
                  f"{format_currency(trade.pnl):>12} "
                  f"{trade.pnl_percent:>+7.2f}% "
                  f"{duration:<10}")
        print("-" * 90 + "\n")

    def save_to_file(self, filepath=PORTFOLIO_FILE):
        try:
            data = {
                'initial_balance': self.initial_balance,
                'current_balance': self.current_balance,
                'trade_counter': self.trade_counter,
                'open_trades': {asset: trade.to_dict() for asset, trade in self.positions.items()},
                'closed_trades': [t.to_dict() for t in self.closed_trades],
                'equity_history': self.equity_history[-500:],  # Letzte 500 Einträge
                'saved_at': datetime.now().isoformat(),
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            print_success(f"Portfolio saved to {filepath}")
        except Exception as e:
            print_error(f"Error saving portfolio: {str(e)}")

    def load_from_file(self, filepath=PORTFOLIO_FILE):
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)

            self.initial_balance = data['initial_balance']
            self.current_balance = data['current_balance']
            self.trade_counter = data.get('trade_counter', 0)
            self.equity_history = data.get('equity_history', [])

            self.trades = []

            # Load open trades
            self.positions = {}
            for asset, trade_data in data.get('open_trades', {}).items():
                trade = Trade.from_dict(trade_data)
                self.positions[asset] = trade
                self.trades.append(trade)

            # Load closed trades
            self.closed_trades = [Trade.from_dict(t) for t in data.get('closed_trades', [])]
            self.trades.extend(self.closed_trades)

            print_success(f"Portfolio loaded: {len(self.positions)} open, {len(self.closed_trades)} closed trades")
            return True
        except Exception as e:
            print_error(f"Error loading portfolio: {str(e)}")
            return False
