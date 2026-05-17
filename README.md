# AI Trading Bot

Automated trading bot that uses a local LLM (via Ollama) together with technical analysis to generate trading signals. Supports paper trading with simulated slippage and transaction costs.

## Features

- **Local AI analysis** using Ollama (Mistral, DeepSeek, etc.) – no cloud APIs required
- **Technical indicators** – RSI, MACD, Bollinger Bands, ADX, Stochastic, OBV
- **News sentiment** via Finnhub for real-time financial news context
- **Realistic paper trading** with configurable bid-ask spread and commission simulation
- **Web dashboard** for live portfolio monitoring, trade history, and signal overview
- **Telegram alerts** for trade notifications
- **Alpaca integration** for broker-connected paper trading (optional)
- **Backtesting** engine to validate strategies on historical data

## Architecture

```
main.py            CLI interface
dashboard.py       Flask web dashboard (localhost:5000)
ai_engine.py       Ollama/LLM integration
strategy.py        Technical analysis and signal generation
portfolio.py       Portfolio management with slippage simulation
data_fetcher.py    Market data (Yahoo Finance, Binance, Alpaca)
news_fetcher.py    Financial news (Finnhub)
alpaca_broker.py   Alpaca paper trading API
telegram_alerts.py Telegram notifications
config.py          Central configuration (.env based)
```

## Getting Started

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai/) with a model installed (e.g. `mistral:latest`)

### Installation

```bash
git clone https://github.com/Marco-Preinfalk/Trading-Bot.git
cd Trading-Bot

pip install -r requirements.txt

ollama pull mistral:latest

cp .env.example .env
# edit .env with your values
```

### Running

```bash
# CLI
python main.py

# Web dashboard
python dashboard.py
# then open http://localhost:5000
```

## Configuration

All settings are managed via `.env`. See [.env.example](.env.example) for all available options.

| Variable | Description | Default |
|---|---|---|
| `OLLAMA_MODEL` | LLM model for analysis | `mistral:latest` |
| `TRADING_MODE` | STOCKS, CRYPTO, or HYBRID | `STOCKS` |
| `INITIAL_BALANCE` | Starting capital (USD) | `10000` |
| `RISK_PER_TRADE` | Max risk per trade (%) | `2.0` |
| `MAX_POSITIONS` | Max concurrent positions | `5` |
| `SLIPPAGE_PERCENT` | Simulated bid-ask spread (%) | `0.05` |
| `COMMISSION_PER_TRADE` | Broker fee per trade (%) | `0.10` |

### Optional API keys

| Service | Purpose | Registration |
|---|---|---|
| Finnhub | Financial news | [finnhub.io](https://finnhub.io/register) (free) |
| Telegram | Trade alerts | [@BotFather](https://t.me/BotFather) |
| Alpaca | Paper trading broker | [alpaca.markets](https://alpaca.markets) (free) |

## Slippage and Transaction Costs

To avoid unrealistic zero-cost trades, entry and exit prices are adjusted by a configurable spread, and a commission is deducted on each round-trip. With default settings this adds up to roughly 0.30% per trade.

## Disclaimer

This is a learning project, not financial advice. The generated signals are experimental. Do not use real money without your own due diligence.

## License

MIT
