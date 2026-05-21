"""Ollama/LLM integration for generating trading signals from market data."""

import json
import requests
from config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TEMPERATURE, DEBUG_MODE
from utils import print_success, print_error, print_warning, print_info, parse_ai_response, retry_on_failure

class AIEngine:
    def __init__(self):
        self.ollama_url = f"{OLLAMA_HOST}/api/generate"
        self.model = OLLAMA_MODEL
        self.temperature = OLLAMA_TEMPERATURE
        self.connected = False
        self.check_connection()

    def check_connection(self):
        try:
            response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
            if response.status_code == 200:
                print_success(f"Connected to Ollama at {OLLAMA_HOST}")
                models = response.json().get("models", [])
                if models:
                    available_models = [m["name"] for m in models]
                    print_info(f"Available models: {', '.join(available_models)}")
                    self.connected = True
                else:
                    print_warning("No models found in Ollama. Run `ollama pull mistral:latest`.")
            else:
                print_error("Cannot connect to Ollama")
        except requests.exceptions.ConnectionError:
            print_error(f"Ollama not reachable at {OLLAMA_HOST}")
            print_warning("Start Ollama with: ollama serve")
        except Exception as e:
            print_error(f"Connection check error: {str(e)}")

    @retry_on_failure(max_retries=2, delay=2.0, backoff=2.0, exceptions=(requests.RequestException,))
    def analyze_market(self, asset, timeframe, technical_data, news_digest=None):
        """
        Analyze market data and generate a trading signal.

        Args:
            asset: e.g. "BTCUSDT" or "AAPL"
            timeframe: e.g. "1h" or "1d"
            technical_data: dict with technical indicators

        Returns:
            Signal dict or None
        """
        prompt = self._build_analysis_prompt(asset, timeframe, technical_data, news_digest=news_digest)

        if DEBUG_MODE:
            print_info(f"Sending prompt to {self.model} for {asset}...")

        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": self.temperature,
                    "format": "json",  # Force JSON output for supported models
                },
                timeout=90
            )

            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "")
                signal = parse_ai_response(response_text)

                if signal:
                    signal["asset"] = asset
                    signal["timeframe"] = timeframe

                    signal = self._sanitize_signal(signal, technical_data)

                    return signal
                else:
                    print_warning(f"No valid signal from {self.model} for {asset}")
                    if DEBUG_MODE:
                        print_info(f"Response: {response_text[:300]}...")
                    return None
            else:
                print_error(f"Ollama error: Status {response.status_code}")
                return None
        except requests.exceptions.Timeout:
            print_error("Ollama request timed out (>90s)")
            return None
        except requests.RequestException:
            raise
        except Exception as e:
            print_error(f"AI analysis error: {str(e)}")
            return None

    def _sanitize_signal(self, signal, tech_data):
        """Clean and validate AI signal data to prevent type errors."""
        close = tech_data.get('close', 0)
        
        def safe_float(val, default=0.0):
            if val is None:
                return default
            try:
                if isinstance(val, str):
                    val = val.replace('$', '').replace(',', '')
                return float(val)
            except (ValueError, TypeError):
                return default

        # Confidence: some models return 75 instead of 0.75
        conf = safe_float(signal.get('confidence', 0))
        if conf > 1:
            conf = conf / 100.0
        signal['confidence'] = max(0.0, min(1.0, conf))

        # Entry Price: fall back to close if missing or unrealistic (>10% deviation)
        entry = safe_float(signal.get('entry_price', 0))
        if entry <= 0 or abs(entry - close) / close > 0.1:
            signal['entry_price'] = close
        else:
            signal['entry_price'] = entry
            
        signal['stop_loss'] = safe_float(signal.get('stop_loss', 0))
        signal['take_profit'] = safe_float(signal.get('take_profit', 0))


        sig = signal.get('signal', '').upper().strip()
        if sig in ('BUY', 'LONG'):
            signal['signal'] = 'BUY'
        elif sig in ('SELL', 'SHORT'):
            signal['signal'] = 'SELL'
        elif sig in ('HOLD', 'NEUTRAL', 'WAIT'):
            signal['signal'] = 'HOLD'
        else:
            signal['signal'] = 'HOLD'

        return signal

    def _build_analysis_prompt(self, asset, timeframe, tech_data, news_digest=None):

        clean_data = {k: v for k, v in tech_data.items() if k != 'score_details'}

        for key, val in clean_data.items():
            if isinstance(val, float):
                clean_data[key] = round(val, 4)

        data_str = json.dumps(clean_data, indent=2)

        tech_score = tech_data.get('tech_score', 0)
        score_interpretation = "NEUTRAL"
        if tech_score > 20:
            score_interpretation = "STRONGLY BULLISH"
        elif tech_score > 10:
            score_interpretation = "BULLISH"
        elif tech_score < -20:
            score_interpretation = "STRONGLY BEARISH"
        elif tech_score < -10:
            score_interpretation = "BEARISH"


        news_block = ""
        if news_digest and news_digest != "No current news available.":
            news_block = f"""

CURRENT NEWS for {asset}:
{news_digest}

IMPORTANT: Factor the news into your analysis!
- Positive news (earnings beat, partnerships, growth) = Bullish tendency
- Negative news (lawsuits, revenue decline, regulation) = Bearish tendency
- Weigh the news together with the technical indicators for your final signal"""

        prompt = f"""You are a professional financial analyst and trading expert.
Analyze the following technical data{' and current news' if news_block else ''} and provide a precise trading signal.

ASSET: {asset}
TIMEFRAME: {timeframe}
TECHNICAL SCORE: {tech_score:+.1f} ({score_interpretation})

TECHNICAL DATA:
{data_str}{news_block}

ANALYSIS RULES:
- RSI < 30: Oversold (bullish), RSI > 70: Overbought (bearish)
- MACD > Signal: Bullish, MACD < Signal: Bearish
- Price > SMA50: Uptrend, Price < SMA50: Downtrend
- ADX > 25: Strong trend, ADX < 20: No clear trend (prefer HOLD)
- BB: Price near lower band = Buy opportunity, near upper band = Sell opportunity
- Volume_Ratio > 1.5: Confirms the current trend

RESPONSE: Reply ONLY with valid JSON in this format:
{{"signal": "BUY", "confidence": 0.75, "reason": "Brief reasoning", "entry_price": {clean_data.get('close', 0)}, "stop_loss": 0.0, "take_profit": 0.0, "risk_reward_ratio": 2.0}}

Signal must be BUY, SELL or HOLD. Confidence between 0.0 and 1.0."""

        return prompt

    def get_model_info(self):
        try:
            response = requests.post(f"{OLLAMA_HOST}/api/show",
                                    json={"name": self.model},
                                    timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print_error(f"Model info unavailable: {str(e)}")
        return None


# Singleton
_ai_engine = None

def get_ai_engine():
    global _ai_engine
    if _ai_engine is None:
        _ai_engine = AIEngine()
    return _ai_engine
