"""Signal generation using technical indicators and LLM analysis."""

import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, SMAIndicator, EMAIndicator, ADXIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator, VolumeWeightedAveragePrice
from data_fetcher import get_data_fetcher
from ai_engine import get_ai_engine
from news_fetcher import get_news_fetcher
from config import SIGNAL_CONFIDENCE_THRESHOLD, BUY_SIGNAL_STRENGTH, DEBUG_MODE
from utils import print_info, print_warning, print_success, format_percent

class TechnicalAnalyzer:

    @staticmethod
    def calculate_indicators(df, rsi_period=14, macd_fast=12, macd_slow=26, sma_periods=[20, 50]):
        """
        Calculate technical indicators on OHLCV data.

        Returns:
            DataFrame with added indicator columns.
        """
        df = df.copy()

        if len(df) < max(sma_periods) + 5:
            # Not enough data for all indicators
            return df.dropna()

        # RSI (Relative Strength Index)
        rsi = RSIIndicator(close=df['close'], window=rsi_period)
        df['RSI'] = rsi.rsi()

        # MACD
        macd = MACD(close=df['close'], window_fast=macd_fast, window_slow=macd_slow, window_sign=9)
        df['MACD'] = macd.macd()
        df['MACD_signal'] = macd.macd_signal()
        df['MACD_diff'] = macd.macd_diff()

        # Simple Moving Averages
        for period in sma_periods:
            df[f'SMA_{period}'] = SMAIndicator(close=df['close'], window=period).sma_indicator()

        # Exponential Moving Averages
        df['EMA_12'] = EMAIndicator(close=df['close'], window=12).ema_indicator()
        df['EMA_26'] = EMAIndicator(close=df['close'], window=26).ema_indicator()

        # Average True Range (für Volatilität)
        atr = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
        df['ATR'] = atr.average_true_range()

        # Bollinger Bands
        bb = BollingerBands(close=df['close'], window=20, window_dev=2)
        df['BB_upper'] = bb.bollinger_hband()
        df['BB_middle'] = bb.bollinger_mavg()
        df['BB_lower'] = bb.bollinger_lband()
        df['BB_width'] = (df['BB_upper'] - df['BB_lower']) / df['BB_middle']  # Normalisierte Bandbreite

        # ADX (Average Directional Index) - Trendstärke
        try:
            adx = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
            df['ADX'] = adx.adx()
        except Exception:
            df['ADX'] = 25  # Default: moderater Trend

        # Stochastic Oscillator
        try:
            stoch = StochasticOscillator(high=df['high'], low=df['low'], close=df['close'], window=14, smooth_window=3)
            df['STOCH_K'] = stoch.stoch()
            df['STOCH_D'] = stoch.stoch_signal()
        except Exception:
            df['STOCH_K'] = 50
            df['STOCH_D'] = 50

        # On-Balance Volume
        try:
            obv = OnBalanceVolumeIndicator(close=df['close'], volume=df['volume'])
            df['OBV'] = obv.on_balance_volume()
            # OBV SMA für Trend
            df['OBV_SMA'] = df['OBV'].rolling(window=20).mean()
        except Exception:
            df['OBV'] = 0
            df['OBV_SMA'] = 0

        # Volume Moving Average
        df['Volume_SMA'] = df['volume'].rolling(window=20).mean()
        df['Volume_Ratio'] = df['volume'] / df['Volume_SMA'].replace(0, 1)

        # Price Change (Returns)
        df['returns'] = df['close'].pct_change()
        df['returns_5'] = df['close'].pct_change(5)


        df = df.dropna()

        return df

    @staticmethod
    def get_latest_indicators(df):
        """Get the latest indicator values from the DataFrame."""
        if df.empty:
            return None

        latest = df.iloc[-1]
        result = {
            'close': float(latest['close']),
            'open': float(latest.get('open', latest['close'])),
            'high': float(latest['high']),
            'low': float(latest['low']),
            'volume': float(latest.get('volume', 0)),
            'RSI': float(latest['RSI']),
            'MACD': float(latest['MACD']),
            'MACD_signal': float(latest['MACD_signal']),
            'MACD_diff': float(latest['MACD_diff']),
            'SMA_20': float(latest['SMA_20']),
            'SMA_50': float(latest['SMA_50']),
            'EMA_12': float(latest['EMA_12']),
            'ATR': float(latest['ATR']),
            'BB_upper': float(latest['BB_upper']),
            'BB_lower': float(latest['BB_lower']),
            'BB_width': float(latest['BB_width']),
            'ADX': float(latest.get('ADX', 25)),
            'STOCH_K': float(latest.get('STOCH_K', 50)),
            'STOCH_D': float(latest.get('STOCH_D', 50)),
            'Volume_Ratio': float(latest.get('Volume_Ratio', 1)),
        }
        return result

    @staticmethod
    def get_technical_score(indicators):
        """
        Calculate a composite technical score from -100 (very bearish) to +100 (very bullish).
        """
        if not indicators:
            return 0, {}

        score = 0
        details = {}
        close = indicators['close']

        # === RSI Score (Gewicht: 20%) ===
        rsi = indicators['RSI']
        if rsi < 30:
            rsi_score = 30  # Stark überverkauft = bullish
        elif rsi < 40:
            rsi_score = 15
        elif rsi < 60:
            rsi_score = 0   # Neutral
        elif rsi < 70:
            rsi_score = -15
        else:
            rsi_score = -30  # Stark überkauft = bearish
        score += rsi_score * 0.20
        details['RSI'] = rsi_score

        # === MACD Score (Gewicht: 20%) ===
        macd_diff = indicators['MACD_diff']
        if macd_diff > 0:
            macd_score = min(30, macd_diff / indicators['ATR'] * 20) if indicators['ATR'] > 0 else 15
        else:
            macd_score = max(-30, macd_diff / indicators['ATR'] * 20) if indicators['ATR'] > 0 else -15
        score += macd_score * 0.20
        details['MACD'] = round(macd_score, 1)

        # === Moving Average Score (Gewicht: 25%) ===
        sma20 = indicators['SMA_20']
        sma50 = indicators['SMA_50']
        ma_score = 0
        if close > sma20 > sma50:
            ma_score = 25  # Price über beiden MAs, bullish
        elif close > sma20:
            ma_score = 10
        elif close < sma20 < sma50:
            ma_score = -25  # Price unter beiden MAs, bearish
        elif close < sma20:
            ma_score = -10
        score += ma_score * 0.25
        details['MA'] = ma_score

        # === Bollinger Bands Score (Gewicht: 15%) ===
        bb_upper = indicators['BB_upper']
        bb_lower = indicators['BB_lower']
        bb_range = bb_upper - bb_lower if bb_upper != bb_lower else 1
        bb_position = (close - bb_lower) / bb_range
        if bb_position < 0.2:
            bb_score = 20  # Nahe unterem Band = Buy Signal
        elif bb_position < 0.4:
            bb_score = 10
        elif bb_position > 0.8:
            bb_score = -20  # Nahe oberem Band = Sell Signal
        elif bb_position > 0.6:
            bb_score = -10
        else:
            bb_score = 0
        score += bb_score * 0.15
        details['BB'] = bb_score

        # === Volume Score (Gewicht: 10%) ===
        vol_ratio = indicators.get('Volume_Ratio', 1)
        # Hohes Volume bestätigt Trends
        vol_score = 0
        if vol_ratio > 1.5:
            vol_score = 10 if score > 0 else -10  # Verstärkt aktuellen Trend
        elif vol_ratio < 0.5:
            vol_score = -5 if score > 0 else 5  # Schwaches Volume = Umkehr möglich
        score += vol_score * 0.10
        details['Volume'] = vol_score

        # === Stochastic Score (Gewicht: 10%) ===
        stoch_k = indicators.get('STOCH_K', 50)
        stoch_d = indicators.get('STOCH_D', 50)
        if stoch_k < 20 and stoch_k > stoch_d:
            stoch_score = 15  # Überverkauft + Aufwärtskreuzung
        elif stoch_k > 80 and stoch_k < stoch_d:
            stoch_score = -15  # Überkauft + Abwärtskreuzung
        else:
            stoch_score = 0
        score += stoch_score * 0.10
        details['Stochastic'] = stoch_score

        return round(score, 2), details


class StrategyEngine:
    """Main strategy engine combining technical analysis with LLM signals."""

    def __init__(self):
        self.analyzer = TechnicalAnalyzer()
        self.fetcher = get_data_fetcher()
        self.ai_engine = get_ai_engine()
        self.news_fetcher = get_news_fetcher()

    def analyze_asset(self, asset, asset_type="CRYPTO", timeframe="1h"):
        """
        Full analysis of an asset.

        Args:
            asset: e.g. "BTCUSDT" or "AAPL"
            asset_type: "CRYPTO" or "STOCK"
            timeframe: "1h", "4h", "1d"

        Returns:
            Signal dict or None
        """
        # Load data
        if asset_type == "CRYPTO":
            df = self.fetcher.get_crypto_klines(asset, interval=timeframe, limit=100)
        else:
            interval_map = {"1h": "1h", "4h": "4h", "1d": "1d"}
            df = self.fetcher.get_stock_data(asset, days=90, interval=interval_map.get(timeframe, "1h"))

        if df is None or df.empty:
            return None

        # Calculate indicators
        df = self.analyzer.calculate_indicators(df)

        if df.empty:
            return None

        # Get latest values
        tech_indicators = self.analyzer.get_latest_indicators(df)

        if tech_indicators is None:
            return None

        # Calculate technical score
        tech_score, score_details = self.analyzer.get_technical_score(tech_indicators)

        if DEBUG_MODE:
            print_info(f"Technical indicators for {asset}:")
            print(f"  RSI: {tech_indicators['RSI']:.2f}")
            print(f"  MACD: {tech_indicators['MACD']:.4f}")
            print(f"  SMA20 vs SMA50: {tech_indicators['SMA_20']:.2f} vs {tech_indicators['SMA_50']:.2f}")
            print(f"  BB: [{tech_indicators['BB_lower']:.2f} - {tech_indicators['BB_upper']:.2f}]")
            print(f"  ADX: {tech_indicators['ADX']:.2f}")
            print(f"  Tech Score: {tech_score:+.1f}")

        # Add technical score to AI context
        tech_indicators['tech_score'] = tech_score
        tech_indicators['score_details'] = score_details

        # Fetch current news (stocks only)
        news_digest = None
        if asset_type == "STOCK":
            try:
                news_digest = self.news_fetcher.get_news_digest(asset)
                if DEBUG_MODE and news_digest:
                    print_info(f"News digest for {asset}: {len(news_digest)} chars")
            except Exception as e:
                if DEBUG_MODE:
                    print_warning(f"News for {asset} unavailable: {e}")

        # Ask AI for signal (with news context)
        ai_signal = self.ai_engine.analyze_market(asset, timeframe, tech_indicators, news_digest=news_digest)

        if not hasattr(self, 'last_raw_signals'):
            self.last_raw_signals = {}
        if ai_signal:
            self.last_raw_signals[asset] = ai_signal.copy()

        if ai_signal and ai_signal.get('confidence', 0) >= SIGNAL_CONFIDENCE_THRESHOLD:
            # Validate and enhance signal
            ai_signal = self._enhance_signal(ai_signal, tech_indicators)
            
            # Validate signal logic (SL/TP consistency)
            if self.validate_signal(ai_signal):
                return ai_signal
            else:
                if DEBUG_MODE:
                    print_warning(f"Signal for {asset} is logically invalid (SL/TP inconsistent), discarding.")
                return None
        else:
            if DEBUG_MODE and ai_signal:
                print_warning(f"Signal confidence too low: {ai_signal.get('confidence', 0)}")
            return None

    def _enhance_signal(self, signal, indicators):
        """Enhance signal with ATR-based Stop-Loss/Take-Profit calculations."""
        entry = signal.get('entry_price', indicators['close'])
        atr = indicators.get('ATR', entry * 0.02)

        if signal.get('signal') == 'BUY':
            # SL: 1.5x ATR below entry
            calculated_sl = entry - (1.5 * atr)
            # TP: 3x ATR above entry (R:R = 2:1)
            calculated_tp = entry + (3.0 * atr)
        elif signal.get('signal') == 'SELL':
            calculated_sl = entry + (1.5 * atr)
            calculated_tp = entry - (3.0 * atr)
        else:
            return signal

        # Use the better of AI-suggested or calculated values
        if signal.get('signal') == 'BUY':
            # SL: the higher (less risk)
            sl_ai = signal.get('stop_loss', 0)
            signal['stop_loss'] = max(calculated_sl, sl_ai) if sl_ai > 0 else calculated_sl

            # TP: the higher (more profit)
            tp_ai = signal.get('take_profit', 0)
            signal['take_profit'] = max(calculated_tp, tp_ai) if tp_ai > 0 else calculated_tp
        else:
            sl_ai = signal.get('stop_loss', float('inf'))
            signal['stop_loss'] = min(calculated_sl, sl_ai) if sl_ai < float('inf') else calculated_sl

            tp_ai = signal.get('take_profit', 0)
            signal['take_profit'] = min(calculated_tp, tp_ai) if tp_ai > 0 else calculated_tp

        # Calculate Risk/Reward ratio
        risk = abs(entry - signal['stop_loss'])
        reward = abs(signal['take_profit'] - entry)
        signal['risk_reward_ratio'] = round(reward / risk, 2) if risk > 0 else 0

        return signal

    def analyze_multiple(self, assets, asset_type="CRYPTO"):
        """Analyze multiple assets and return all valid signals."""
        signals = []

        for asset in assets:
            signal = self.analyze_asset(asset, asset_type=asset_type)
            if signal:
                signals.append(signal)

        # Sort by confidence
        signals.sort(key=lambda s: s.get('confidence', 0), reverse=True)
        return signals

    def calculate_position_size(self, portfolio_balance, risk_percent, entry_price, stop_loss, signal_type="BUY"):
        """
        Calculate position size based on risk management.
        Works for both LONG and SHORT trades.

        Args:
            portfolio_balance: available capital
            risk_percent: risk in % (e.g. 2.0 for 2%)
            entry_price: entry price
            stop_loss: stop loss price
            signal_type: "BUY" or "SELL"
        """
        if entry_price <= 0 or stop_loss <= 0:
            return 0

        # Risk amount
        risk_amount = portfolio_balance * (risk_percent / 100)

        # Price risk per unit (always positive)
        price_risk = abs(entry_price - stop_loss)

        if price_risk <= 0:
            return 0

        position_size = risk_amount / price_risk
        return position_size

    def validate_signal(self, signal):
        """Check whether a signal is valid and tradeable."""
        if not signal:
            return False

        required_fields = ['signal', 'confidence', 'entry_price', 'stop_loss', 'take_profit']
        for field in required_fields:
            if field not in signal:
                return False

        # Check logic
        if signal['signal'] == 'BUY':
            if signal['stop_loss'] >= signal['entry_price']:
                return False
            if signal['take_profit'] <= signal['entry_price']:
                return False

        if signal['signal'] == 'SELL':
            if signal['stop_loss'] <= signal['entry_price']:
                return False
            if signal['take_profit'] >= signal['entry_price']:
                return False

        # Confidence must be between 0 and 1
        if not (0 <= signal['confidence'] <= 1):
            return False

        return True


# Singleton
_strategy = None

def get_strategy_engine():
    global _strategy
    if _strategy is None:
        _strategy = StrategyEngine()
    return _strategy
