"""Central configuration - loads all settings from .env file."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv nicht installiert, nutze Defaults

# ===== OLLAMA / DEEPSEEK KONFIGURATION =====
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:latest")  # oder "deepseek-r1:8b"
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.3"))

# ===== TELEGRAM ALERTS (OPTIONAL) =====
# 1. Bot erstellen bei @BotFather auf Telegram
# 2. Token kopieren und in .env eintragen
# 3. Chat ID: Schreib @userinfobot ein Message, bekommst Chat ID
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "False").lower() in ("true", "1", "yes")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ===== ALPACA PAPER TRADING (OPTIONAL) =====
# 1. Gehe zu https://alpaca.markets
# 2. Erstelle kostenlosen Paper Trading Account
# 3. Generiere API Keys
# 4. Trage in .env ein
ALPACA_ENABLED = os.getenv("ALPACA_ENABLED", "False").lower() in ("true", "1", "yes")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "dein_alpaca_api_key")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "dein_alpaca_secret_key")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "True").lower() in ("true", "1", "yes")

# ===== TRADING KONFIGURATION =====
# Available assets: Crypto (Binance) or Stocks (Yahoo)
TRADING_MODE = os.getenv("TRADING_MODE", "STOCKS")  # "CRYPTO", "STOCKS", oder "HYBRID"

# Krypto-Paare for Backtesting/Paper Trading (Binance)
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
    # ETFs (diversifiziert)
    "SPY",       # S&P 500 ETF
    "QQQ",       # Nasdaq 100 ETF
    # Volatil (gut for kurzfristige Signale)
    "TSLA",      # Tesla
]

# ===== PORTFOLIO KONFIGURATION =====
INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "10000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "2.0"))  # Immer in Prozent: 2.0 = 2% des Portfolios pro Trade
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "5"))

# ===== AI TRADING SIGNAL THRESHOLDS =====
SIGNAL_CONFIDENCE_THRESHOLD = float(os.getenv("SIGNAL_CONFIDENCE_THRESHOLD", "0.55"))
BUY_SIGNAL_STRENGTH = "STRONG"      # "STRONG", "MODERATE", oder "WEAK"
SELL_SIGNAL_STRENGTH = "MODERATE"   # Verkauf auch bei moderaten Signals

# ===== RISIKO MANAGEMENT =====
STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "2.0"))
TAKE_PROFIT_PERCENT = float(os.getenv("TAKE_PROFIT_PERCENT", "5.0"))
TRAILING_STOP = os.getenv("TRAILING_STOP", "False").lower() in ("true", "1", "yes")

# ===== SLIPPAGE & TRANSAKTIONSKOSTEN =====
# Simulierter Bid-Ask-Spread (0.05% = 5 Basispunkte pro Seite)
SLIPPAGE_PERCENT = float(os.getenv("SLIPPAGE_PERCENT", "0.05"))
# Broker-Kommission pro Trade (0.10% = 10 Basispunkte)
COMMISSION_PER_TRADE = float(os.getenv("COMMISSION_PER_TRADE", "0.10"))

# ===== BACKTESTING KONFIGURATION =====
BACKTEST_DAYS = int(os.getenv("BACKTEST_DAYS", "60"))
BACKTEST_INTERVAL = os.getenv("BACKTEST_INTERVAL", "1h")

# ===== LOGGING & DEBUG =====
DEBUG_MODE = os.getenv("DEBUG_MODE", "True").lower() in ("true", "1", "yes")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ===== BINANCE API (Public/Kostenlos) =====
# The public API does not require an API key!
BINANCE_API_ENDPOINT = "https://api.binance.com/api/v3"

# ===== FINNHUB NEWS API =====
# Kostenloser Key: https://finnhub.io/register (60 Calls/Minute)
# Liefert News von Reuters, MarketWatch, Bloomberg, CNBC etc.
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
