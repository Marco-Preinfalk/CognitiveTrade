"""Telegram notifications for trades and signals using async I/O."""

import asyncio
import threading
from telegram import Bot
from telegram.error import TelegramError
from config import DEBUG_MODE
from utils import print_success, print_error, print_warning, print_info

class TelegramAlerter:

    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot = None
        self.connected = False
        
        # Thread for async tasks
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

        self._check_connection()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _check_connection(self):
        async def verify():
            try:
                self.bot = Bot(token=self.bot_token)
                await self.bot.get_me()
                self.connected = True
                print_success("Telegram bot connected")
            except Exception as e:
                print_error(f"Telegram error: {str(e)}")
                self.connected = False
        
        asyncio.run_coroutine_threadsafe(verify(), self.loop)

    def _send_async_message(self, text):
        if not self.connected or not self.bot:
            return False

        async def send():
            try:
                await self.bot.send_message(chat_id=self.chat_id, text=text)
            except Exception as e:
                if DEBUG_MODE:
                    print_error(f"Failed to send Telegram message: {str(e)}")
        
        asyncio.run_coroutine_threadsafe(send(), self.loop)
        return True

    def send_signal_alert(self, asset, signal_data):
        if not self.connected:
            return False

        message = f"""
📊 NEW TRADING SIGNAL 📊

Asset: {asset}
Signal: {signal_data.get('signal', 'UNKNOWN')}
Confidence: {signal_data.get('confidence', 0)*100:.1f}%

Entry: ${signal_data.get('entry_price', 0):.2f}
Stop Loss: ${signal_data.get('stop_loss', 0):.2f}
Take Profit: ${signal_data.get('take_profit', 0):.2f}
R/R Ratio: {signal_data.get('risk_reward_ratio', 0):.2f}

Reason: {signal_data.get('reason', 'N/A')}
"""
        self._send_async_message(message)
        if DEBUG_MODE:
            print_info(f"Telegram alert sent: {asset}")
        return True

    def send_trade_open_alert(self, trade_id, asset, signal_type, entry_price, size):
        if not self.connected:
            return False

        message = f"""
✅ TRADE OPENED ✅

Trade ID: {trade_id}
Asset: {asset}
Type: {signal_type}
Entry: ${entry_price:.2f}
Size: {size:.4f}

Position is now active and being monitored.
"""
        self._send_async_message(message)
        if DEBUG_MODE:
            print_info(f"Telegram Trade Open: {trade_id}")
        return True

    def send_trade_close_alert(self, trade_id, asset, pnl, pnl_percent, reason="Manual"):
        if not self.connected:
            return False

        emoji = "🟢" if pnl >= 0 else "🔴"
        message = f"""
{emoji} TRADE CLOSED {emoji}

Trade ID: {trade_id}
Asset: {asset}
P&L: ${pnl:.2f} ({pnl_percent:+.2f}%)
Reason: {reason}

{'🎉 Profit!' if pnl >= 0 else '⚠️ Loss'}
"""
        self._send_async_message(message)
        if DEBUG_MODE:
            print_info(f"Telegram Trade Close: {trade_id}")
        return True

    def send_portfolio_update(self, stats):
        if not self.connected:
            return False

        message = f"""
📈 PORTFOLIO UPDATE 📈

Balance: ${stats.get('current_balance', 0):.2f}
Total Equity: ${stats.get('total_equity', 0):.2f}
P&L: ${stats.get('total_pnl', 0):.2f} ({stats.get('return_percent', 0):+.2f}%)
Unrealized: ${stats.get('unrealized_pnl', 0):.2f}

Trades: {stats.get('total_trades', 0)}
Winners: {stats.get('winning_trades', 0)}
Losers: {stats.get('losing_trades', 0)}
Win Rate: {stats.get('win_rate', 0):.1f}%

Profit Factor: {stats.get('profit_factor', 0):.2f}
Max Drawdown: -{stats.get('max_drawdown_pct', 0):.1f}%

Open Positions: {stats.get('open_positions', 0)}
"""
        self._send_async_message(message)
        if DEBUG_MODE:
            print_info("Telegram portfolio update sent")
        return True

    def send_error_alert(self, title, error_message):
        if not self.connected:
            return False

        message = f"""
🚨 ERROR 🚨

{title}
{error_message}

Please check!
"""
        self._send_async_message(message)
        print_error("Error alert sent")
        return True

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)


# Singleton
_alerter = None

def get_telegram_alerter(bot_token=None, chat_id=None):
    """Get or create Telegram Alerter"""
    global _alerter
    if _alerter is None and bot_token and chat_id:
        _alerter = TelegramAlerter(bot_token, chat_id)
    return _alerter
