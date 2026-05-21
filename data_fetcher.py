"""Market data fetching from Alpaca, Yahoo Finance, and Binance with caching."""

import requests
import pandas as pd
import yfinance as yf
import time
from datetime import datetime, timedelta
from config import (BINANCE_API_ENDPOINT, BACKTEST_INTERVAL, DEBUG_MODE,
                    ALPACA_ENABLED, ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER)
from utils import print_success, print_error, print_warning, print_info, retry_on_failure


class AlpacaDataProvider:
    """Alpaca as primary data source for stock price data."""

    def __init__(self):
        self.connected = False
        self.api = None

        if not ALPACA_ENABLED:
            return

        try:
            from alpaca_trade_api import REST
            self.api = REST(
                key_id=ALPACA_API_KEY,
                secret_key=ALPACA_SECRET_KEY,
                base_url='https://paper-api.alpaca.markets' if ALPACA_PAPER else 'https://api.alpaca.markets'
            )
            # Quick connection test
            self.api.get_account()
            self.connected = True
            print_success("Alpaca data provider connected")
        except Exception as e:
            print_warning(f"Alpaca data provider unavailable: {e}")
            self.connected = False

    def get_stock_bars(self, symbol, days=90, timeframe='1Hour'):
        """
        Get price data from the Alpaca Data API.

        Args:
            symbol: e.g. "AAPL"
            days: how many days back
            timeframe: '1Min', '5Min', '15Min', '1Hour', '1Day'

        Returns:
            DataFrame with OHLCV data or None.
        """
        if not self.connected:
            return None

        try:
            from alpaca_trade_api.rest import TimeFrame

            # Timeframe-Mapping
            tf_map = {
                '1m': TimeFrame.Minute,
                '5m': TimeFrame(5, 'Min'),
                '15m': TimeFrame(15, 'Min'),
                '1h': TimeFrame.Hour,
                '1Hour': TimeFrame.Hour,
                '4h': TimeFrame(4, 'Hour'),
                '1d': TimeFrame.Day,
                '1Day': TimeFrame.Day,
            }

            tf = tf_map.get(timeframe, TimeFrame.Hour)

            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')

            bars = self.api.get_bars(
                symbol,
                tf,
                start=start_date,
                end=end_date,
                adjustment='raw',
                feed='iex'
            )

            if not bars:
                return None

            # Convert to DataFrame
            data = []
            for bar in bars:
                data.append({
                    'timestamp': bar.t,
                    'open': float(bar.o),
                    'high': float(bar.h),
                    'low': float(bar.l),
                    'close': float(bar.c),
                    'volume': float(bar.v),
                })

            if not data:
                return None

            df = pd.DataFrame(data)

            if DEBUG_MODE:
                print_success(f"{symbol} data loaded (Alpaca): {len(df)} bars")

            return df

        except Exception as e:
            if DEBUG_MODE:
                print_warning(f"Alpaca bars for {symbol} unavailable: {e}")
            return None

    def get_current_price(self, symbol):
        if not self.connected:
            return None

        try:
            trade = self.api.get_latest_trade(symbol, feed='iex')
            if trade:
                return float(trade.price)
        except Exception:
            pass

        # Fallback: last bar
        try:
            from alpaca_trade_api.rest import TimeFrame
            bars = self.api.get_bars(symbol, TimeFrame.Minute, limit=1, feed='iex')
            if bars:
                return float(bars[-1].c)
        except Exception as e:
            if DEBUG_MODE:
                print_warning(f"Alpaca price for {symbol} unavailable: {e}")
        return None


class DataFetcher:
    def __init__(self):
        self.binance_endpoint = BINANCE_API_ENDPOINT
        self.cache = {}
        self.cache_expiry = {}
        self.default_cache_ttl = 60

        self.alpaca = AlpacaDataProvider()

    def _get_cached(self, key):
        if key in self.cache and key in self.cache_expiry:
            if time.time() < self.cache_expiry[key]:
                return self.cache[key]
            else:
                # Cache expired, cleaning up
                del self.cache[key]
                del self.cache_expiry[key]
        return None

    def _set_cached(self, key, value, ttl=None):
        if ttl is None:
            ttl = self.default_cache_ttl
        self.cache[key] = value
        self.cache_expiry[key] = time.time() + ttl



    @retry_on_failure(max_retries=2, delay=1.0, exceptions=(requests.RequestException,))
    def get_crypto_klines(self, symbol, interval="1h", limit=100):
        """
        Fetch OHLCV bar data from Binance.

        Args:
            symbol: e.g. "BTCUSDT"
            interval: "1m", "5m", "15m", "1h", "4h", "1d"
            limit: number of bars (max 1000)

        Returns:
            DataFrame with OHLCV data.
        """
        cache_key = f"klines_{symbol}_{interval}_{limit}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            url = f"{self.binance_endpoint}/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": min(limit, 1000)
            }

            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()

                # Parse to DataFrame
                df = pd.DataFrame(data, columns=[
                    'open_time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'trades',
                    'taker_buy_base', 'taker_buy_quote', 'ignore'
                ])


                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col])

                df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
                df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

                if DEBUG_MODE:
                    print_success(f"{symbol} data loaded: {len(df)} bars")

                self._set_cached(cache_key, df, ttl=120)
                return df
            else:
                print_error(f"Binance API error: {response.status_code}")
                return None
        except requests.RequestException:
            raise
        except Exception as e:
            print_error(f"Error loading {symbol}: {str(e)}")
            return None

    def get_current_price(self, symbol):
        """
        Get current price — Alpaca first, then Yahoo as fallback.

        Args:
            symbol: e.g. "BTCUSDT" (crypto) or "AAPL" (stock)

        Returns:
            float price or None.
        """
        cache_key = f"price_{symbol}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Crypto symbols end in USDT/BTC/ETH
        if symbol.endswith("USDT") or symbol.endswith("BTC") or symbol.endswith("ETH"):
            price = self._get_crypto_price(symbol)
        else:
            # Try Alpaca first, then Yahoo fallback
            price = None
            if self.alpaca.connected:
                price = self.alpaca.get_current_price(symbol)
                if price and DEBUG_MODE:
                    pass  # No spam on every price fetch

            if price is None:
                price = self._get_stock_price_yahoo(symbol)

        if price is not None:
            self._set_cached(cache_key, price, ttl=30)
        return price

    def _get_crypto_price(self, symbol):
        try:
            url = f"{self.binance_endpoint}/ticker/price"
            params = {"symbol": symbol}
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                return float(response.json()["price"])
        except Exception as e:
            print_warning(f"Cannot fetch crypto price for {symbol}: {str(e)}")
        return None

    def _get_stock_price_yahoo(self, symbol):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
            # Fallback: ticker.info
            info = ticker.info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if price:
                return float(price)
        except Exception as e:
            print_warning(f"Cannot fetch stock price for {symbol} (Yahoo): {str(e)}")
        return None

    def get_crypto_24h_stats(self, symbol):
        cache_key = f"stats_24h_{symbol}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            url = f"{self.binance_endpoint}/ticker/24hr"
            params = {"symbol": symbol}
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                result = {
                    "price": float(data["lastPrice"]),
                    "change": float(data["priceChangePercent"]),
                    "high": float(data["highPrice"]),
                    "low": float(data["lowPrice"]),
                    "volume": float(data["volume"])
                }
                self._set_cached(cache_key, result, ttl=60)
                return result
        except Exception as e:
            print_warning(f"Cannot fetch 24h stats: {str(e)}")
        return None

    # ===== Stock Data (Alpaca primary, Yahoo fallback) =====

    @retry_on_failure(max_retries=2, delay=1.0, exceptions=(Exception,))
    def get_stock_data(self, symbol, days=60, interval="1h"):
        """
        Fetch stock data — Alpaca first, Yahoo Finance as fallback.

        Args:
            symbol: e.g. "AAPL"
            days: how many days back
            interval: "1m", "5m", "15m", "1h", "1d"

        Returns:
            DataFrame with OHLCV data.
        """
        cache_key = f"stock_{symbol}_{days}_{interval}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached



        # Try Alpaca first
        df = None
        if self.alpaca.connected:
            df = self.alpaca.get_stock_bars(symbol, days=days, timeframe=interval)

        # Fallback: Yahoo Finance
        if df is None:
            df = self._get_stock_data_yahoo(symbol, days=days, interval=interval)

        if df is not None and not df.empty:
            self._set_cached(cache_key, df, ttl=300)

        return df

    def _get_stock_data_yahoo(self, symbol, days=60, interval="1h"):
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # Yahoo limits: 1h max 730d, 1m max 7d
            if interval in ("1m", "2m", "5m") and days > 7:
                days = 7
                start_date = end_date - timedelta(days=days)
            elif interval == "15m" and days > 60:
                days = 60
                start_date = end_date - timedelta(days=days)

            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date, interval=interval)

            if df.empty:
                print_warning(f"No data for {symbol} found (Yahoo)")
                return None

            # Standardize columns
            df.columns = [col.lower() for col in df.columns]

            # Check required columns
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            available = [c for c in required_cols if c in df.columns]
            if len(available) < len(required_cols):
                print_warning(f"Missing columns for {symbol}: {set(required_cols) - set(available)}")
                return None

            df = df[required_cols]
            df['timestamp'] = df.index
            df = df.reset_index(drop=True)

            if DEBUG_MODE:
                print_success(f"{symbol} data loaded (Yahoo fallback): {len(df)} bars")

            return df
        except Exception as e:
            print_error(f"Error loading {symbol} from Yahoo: {str(e)}")
            raise

    def get_stock_info(self, symbol):
        cache_key = f"info_{symbol}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            result = {
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "change": info.get("regularMarketChangePercent"),
                "high": info.get("fiftyTwoWeekHigh"),
                "low": info.get("fiftyTwoWeekLow"),
                "market_cap": info.get("marketCap"),
                "name": info.get("shortName", symbol),
                "pe_ratio": info.get("trailingPE"),
                "dividend_yield": info.get("dividendYield"),
            }
            self._set_cached(cache_key, result, ttl=300)
            return result
        except Exception as e:
            print_warning(f"Cannot fetch info for {symbol}: {str(e)}")
        return None

    def clear_cache(self):
        self.cache.clear()
        self.cache_expiry.clear()


# Singleton
_fetcher = None

def get_data_fetcher():
    global _fetcher
    if _fetcher is None:
        _fetcher = DataFetcher()
    return _fetcher
