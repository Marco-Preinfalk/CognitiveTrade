"""Shared utility functions: colored output, logging, JSON parsing, retry decorator."""
import json
import re
import time
import functools
import logging
from colorama import Fore, Style, init

init(autoreset=True)


logger = logging.getLogger("CognitiveTrade")
logger.setLevel(logging.DEBUG)


_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
logger.addHandler(_ch)


def print_success(message):
    print(f"{Fore.GREEN}[OK] {message}{Style.RESET_ALL}")
    logger.debug(message)

def print_error(message):
    print(f"{Fore.RED}[ERROR] {message}{Style.RESET_ALL}")
    logger.debug(message)

def print_warning(message):
    print(f"{Fore.YELLOW}[WARN] {message}{Style.RESET_ALL}")
    logger.debug(message)

def print_info(message):
    print(f"{Fore.CYAN}[INFO] {message}{Style.RESET_ALL}")
    logger.debug(message)

def print_divider():
    print(f"{Fore.MAGENTA}{'='*60}{Style.RESET_ALL}")

def format_currency(amount, symbol="$"):
    if amount is None:
        return f"{symbol}0.00"
    return f"{symbol}{amount:,.2f}"

def format_percent(value):
    if value is None:
        value = 0
    color = Fore.GREEN if value >= 0 else Fore.RED
    return f"{color}{value:+.2f}%{Style.RESET_ALL}"

def parse_ai_response(response_text):
    """Extract JSON from LLM response text. Handles raw JSON, markdown code blocks,
    embedded JSON, and model <think> tags."""
    if not response_text or not response_text.strip():
        return None

    cleaned = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    code_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', cleaned, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Fallback: brace-matching to find outermost JSON object
    brace_depth = 0
    json_start = -1
    for i, char in enumerate(cleaned):
        if char == '{':
            if brace_depth == 0:
                json_start = i
            brace_depth += 1
        elif char == '}':
            brace_depth -= 1
            if brace_depth == 0 and json_start != -1:
                try:
                    return json.loads(cleaned[json_start:i + 1])
                except json.JSONDecodeError:
                    json_start = -1  # Versuche nächstes JSON-Objekt

    return None

def format_trade_signal(signal):
    if not signal:
        return "NO SIGNALS"

    signal_type = signal.get('signal', 'UNKNOWN')
    if signal_type == 'BUY':
        signal_color = Fore.GREEN
    elif signal_type == 'SELL':
        signal_color = Fore.RED
    else:
        signal_color = Fore.YELLOW

    output = "\n"
    output += f"  Signal: {signal_color}{signal_type}{Style.RESET_ALL}\n"
    output += f"  Confidence: {format_percent(signal.get('confidence', 0) * 100)}\n"
    output += f"  Reason: {signal.get('reason', 'N/A')}\n"
    output += f"  Entry: {format_currency(signal.get('entry_price', 0))}\n"
    output += f"  SL: {format_currency(signal.get('stop_loss', 0))}\n"
    output += f"  TP: {format_currency(signal.get('take_profit', 0))}\n"

    # Risk/Reward Ratio
    entry = signal.get('entry_price', 0)
    sl = signal.get('stop_loss', 0)
    tp = signal.get('take_profit', 0)
    if entry and sl and tp and entry != sl:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        rr_ratio = reward / risk if risk > 0 else 0
        output += f"  R/R: {Fore.CYAN}{rr_ratio:.2f}{Style.RESET_ALL}\n"

    return output


def retry_on_failure(max_retries=3, delay=1.0, backoff=2.0, exceptions=(Exception,)):
    """Decorator for automatic retry on failure with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"Retry {attempt + 1}/{max_retries} für {func.__name__}: {e}")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"Alle {max_retries} Retries fehlgeschlagen für {func.__name__}: {e}")
            raise last_exception
        return wrapper
    return decorator
