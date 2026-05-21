"""Tests for strategy engine: signal validation, position sizing, technical score."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from strategy import TechnicalAnalyzer, StrategyEngine


# ---------------------------------------------------------------------------
# validate_signal
# ---------------------------------------------------------------------------

class TestValidateSignal:

    def setup_method(self):
        # StrategyEngine.__init__ connects to data sources, so we instantiate
        # just the parts we need. validate_signal is a pure function on self.
        self.engine = StrategyEngine.__new__(StrategyEngine)

    def test_valid_buy_signal(self):
        signal = {
            'signal': 'BUY',
            'confidence': 0.75,
            'entry_price': 100.0,
            'stop_loss': 95.0,
            'take_profit': 110.0,
        }
        assert self.engine.validate_signal(signal) is True

    def test_valid_sell_signal(self):
        signal = {
            'signal': 'SELL',
            'confidence': 0.65,
            'entry_price': 100.0,
            'stop_loss': 105.0,
            'take_profit': 90.0,
        }
        assert self.engine.validate_signal(signal) is True

    def test_buy_sl_above_entry_is_invalid(self):
        """BUY with stop_loss >= entry_price is logically wrong."""
        signal = {
            'signal': 'BUY',
            'confidence': 0.7,
            'entry_price': 100.0,
            'stop_loss': 101.0,    # Wrong: SL above entry for a long
            'take_profit': 110.0,
        }
        assert self.engine.validate_signal(signal) is False

    def test_buy_tp_below_entry_is_invalid(self):
        """BUY with take_profit <= entry_price is logically wrong."""
        signal = {
            'signal': 'BUY',
            'confidence': 0.7,
            'entry_price': 100.0,
            'stop_loss': 95.0,
            'take_profit': 99.0,   # Wrong: TP below entry for a long
        }
        assert self.engine.validate_signal(signal) is False

    def test_sell_sl_below_entry_is_invalid(self):
        """SELL with stop_loss <= entry_price is logically wrong."""
        signal = {
            'signal': 'SELL',
            'confidence': 0.7,
            'entry_price': 100.0,
            'stop_loss': 95.0,     # Wrong: SL below entry for a short
            'take_profit': 90.0,
        }
        assert self.engine.validate_signal(signal) is False

    def test_sell_tp_above_entry_is_invalid(self):
        """SELL with take_profit >= entry_price is logically wrong."""
        signal = {
            'signal': 'SELL',
            'confidence': 0.7,
            'entry_price': 100.0,
            'stop_loss': 105.0,
            'take_profit': 101.0,  # Wrong: TP above entry for a short
        }
        assert self.engine.validate_signal(signal) is False

    def test_confidence_out_of_range(self):
        signal = {
            'signal': 'BUY',
            'confidence': 1.5,     # Invalid: > 1
            'entry_price': 100.0,
            'stop_loss': 95.0,
            'take_profit': 110.0,
        }
        assert self.engine.validate_signal(signal) is False

    def test_negative_confidence(self):
        signal = {
            'signal': 'BUY',
            'confidence': -0.1,
            'entry_price': 100.0,
            'stop_loss': 95.0,
            'take_profit': 110.0,
        }
        assert self.engine.validate_signal(signal) is False

    def test_missing_fields(self):
        signal = {'signal': 'BUY', 'confidence': 0.7}
        assert self.engine.validate_signal(signal) is False

    def test_none_signal(self):
        assert self.engine.validate_signal(None) is False

    def test_empty_dict(self):
        assert self.engine.validate_signal({}) is False


# ---------------------------------------------------------------------------
# calculate_position_size
# ---------------------------------------------------------------------------

class TestPositionSizing:

    def setup_method(self):
        self.engine = StrategyEngine.__new__(StrategyEngine)

    def test_basic_position_size(self):
        """With $10k balance, 2% risk, $5 price risk → should risk $200,
        giving position size of 40 units."""
        size = self.engine.calculate_position_size(
            portfolio_balance=10_000,
            risk_percent=2.0,
            entry_price=100.0,
            stop_loss=95.0,
        )
        # risk_amount = 10000 * 0.02 = 200
        # price_risk = |100 - 95| = 5
        # size = 200 / 5 = 40
        assert size == pytest.approx(40.0)

    def test_zero_price_risk(self):
        """If entry == stop_loss, position size must be 0 (avoid division by zero)."""
        size = self.engine.calculate_position_size(10_000, 2.0, 100.0, 100.0)
        assert size == 0

    def test_zero_entry_price(self):
        size = self.engine.calculate_position_size(10_000, 2.0, 0.0, 50.0)
        assert size == 0

    def test_zero_stop_loss(self):
        size = self.engine.calculate_position_size(10_000, 2.0, 100.0, 0.0)
        assert size == 0

    def test_higher_risk_means_larger_position(self):
        size_low = self.engine.calculate_position_size(10_000, 1.0, 100.0, 95.0)
        size_high = self.engine.calculate_position_size(10_000, 5.0, 100.0, 95.0)
        assert size_high > size_low


# ---------------------------------------------------------------------------
# TechnicalAnalyzer.get_technical_score
# ---------------------------------------------------------------------------

class TestTechnicalScore:

    def _make_indicators(self, **overrides):
        """Create a baseline neutral indicator set."""
        base = {
            'close': 100.0,
            'open': 99.0,
            'high': 101.0,
            'low': 98.0,
            'volume': 1_000_000,
            'RSI': 50.0,
            'MACD': 0.0,
            'MACD_signal': 0.0,
            'MACD_diff': 0.0,
            'SMA_20': 100.0,
            'SMA_50': 100.0,
            'EMA_12': 100.0,
            'ATR': 2.0,
            'BB_upper': 104.0,
            'BB_lower': 96.0,
            'BB_width': 0.08,
            'ADX': 25.0,
            'STOCH_K': 50.0,
            'STOCH_D': 50.0,
            'Volume_Ratio': 1.0,
        }
        base.update(overrides)
        return base

    def test_neutral_score_near_zero(self):
        indicators = self._make_indicators()
        score, _ = TechnicalAnalyzer.get_technical_score(indicators)
        # Neutral indicators should produce a score near zero
        assert abs(score) < 10

    def test_oversold_rsi_is_bullish(self):
        indicators = self._make_indicators(RSI=25.0)
        score, details = TechnicalAnalyzer.get_technical_score(indicators)
        assert details['RSI'] > 0, "RSI < 30 should produce a positive RSI score"

    def test_overbought_rsi_is_bearish(self):
        indicators = self._make_indicators(RSI=75.0)
        score, details = TechnicalAnalyzer.get_technical_score(indicators)
        assert details['RSI'] < 0, "RSI > 70 should produce a negative RSI score"

    def test_price_above_both_mas_is_bullish(self):
        indicators = self._make_indicators(close=110.0, SMA_20=105.0, SMA_50=100.0)
        score, details = TechnicalAnalyzer.get_technical_score(indicators)
        assert details['MA'] > 0

    def test_price_below_both_mas_is_bearish(self):
        indicators = self._make_indicators(close=90.0, SMA_20=95.0, SMA_50=100.0)
        score, details = TechnicalAnalyzer.get_technical_score(indicators)
        assert details['MA'] < 0

    def test_near_lower_bb_is_bullish(self):
        # close near BB_lower → BB position < 0.2
        indicators = self._make_indicators(close=96.5, BB_lower=96.0, BB_upper=104.0)
        score, details = TechnicalAnalyzer.get_technical_score(indicators)
        assert details['BB'] > 0

    def test_near_upper_bb_is_bearish(self):
        # close near BB_upper → BB position > 0.8
        indicators = self._make_indicators(close=103.5, BB_lower=96.0, BB_upper=104.0)
        score, details = TechnicalAnalyzer.get_technical_score(indicators)
        assert details['BB'] < 0

    def test_none_indicators_returns_zero(self):
        score, details = TechnicalAnalyzer.get_technical_score(None)
        assert score == 0
        assert details == {}
