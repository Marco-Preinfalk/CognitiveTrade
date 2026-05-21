"""Tests for LLM response parsing and signal sanitization."""

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils import parse_ai_response
from ai_engine import AIEngine


# ---------------------------------------------------------------------------
# parse_ai_response
# ---------------------------------------------------------------------------

class TestParseAiResponse:

    def test_clean_json(self):
        raw = '{"signal": "BUY", "confidence": 0.75, "reason": "bullish"}'
        result = parse_ai_response(raw)
        assert result is not None
        assert result['signal'] == 'BUY'
        assert result['confidence'] == 0.75

    def test_json_in_markdown_code_block(self):
        raw = '''Here is the analysis:
```json
{"signal": "SELL", "confidence": 0.80, "reason": "bearish divergence"}
```
That's my recommendation.'''
        result = parse_ai_response(raw)
        assert result is not None
        assert result['signal'] == 'SELL'

    def test_json_in_code_block_no_lang(self):
        raw = '''```
{"signal": "HOLD", "confidence": 0.30}
```'''
        result = parse_ai_response(raw)
        assert result is not None
        assert result['signal'] == 'HOLD'

    def test_json_embedded_in_text(self):
        raw = 'Based on the data, the result is: {"signal": "BUY", "confidence": 0.60} and I think it will go up.'
        result = parse_ai_response(raw)
        assert result is not None
        assert result['signal'] == 'BUY'

    def test_think_tags_stripped(self):
        """DeepSeek models wrap reasoning in <think> tags. The parser must
        strip those before extracting JSON."""
        raw = '<think>Let me analyze RSI... it looks oversold.</think>{"signal": "BUY", "confidence": 0.70}'
        result = parse_ai_response(raw)
        assert result is not None
        assert result['signal'] == 'BUY'

    def test_empty_string(self):
        assert parse_ai_response("") is None

    def test_none_input(self):
        assert parse_ai_response(None) is None

    def test_whitespace_only(self):
        assert parse_ai_response("   \n\t  ") is None

    def test_no_json_at_all(self):
        assert parse_ai_response("This is just plain text with no JSON.") is None

    def test_invalid_json(self):
        raw = '{"signal": "BUY", confidence: 0.75}'  # Missing quotes around key
        # The brace-matching fallback should still try, but json.loads will fail
        result = parse_ai_response(raw)
        assert result is None

    def test_nested_json_objects(self):
        """Parser should extract the outermost JSON object."""
        raw = '{"signal": "BUY", "metadata": {"source": "AI"}, "confidence": 0.65}'
        result = parse_ai_response(raw)
        assert result is not None
        assert result['signal'] == 'BUY'
        assert result['metadata']['source'] == 'AI'


# ---------------------------------------------------------------------------
# _sanitize_signal
# ---------------------------------------------------------------------------

class TestSanitizeSignal:
    """Tests for AIEngine._sanitize_signal which normalizes LLM output
    into a consistent format."""

    def setup_method(self):
        # Avoid connecting to Ollama during tests
        self.engine = AIEngine.__new__(AIEngine)

    def _make_tech_data(self, close=100.0):
        return {'close': close}

    def test_confidence_above_one_normalized(self):
        """Some models return confidence as 75 instead of 0.75."""
        signal = {'signal': 'BUY', 'confidence': 75, 'entry_price': 100.0}
        result = self.engine._sanitize_signal(signal, self._make_tech_data())
        assert result['confidence'] == 0.75

    def test_confidence_exactly_one(self):
        signal = {'signal': 'BUY', 'confidence': 1.0, 'entry_price': 100.0}
        result = self.engine._sanitize_signal(signal, self._make_tech_data())
        assert result['confidence'] == 1.0

    def test_confidence_clamped_to_bounds(self):
        signal = {'signal': 'BUY', 'confidence': 150, 'entry_price': 100.0}
        result = self.engine._sanitize_signal(signal, self._make_tech_data())
        assert 0.0 <= result['confidence'] <= 1.0

    def test_missing_entry_price_falls_back_to_close(self):
        signal = {'signal': 'BUY', 'confidence': 0.7}
        result = self.engine._sanitize_signal(signal, self._make_tech_data(close=150.0))
        assert result['entry_price'] == 150.0

    def test_unrealistic_entry_price_replaced(self):
        """Entry price deviating >10% from close should be replaced."""
        signal = {'signal': 'BUY', 'confidence': 0.7, 'entry_price': 200.0}
        result = self.engine._sanitize_signal(signal, self._make_tech_data(close=100.0))
        assert result['entry_price'] == 100.0  # Fell back to close

    def test_string_prices_parsed(self):
        """LLMs sometimes return prices as "$150.50" strings."""
        signal = {
            'signal': 'BUY',
            'confidence': 0.7,
            'entry_price': '$100.00',
            'stop_loss': '$95.00',
            'take_profit': '$110.00',
        }
        result = self.engine._sanitize_signal(signal, self._make_tech_data())
        assert result['stop_loss'] == 95.0
        assert result['take_profit'] == 110.0

    def test_signal_aliases_normalized(self):
        """LONG → BUY, SHORT → SELL, WAIT → HOLD, etc."""
        cases = [
            ('LONG', 'BUY'),
            ('long', 'BUY'),
            ('SHORT', 'SELL'),
            ('short', 'SELL'),
            ('HOLD', 'HOLD'),
            ('NEUTRAL', 'HOLD'),
            ('WAIT', 'HOLD'),
            ('???', 'HOLD'),    # Unknown → defaults to HOLD
        ]
        for input_sig, expected in cases:
            signal = {'signal': input_sig, 'confidence': 0.5, 'entry_price': 100.0}
            result = self.engine._sanitize_signal(signal, self._make_tech_data())
            assert result['signal'] == expected, f"Expected '{input_sig}' → '{expected}', got '{result['signal']}'"

    def test_missing_sl_tp_default_to_zero(self):
        signal = {'signal': 'BUY', 'confidence': 0.7, 'entry_price': 100.0}
        result = self.engine._sanitize_signal(signal, self._make_tech_data())
        assert result['stop_loss'] == 0.0
        assert result['take_profit'] == 0.0

    def test_none_confidence(self):
        signal = {'signal': 'BUY', 'confidence': None, 'entry_price': 100.0}
        result = self.engine._sanitize_signal(signal, self._make_tech_data())
        assert result['confidence'] == 0.0
