"""Tests for portfolio math: Trade P&L, slippage, commission, position limits, stats."""

import os
import sys
import json
import tempfile
import pytest

# Ensure project root is on the path so imports work when running from /tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from portfolio import Trade, Portfolio, TradeStatus


# ---------------------------------------------------------------------------
# Trade P&L
# ---------------------------------------------------------------------------

class TestTradePnL:
    """Verify that P&L calculations (including slippage and commission) are
    correct for both BUY and SELL trades."""

    def _make_trade(self, signal_type, entry, size):
        return Trade(
            trade_id="TRD_00001",
            asset="AAPL",
            signal_type=signal_type,
            entry_price=entry,
            stop_loss=entry * 0.95,
            take_profit=entry * 1.10,
            position_size=size,
        )

    def test_buy_trade_profit(self):
        """BUY trade closed above entry should yield positive P&L."""
        t = self._make_trade("BUY", entry=100.0, size=10)
        pnl = t.close_trade(exit_price=110.0)

        # Slippage lowers the effective exit by SLIPPAGE_PERCENT
        # Commission is deducted on both legs
        assert pnl > 0, "Profitable BUY trade must have positive P&L"
        assert t.status == TradeStatus.CLOSED
        assert t.exit_price is not None
        assert t.pnl_percent > 0

    def test_buy_trade_loss(self):
        """BUY trade closed below entry should yield negative P&L."""
        t = self._make_trade("BUY", entry=100.0, size=10)
        pnl = t.close_trade(exit_price=90.0)
        assert pnl < 0

    def test_sell_trade_profit(self):
        """SELL (short) trade closed below entry should yield positive P&L."""
        t = self._make_trade("SELL", entry=100.0, size=10)
        pnl = t.close_trade(exit_price=90.0)
        assert pnl > 0

    def test_sell_trade_loss(self):
        """SELL trade closed above entry should yield negative P&L."""
        t = self._make_trade("SELL", entry=100.0, size=10)
        pnl = t.close_trade(exit_price=110.0)
        assert pnl < 0

    def test_slippage_applied_on_exit(self):
        """The effective exit price must differ from the raw exit price
        by the configured slippage percentage."""
        from config import SLIPPAGE_PERCENT

        t = self._make_trade("BUY", entry=100.0, size=1)
        t.close_trade(exit_price=110.0)

        expected_exit = 110.0 * (1 - SLIPPAGE_PERCENT / 100)
        assert t.exit_price == pytest.approx(expected_exit, abs=0.01)

    def test_commission_deducted(self):
        """P&L must be lower than raw price difference * size due to commission."""
        from config import COMMISSION_PER_TRADE

        t = self._make_trade("BUY", entry=100.0, size=10)
        t.close_trade(exit_price=100.0)  # Flat trade

        # Even a flat trade should lose money because of commission + slippage
        assert t.pnl < 0, "A flat trade must lose money due to costs"


# ---------------------------------------------------------------------------
# Unrealized P&L
# ---------------------------------------------------------------------------

class TestUnrealizedPnL:

    def test_unrealized_pnl_buy(self):
        t = Trade("T1", "AAPL", "BUY", 100.0, 95.0, 110.0, 10)
        pnl, pct = t.get_unrealized_pnl(current_price=105.0)
        assert pnl == pytest.approx(50.0)
        assert pct > 0

    def test_unrealized_pnl_sell(self):
        t = Trade("T1", "AAPL", "SELL", 100.0, 105.0, 90.0, 10)
        pnl, pct = t.get_unrealized_pnl(current_price=95.0)
        assert pnl == pytest.approx(50.0)
        assert pct > 0


# ---------------------------------------------------------------------------
# Portfolio: can_open_position
# ---------------------------------------------------------------------------

class TestCanOpenPosition:

    def test_insufficient_capital(self):
        p = Portfolio(initial_balance=1000)
        assert p.can_open_position("AAPL", 100, 100.0) is False  # needs $10,000

    def test_max_positions_reached(self):
        from config import MAX_POSITIONS

        p = Portfolio(initial_balance=1_000_000)
        for i in range(MAX_POSITIONS):
            sym = f"SYM{i}"
            p.positions[sym] = Trade(f"T{i}", sym, "BUY", 10, 9, 11, 1)

        assert p.can_open_position("NEWSTOCK", 1, 10.0) is False

    def test_duplicate_position(self):
        p = Portfolio(initial_balance=100_000)
        p.positions["AAPL"] = Trade("T1", "AAPL", "BUY", 100, 95, 110, 1)
        assert p.can_open_position("AAPL", 1, 100.0) is False

    def test_position_too_large(self):
        """A single trade must not exceed 25% of initial balance."""
        p = Portfolio(initial_balance=10_000)
        # 25% of $10k = $2,500. Requesting $5,000 worth should fail.
        assert p.can_open_position("AAPL", 50, 100.0) is False

    def test_valid_open(self):
        p = Portfolio(initial_balance=100_000)
        assert p.can_open_position("AAPL", 1, 100.0) is True


# ---------------------------------------------------------------------------
# Portfolio: open_trade applies slippage on entry
# ---------------------------------------------------------------------------

class TestOpenTrade:

    def test_slippage_on_buy_entry(self):
        """BUY entry should be adjusted UP by slippage (worse fill)."""
        from config import SLIPPAGE_PERCENT

        p = Portfolio(initial_balance=100_000)
        trade = p.open_trade("AAPL", "BUY", 100.0, 95.0, 110.0, 10)

        assert trade is not None
        expected_entry = 100.0 * (1 + SLIPPAGE_PERCENT / 100)
        assert trade.entry_price == pytest.approx(expected_entry, abs=0.01)

    def test_slippage_on_sell_entry(self):
        """SELL entry should be adjusted DOWN by slippage (worse fill)."""
        from config import SLIPPAGE_PERCENT

        p = Portfolio(initial_balance=100_000)
        trade = p.open_trade("AAPL", "SELL", 100.0, 105.0, 90.0, 10)

        assert trade is not None
        expected_entry = 100.0 * (1 - SLIPPAGE_PERCENT / 100)
        assert trade.entry_price == pytest.approx(expected_entry, abs=0.01)

    def test_balance_decreases_after_open(self):
        p = Portfolio(initial_balance=100_000)
        p.open_trade("AAPL", "BUY", 100.0, 95.0, 110.0, 5)
        assert p.current_balance < 100_000


# ---------------------------------------------------------------------------
# Portfolio: stats
# ---------------------------------------------------------------------------

class TestPortfolioStats:

    def _build_portfolio_with_trades(self):
        p = Portfolio(initial_balance=100_000)
        # Simulate two closed trades: one win, one loss
        t1 = Trade("T1", "AAPL", "BUY", 100.0, 95.0, 110.0, 10)
        t1.close_trade(110.0)
        p.closed_trades.append(t1)

        t2 = Trade("T2", "MSFT", "BUY", 200.0, 190.0, 220.0, 5)
        t2.close_trade(190.0)
        p.closed_trades.append(t2)

        return p

    def test_win_rate(self):
        p = self._build_portfolio_with_trades()
        stats = p.get_portfolio_stats()
        assert stats['total_trades'] == 2
        assert stats['win_rate'] == pytest.approx(50.0)

    def test_profit_factor(self):
        p = self._build_portfolio_with_trades()
        stats = p.get_portfolio_stats()
        assert stats['profit_factor'] > 0

    def test_empty_portfolio_stats(self):
        p = Portfolio(initial_balance=10_000)
        stats = p.get_portfolio_stats()
        assert stats['total_trades'] == 0
        assert stats['win_rate'] == 0
        assert stats['profit_factor'] == 0


# ---------------------------------------------------------------------------
# Portfolio: atomic save / load
# ---------------------------------------------------------------------------

class TestAtomicSaveLoad:

    def test_save_and_reload(self, tmp_path):
        filepath = str(tmp_path / "test_portfolio.json")

        p = Portfolio(initial_balance=50_000)
        p.open_trade("AAPL", "BUY", 150.0, 140.0, 170.0, 5)
        p.save_to_file(filepath)

        assert os.path.exists(filepath)

        p2 = Portfolio()
        loaded = p2.load_from_file(filepath)
        assert loaded is True
        assert "AAPL" in p2.positions
        assert p2.initial_balance == 50_000

    def test_load_corrupt_json(self, tmp_path):
        filepath = str(tmp_path / "corrupt.json")
        with open(filepath, 'w') as f:
            f.write("{invalid json!!!}")

        p = Portfolio()
        loaded = p.load_from_file(filepath)
        assert loaded is False

        # Corrupt file should have been renamed
        assert os.path.exists(filepath + '.corrupt')

    def test_load_empty_file(self, tmp_path):
        filepath = str(tmp_path / "empty.json")
        with open(filepath, 'w') as f:
            f.write("")

        p = Portfolio()
        loaded = p.load_from_file(filepath)
        assert loaded is False

    def test_load_nonexistent_file(self):
        p = Portfolio()
        loaded = p.load_from_file("/nonexistent/path/portfolio.json")
        assert loaded is False


# ---------------------------------------------------------------------------
# Trade serialization round-trip
# ---------------------------------------------------------------------------

class TestTradeSerialization:

    def test_roundtrip(self):
        t = Trade("T1", "NVDA", "BUY", 500.0, 480.0, 550.0, 3)
        data = t.to_dict()
        t2 = Trade.from_dict(data)

        assert t2.id == t.id
        assert t2.asset == t.asset
        assert t2.signal_type == t.signal_type
        assert t2.entry_price == t.entry_price
        assert t2.position_size == t.position_size
