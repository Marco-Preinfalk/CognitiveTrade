"""Alpaca paper trading API integration."""

from alpaca_trade_api import REST
import pandas as pd
from datetime import datetime, timedelta
from utils import print_success, print_error, print_warning, print_info, format_currency

class AlpacaBroker:
    """Connection to the Alpaca Broker API."""
    
    def __init__(self, api_key, secret_key, paper=True):
        """
        Args:
            api_key: Alpaca API Key
            secret_key: Alpaca Secret Key
            paper: True for Paper Trading, False for Live
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.connected = False
        self.api = None
        
        try:
            self.api = REST(
                key_id=api_key,
                secret_key=secret_key,
                base_url='https://paper-api.alpaca.markets' if paper else 'https://api.alpaca.markets'
            )
            
            # Test connection
            account = self.api.get_account()
            self.connected = True
            
            print_success(f"Alpaca {'Paper' if paper else 'Live'} Trading connected!")
            print_info(f"   Account: {account.account_number}")
            print_info(f"   Portfolio Value: {format_currency(float(account.portfolio_value))}")
            
        except Exception as e:
            print_error(f"Alpaca connection failed: {str(e)}")
            self.connected = False
    
    def get_account_info(self):
        """Fetch account information."""
        try:
            account = self.api.get_account()
            return {
                'cash': float(account.cash),
                'portfolio_value': float(account.portfolio_value),
                'equity': float(account.equity),
                'buying_power': float(account.buying_power),
                'multiplier': float(account.multiplier),
            }
        except Exception as e:
            print_error(f"Error fetching account info: {str(e)}")
            return None
    
    def get_positions(self):
        """Fetch all open positions."""
        try:
            positions = self.api.list_positions()
            result = {}
            for position in positions:
                result[position.symbol] = {
                    'qty': float(position.qty),
                    'avg_entry_price': float(position.avg_entry_price),
                    'current_price': float(position.current_price),
                    'market_value': float(position.market_value),
                    'unrealized_pl': float(position.unrealized_pl),
                    'unrealized_plpc': float(position.unrealized_plpc),
                }
            return result
        except Exception as e:
            print_error(f"Error fetching positions: {str(e)}")
            return {}

    def close_all_positions(self):
        """Close ALL open positions at Alpaca."""
        try:
            self.api.close_all_positions()
            print_success("All Alpaca positions closed")
            return True
        except Exception as e:
            print_error(f"Error closing all positions: {str(e)}")
            return False

    def close_position(self, symbol):
        """Close a single position at Alpaca."""
        try:
            # Cancel all pending orders first (TP/SL), otherwise "insufficient qty" error
            open_orders = self.api.list_orders(status="open", symbols=[symbol])
            for o in open_orders:
                self.api.cancel_order(o.id)
                
            self.api.close_position(symbol)
            print_success(f"Position {symbol} closed")
            return True
        except Exception as e:
            print_error(f"Error closing {symbol}: {str(e)}")
            return False
    
    def submit_order(self, symbol, qty, side, order_type='market', time_in_force='day', limit_price=None):
        """
        Submit an order to Alpaca.

        Args:
            symbol: e.g. "AAPL"
            qty: quantity
            side: "buy" or "sell"
            order_type: "market" or "limit"
            time_in_force: "day", "gtc" (good-til-cancelled)
            limit_price: price for limit orders

        Returns:
            Order dict or None
        """
        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type=order_type,
                time_in_force=time_in_force,
                limit_price=limit_price
            )
            
            print_success(f"Order submitted: {side.upper()} {qty} {symbol} @ {order_type}")
            return {
                'order_id': order.id,
                'symbol': order.symbol,
                'qty': float(order.qty),
                'side': order.side,
                'status': order.status,
                'filled_qty': float(order.filled_qty),
                'filled_avg_price': order.filled_avg_price,
            }
        except Exception as e:
            print_error(f"Error submitting order: {str(e)}")
            return None
    
    def get_order_status(self, order_id):
        """Fetch order status."""
        try:
            order = self.api.get_order(order_id)
            return {
                'id': order.id,
                'status': order.status,
                'filled_qty': float(order.filled_qty),
                'filled_avg_price': order.filled_avg_price,
            }
        except Exception as e:
            print_error(f"Error fetching order: {str(e)}")
            return None
    
    def cancel_order(self, order_id):
        """Cancel an order."""
        try:
            self.api.cancel_order(order_id)
            print_success(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            print_error(f"Error cancelling order: {str(e)}")
            return False
    
    def cancel_all_orders(self):
        """Cancel all open orders."""
        try:
            self.api.cancel_all_orders()
            print_success("All open orders cancelled")
            return True
        except Exception as e:
            print_error(f"Error cancelling all orders: {str(e)}")
            return False
    
    def get_portfolio_history(self, period='1M'):
        """
        Fetch portfolio history.

        Args:
            period: "1D", "1W", "1M", "3M", "1A"

        Returns:
            Portfolio value over time.
        """
        try:
            portfolio_history = self.api.get_portfolio_history(period=period)
            
            return {
                'timestamps': portfolio_history.timestamp,
                'equity': portfolio_history.equity,
                'profit_loss': portfolio_history.profit_loss,
                'profit_loss_pct': portfolio_history.profit_loss_pct,
            }
        except Exception as e:
            print_error(f"Error loading History: {str(e)}")
            return None


# Singleton
_broker = None

def get_alpaca_broker(api_key=None, secret_key=None, paper=True):
    """Get or create Alpaca Broker connection"""
    global _broker
    if _broker is None and api_key and secret_key:
        _broker = AlpacaBroker(api_key, secret_key, paper=paper)
    return _broker
