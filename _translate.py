"""Batch translate remaining German strings to English."""
import re

replacements = {
    # data_fetcher.py
    "Alpaca Daten-Provider nicht verfügbar": "Alpaca data provider unavailable",
    "Alpaca Daten-Provider verbunden": "Alpaca data provider connected",
    "Wie viele Tage zurück": "How many days back",
    "Alpaca Bars für": "Alpaca bars for",
    "nicht verfügbar": "unavailable",
    "Alpaca Preis für": "Alpaca price for",
    "Cache abgelaufen, aufräumen": "Cache expired, cleaning up",
    "Kann Crypto-Preis für": "Cannot load crypto price for",
    "nicht laden:": "unavailable:",
    "Kann Stock-Preis für": "Cannot load stock price for",
    "nicht laden (Yahoo)": "unavailable (Yahoo)",
    "Keine Daten für": "No data for",
    "gefunden (Yahoo)": "found (Yahoo)",
    "Prüfe ob alle nötigen Spalten vorhanden sind": "Check required columns",
    "Fehlende Spalten für": "Missing columns for",
    "Kann Info für": "Cannot load info for",
    "# Singleton für einfache Nutzung": "# Singleton",
    "Daten geladen (Alpaca)": "data loaded (Alpaca)",
    "Kerzen": "bars",
    "Daten geladen:": "data loaded:",
    "Binance API Fehler": "Binance API error",
    "Fehler beim Laden von": "Error loading",
    "von Yahoo:": "from Yahoo:",
    "# Standardize columns": "# Standardize columns",  # keep
    "Hole Kursdaten von Alpaca Data API": "Get price data from Alpaca Data API",
    "DataFrame mit OHLCV Daten oder None": "DataFrame with OHLCV data or None",
    
    # news_fetcher.py
    "Hole aktuelle Nachrichten für ein Unternehmen von Finnhub.": "Fetch current news for a company from Finnhub.",
    "Wie viele Tage zurück?": "How many days back?",
    "Keine News für": "No news for",
    "gefunden": "found",
    "News-Artikel für": "news articles for",
    "geladen": "loaded",
    "Finnhub API Key ungültig!": "Finnhub API key is invalid!",
    "Finnhub API Key nicht konfiguriert! News-Feature deaktiviert.": "Finnhub API key not configured. News disabled.",
    "Finnhub News-API verbunden": "Finnhub news API connected",
    "Timeout beim Laden der News für": "Timeout loading news for",
    "Fehler beim Laden der News für": "Error loading news for",
    "Erstellt einen kompakten Text-Digest der aktuellen News für den AI-Prompt.": "Create a compact text digest of current news for the AI prompt.",
    "String mit formatiertem News-Digest für den Prompt": "Formatted news digest string for the prompt",
    "Keine aktuellen Nachrichten verfügbar.": "No current news available.",
    "Hole den allgemeinen Markt-Sentiment für ein Symbol.": "Get general market sentiment for a symbol.",
    "Nutzt Finnhub's Basic Financials als Ergänzung.": "Uses Finnhub Basic Financials as supplement.",
    "Sentiment-Daten für": "Sentiment data for",
    "nicht verfügbar:": "unavailable:",
    "Aktien-Symbol, z.B.": "Stock symbol, e.g.",
    "Aktien-Symbol": "Stock symbol",
    "Dict mit sentiment-relevanten Daten oder None": "Dict with sentiment-relevant data or None",
    "Berechne Score:": "Calculate score:",
    "Finnhub API Fehler: Status": "Finnhub API error: status",
    
    # backtest.py
    "Wie viele Tage zurück?": "How many days back?",
    "Zeitrahmen für Kerzen": "Timeframe for candles",
    "Starte Backtest für": "Starting backtest for",
    "Tage, Interval": "days, interval",
    "Keine Daten für Backtest von": "No data for backtest of",
    "Nicht genug Daten nach Indikator-Berechnung für": "Not enough data after indicator calculation for",
    "Prüfe ob SL/TP den Trade geschlossen hat": "Check if SL/TP closed the trade",
    "Durchschnittlicher Return": "Average return",
    "Gesamttrades": "Total trades",
    "Dict mit Backtest-Ergebnissen": "Dict with backtest results",
    
    # ml_strategy.py
    "Lade": "Loading",
    "Tage Daten für": "days of data for",
    "Keine Daten für": "No data for",
    "Keine Indikatoren berechnet": "No indicators calculated",
    "% für Test Set": "% for test set",
    "Trainiere ML Modell für": "Training ML model for",
    "Predict Signal für Asset basierend auf ML": "Predict signal for asset based on ML",
    "Prepare historische Daten zum Training": "Prepare historical data for training",
    "Trainiere ML Modell auf historischen Daten": "Train ML model on historical data",
    "Lade letzte 50 Kerzen": "Load latest candles",
    "Fehler beim Speichern": "Error saving",
    "ML Model '": "ML model '",
    "' geladen": "' loaded",
    "' gespeichert": "' saved",
    "Kann Model nicht laden": "Cannot load model",
    "Trainings-Samples vorbereitet": "training samples prepared",
    "Training abgeschlossen": "Training complete",
    "Model nicht trainiert! Nutze train() zuerst.": "Model not trained! Run train() first.",
    
    # ai_engine.py
    "Verfügbare Modelle": "Available models",
    "Keine Modelle in Ollama gefunden. Bitte `ollama pull mistral:latest` ausführen.": "No models found in Ollama. Please run `ollama pull mistral:latest`.",
    "Sende Prompt an": "Sending prompt to",
    "für": "for",
    "Erzwingt JSON-Output bei unterstützten Modellen": "Force JSON output for supported models",
    "Erhöht für langsamere Modelle": "Increased for slower models",
    "Kein gültiges Signal zurück von": "No valid signal from",
    
    # dashboard.py
    "überprüfe auch, ob Alpaca-Positionen geschlossen wurden, die wir lokal noch offen haben": "check if Alpaca positions were closed that are still open locally",
    "Wir müssen sie auch lokal schließen": "Must close locally too",
    "bei Alpaca geschlossen, schließe lokal": "closed at Alpaca, closing locally",
    "Schließe lokale Positionen, die bei Alpaca fehlen": "Close local positions that are missing at Alpaca",
    "Lokale Position": "Local position",
    "existiert nicht bei Alpaca, schließe": "not found at Alpaca, closing",
    "Prüfe ob ein Symbol im Wash-Trade Cooldown ist": "Check if a symbol is in wash-trade cooldown",
    "Prüfe ob Alpaca die Position wirklich hat": "Check if Alpaca actually holds the position",
    "nicht bei Alpaca vorhanden, überspringe Close-Order": "not found at Alpaca, skipping close order",
    "Wash-Trade Cooldown prüfen": "Wash-trade cooldown check",
    "Signal cachen für Dashboard-API": "Cache signal for dashboard API",
    "Ungültiger Entry/SL Preis": "Invalid entry/SL price",
    "Bereits geöffnet (Race Condition vermieden)": "Already opened (race condition avoided)",
    "API: Portfolio zurücksetzen und mit Alpaca synchronisieren": "API: Reset portfolio and sync with Alpaca",
    "Portfolio zurückgesetzt auf": "Portfolio reset to",
    "Alpaca Verbindung fehlgeschlagen - nutze lokales Portfolio": "Alpaca connection failed, using local portfolio",
    "Alpaca konnte nicht geladen werden": "Alpaca could not be loaded",
    
    # alpaca_broker.py
    "True für Paper Trading, False für Live": "True for paper trading, False for live",
    "Storniere zuerst alle hängenden Orders": "Cancel all pending orders first",
    "Portfolio Value über Zeit": "Portfolio value over time",
    
    # config.py
    "# Verfügbare Assets: Krypto (BINANCE) oder Aktien (YAHOO)": "# Available assets: Crypto (Binance) or Stocks (Yahoo)",
    "# Krypto-Paare für Backtesting/Paper Trading (Binance)": "# Crypto pairs for backtesting/paper trading (Binance)",
    "# Aktien für Trading - diversifiziert über verschiedene Sektoren": "# Stocks for trading - diversified across sectors",
    "# Volatil (gut für kurzfristige Signale)": "# Volatile (good for short-term signals)",
    "# Die public API benötigt keinen API Key!": "# The public API does not require an API key!",
}

files = [
    'data_fetcher.py', 'news_fetcher.py', 'backtest.py', 'ml_strategy.py',
    'ai_engine.py', 'dashboard.py', 'alpaca_broker.py', 'config.py'
]

for filepath in files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    changed = False
    for german, english in replacements.items():
        if german in content:
            content = content.replace(german, english)
            changed = True
    
    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated: {filepath}")
    else:
        print(f"No changes: {filepath}")
