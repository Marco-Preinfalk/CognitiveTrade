"""Finnhub news API integration for financial news and sentiment data."""

import requests
import time
from datetime import datetime, timedelta
from config import FINNHUB_API_KEY, DEBUG_MODE
from utils import print_success, print_error, print_warning, print_info


class NewsFetcher:

    def __init__(self):
        self.api_key = FINNHUB_API_KEY
        self.base_url = "https://finnhub.io/api/v1"
        self.cache = {}
        self.cache_expiry = {}
        self.cache_ttl = 300  # 5 minute cache
        self.enabled = bool(self.api_key and self.api_key != "dein_key_hier")

        if not self.enabled:
            print_warning("Finnhub API key not configured. News disabled.")
            print_info("Get a free key: https://finnhub.io/register")
        else:
            print_success("Finnhub news API connected")

    def _get_cached(self, key):
        if key in self.cache and key in self.cache_expiry:
            if time.time() < self.cache_expiry[key]:
                return self.cache[key]
            else:
                del self.cache[key]
                del self.cache_expiry[key]
        return None

    def _set_cached(self, key, value, ttl=None):
        if ttl is None:
            ttl = self.cache_ttl
        self.cache[key] = value
        self.cache_expiry[key] = time.time() + ttl

    def get_company_news(self, symbol, days_back=3, max_articles=10):
        """
        Fetch current news for a company from Finnhub.

        Sources: Reuters, MarketWatch, Seeking Alpha, Bloomberg, CNBC, etc.

        Args:
            symbol: Stock symbol, e.g. "AAPL"
            days_back: how many days back
            max_articles: maximum number of articles

        Returns:
            List of dicts with: headline, summary, source, url, datetime, image.
        """
        if not self.enabled:
            return []

        cache_key = f"news_{symbol}_{days_back}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

            url = f"{self.base_url}/company-news"
            params = {
                "symbol": symbol,
                "from": start_date,
                "to": end_date,
                "token": self.api_key,
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                articles = response.json()

                if not articles:
                    if DEBUG_MODE:
                        print_info(f"No news for {symbol} found")
                    return []


                articles = articles[:max_articles]


                cleaned = []
                for article in articles:
                    cleaned.append({
                        "headline": article.get("headline", ""),
                        "summary": article.get("summary", "")[:300],
                        "source": article.get("source", "Unknown"),
                        "url": article.get("url", ""),
                        "datetime": datetime.fromtimestamp(article.get("datetime", 0)).isoformat()
                            if article.get("datetime") else None,
                        "image": article.get("image", ""),
                        "category": article.get("category", "general"),
                        "related": article.get("related", symbol),
                    })

                if DEBUG_MODE:
                    print_success(f"{len(cleaned)} news articles for {symbol} loaded")

                self._set_cached(cache_key, cleaned)
                return cleaned
            elif response.status_code == 401:
                print_error("Finnhub API key is invalid!")
                self.enabled = False
                return []
            elif response.status_code == 429:
                print_warning("Finnhub rate limit — waiting...")
                time.sleep(2)
                return []
            else:
                print_error(f"Finnhub API error: status {response.status_code}")
                return []

        except requests.exceptions.Timeout:
            print_warning(f"Timeout loading news for {symbol}")
            return []
        except Exception as e:
            print_error(f"Error loading news for {symbol}: {str(e)}")
            return []

    def get_news_digest(self, symbol, max_articles=5):
        """
        Create a compact text digest of current news for the AI prompt.

        Args:
            symbol: Stock symbol

        Returns:
            Formatted news digest string for the prompt
        """
        articles = self.get_company_news(symbol, days_back=3, max_articles=max_articles)

        if not articles:
            return "No current news available."

        lines = []
        for article in articles:
            source = article.get("source", "Unknown")
            headline = article.get("headline", "")
            dt = article.get("datetime", "")

            # Relative time
            time_ago = ""
            if dt:
                try:
                    article_time = datetime.fromisoformat(dt)
                    delta = datetime.now() - article_time
                    hours = delta.total_seconds() / 3600
                    if hours < 1:
                        time_ago = f"{int(delta.total_seconds() / 60)}m ago"
                    elif hours < 24:
                        time_ago = f"{int(hours)}h ago"
                    else:
                        time_ago = f"{int(hours / 24)}d ago"
                except (ValueError, TypeError):
                    time_ago = ""

            time_str = f" ({time_ago})" if time_ago else ""
            lines.append(f"- [{source}] {headline}{time_str}")

        return "\n".join(lines)

    def get_market_sentiment(self, symbol):
        """
        Get general market sentiment for a symbol.
        Uses Finnhub Basic Financials as supplement.

        Returns:
            Dict with sentiment-relevant data or None
        """
        if not self.enabled:
            return None

        cache_key = f"sentiment_{symbol}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            # Recommendation trends from Finnhub
            url = f"{self.base_url}/stock/recommendation"
            params = {"symbol": symbol, "token": self.api_key}
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data:
                    latest = data[0]  # Latest recommendation
                    result = {
                        "period": latest.get("period", ""),
                        "strong_buy": latest.get("strongBuy", 0),
                        "buy": latest.get("buy", 0),
                        "hold": latest.get("hold", 0),
                        "sell": latest.get("sell", 0),
                        "strong_sell": latest.get("strongSell", 0),
                    }
                    # Calculate score: +2 strongBuy, +1 buy, 0 hold, -1 sell, -2 strongSell
                    total_analysts = result["strong_buy"] + result["buy"] + result["hold"] + result["sell"] + result["strong_sell"]
                    if total_analysts > 0:
                        score = (
                            result["strong_buy"] * 2 + result["buy"] * 1 +
                            result["sell"] * -1 + result["strong_sell"] * -2
                        ) / total_analysts
                        result["consensus_score"] = round(score, 2)
                        if score > 0.5:
                            result["consensus"] = "BULLISH"
                        elif score < -0.5:
                            result["consensus"] = "BEARISH"
                        else:
                            result["consensus"] = "NEUTRAL"
                    else:
                        result["consensus"] = "UNKNOWN"
                        result["consensus_score"] = 0

                    self._set_cached(cache_key, result, ttl=3600)  # 1h Cache
                    return result
        except Exception as e:
            if DEBUG_MODE:
                print_warning(f"Sentiment data for {symbol} unavailable: {str(e)}")
        return None


# Singleton
_news_fetcher = None


def get_news_fetcher():
    global _news_fetcher
    if _news_fetcher is None:
        _news_fetcher = NewsFetcher()
    return _news_fetcher
