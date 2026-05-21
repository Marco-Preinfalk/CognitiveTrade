"""Central configuration - loads all settings from .env file."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, using defaults

# ===== OLLAMA / LLM CONFIGURATION =====
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:latest")  # or "deepseek-r1:8b"
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.3"))

# ===== TELEGRAM ALERTS (OPTIONAL) =====
# 1. Create a bot using @BotFather on Telegram
# 2. Copy the token and add it to .env
# 3. Message @userinfobot to get your Chat ID
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "False").lower() in ("true", "1", "yes")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ===== ALPACA PAPER TRADING (OPTIONAL) =====
# 1. Go to https://alpaca.markets
# 2. Create a free Paper Trading account
# 3. Generate API Keys
# 4. Add them to .env
ALPACA_ENABLED = os.getenv("ALPACA_ENABLED", "False").lower() in ("true", "1", "yes")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "your_alpaca_api_key")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "your_alpaca_secret_key")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "True").lower() in ("true", "1", "yes")

# ===== TRADING CONFIGURATION =====
# Available assets: Crypto (Binance) or Stocks (Yahoo)
TRADING_MODE = os.getenv("TRADING_MODE", "STOCKS")  # "CRYPTO", "STOCKS", or "HYBRID"

# Crypto pairs for backtesting/paper trading (Binance)
CRYPTO_PAIRS = [
    "BTCUSDT",   # Bitcoin
    "ETHUSDT",   # Ethereum
    "BNBUSDT",   # Binance Coin
]

# Stocks for trading - diversified across sectors
STOCKS = [
    # Tech
    "AAPL",      # Apple
    "MSFT",      # Microsoft
    "GOOGL",     # Google
    "NVDA",      # NVIDIA
    "META",      # Meta/Facebook
    "AMD",       # AMD
    # Finance
    "JPM",       # JPMorgan
    "BAC",       # Bank of America
    "GS",        # Goldman Sachs
    # Healthcare
    "JNJ",       # Johnson & Johnson
    "UNH",       # UnitedHealth
    "PFE",       # Pfizer
    # Energy
    "XOM",       # ExxonMobil
    "CVX",       # Chevron
    # Consumer
    "AMZN",      # Amazon
    "WMT",       # Walmart
    "KO",        # Coca-Cola
    # ETFs (diversified)
    "SPY",       # S&P 500 ETF
    "QQQ",       # Nasdaq 100 ETF
    # Volatile (good for short-term signals)
    "TSLA",      # Tesla
]

# ===== PORTFOLIO CONFIGURATION =====
INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "10000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "2.0"))  # Always in percentage: 2.0 = 2% of portfolio per trade
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "5"))

# ===== AI TRADING SIGNAL THRESHOLDS =====
SIGNAL_CONFIDENCE_THRESHOLD = float(os.getenv("SIGNAL_CONFIDENCE_THRESHOLD", "0.55"))
BUY_SIGNAL_STRENGTH = "STRONG"      # "STRONG", "MODERATE", or "WEAK"
SELL_SIGNAL_STRENGTH = "MODERATE"   # Sell even on moderate signals

# ===== RISK MANAGEMENT =====
STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "2.0"))
TAKE_PROFIT_PERCENT = float(os.getenv("TAKE_PROFIT_PERCENT", "5.0"))
TRAILING_STOP = os.getenv("TRAILING_STOP", "False").lower() in ("true", "1", "yes")

# ===== SLIPPAGE & TRANSACTION COSTS =====
# Simulated Bid-Ask Spread (0.05% = 5 basis points per side)
SLIPPAGE_PERCENT = float(os.getenv("SLIPPAGE_PERCENT", "0.05"))
# Broker commission per trade (0.10% = 10 basis points)
COMMISSION_PER_TRADE = float(os.getenv("COMMISSION_PER_TRADE", "0.10"))

# ===== BACKTESTING CONFIGURATION =====
BACKTEST_DAYS = int(os.getenv("BACKTEST_DAYS", "60"))
BACKTEST_INTERVAL = os.getenv("BACKTEST_INTERVAL", "1h")

# ===== LOGGING & DEBUG =====
DEBUG_MODE = os.getenv("DEBUG_MODE", "True").lower() in ("true", "1", "yes")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ===== BINANCE API (Public/Free) =====
# The public API does not require an API key!
BINANCE_API_ENDPOINT = "https://api.binance.com/api/v3"

# ===== FINNHUB NEWS API =====
# Free key: https://finnhub.io/register (60 calls/minute)
# Provides news from Reuters, MarketWatch, Bloomberg, CNBC etc.
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
