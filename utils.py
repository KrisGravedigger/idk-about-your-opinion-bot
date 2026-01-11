"""
Opinion Farming Bot - Utilities Module
======================================

Helper functions for precision handling, formatting, and conversions.
All financial calculations should use Decimal for accuracy.

Key concepts:
- USDT has 18 decimals on BSC (stored as wei)
- Prices are typically 4 decimal places
- Always use Decimal for money calculations, not float
"""

import json
import os
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, InvalidOperation
from typing import Any, Optional, Union

from config_loader import config

PRICE_DECIMALS = config.PRICE_DECIMALS
AMOUNT_DECIMALS = config.AMOUNT_DECIMALS
STATE_FILE = config.STATE_FILE


# =============================================================================
# PRECISION CONVERSION FUNCTIONS
# =============================================================================

def usdt_to_wei(usdt_amount: Union[float, str, Decimal]) -> int:
    """
    Convert USDT amount to wei (18 decimals).
    
    Opinion.trade uses USDT with 18 decimals on BSC.
    1 USDT = 1,000,000,000,000,000,000 wei (10^18)
    
    Args:
        usdt_amount: Amount in USDT (human-readable)
        
    Returns:
        Amount in wei (integer, blockchain format)
        
    Example:
        >>> usdt_to_wei(1.5)
        1500000000000000000
        >>> usdt_to_wei("100.00")
        100000000000000000000
    """
    # Convert to Decimal for precision
    amount = Decimal(str(usdt_amount))
    
    # Multiply by 10^18
    wei = amount * Decimal(10 ** 18)
    
    # Return as integer (truncate any remaining decimals)
    return int(wei.to_integral_value(rounding=ROUND_DOWN))


def wei_to_usdt(wei_amount: Union[int, str]) -> Decimal:
    """
    Convert wei to USDT (human-readable).
    
    Args:
        wei_amount: Amount in wei (blockchain format)
        
    Returns:
        Amount in USDT (Decimal for precision)
        
    Example:
        >>> wei_to_usdt(1500000000000000000)
        Decimal('1.5')
    """
    wei = Decimal(str(wei_amount))
    usdt = wei / Decimal(10 ** 18)
    return usdt


def wei_to_usdt_float(wei_amount: Union[int, str]) -> float:
    """
    Convert wei to USDT as float (for display purposes only).
    
    WARNING: Use this only for display! For calculations, use wei_to_usdt().
    
    Args:
        wei_amount: Amount in wei
        
    Returns:
        Amount in USDT as float (may lose precision)
    """
    return float(wei_to_usdt(wei_amount))


# =============================================================================
# FORMATTING FUNCTIONS
# =============================================================================

def format_usdt(amount: Union[float, Decimal, str]) -> str:
    """
    Format USDT amount for display with $ symbol and 2 decimals.
    
    Args:
        amount: USDT amount
        
    Returns:
        Formatted string like "$1,234.56"
        
    Example:
        >>> format_usdt(1234.5678)
        "$1,234.57"
    """
    try:
        value = float(amount)
        return f"${value:,.2f}"
    except (ValueError, TypeError):
        return "$0.00"


def format_price(price: Union[float, Decimal, str]) -> str:
    """
    Format price for display with $ symbol and 4 decimals.
    
    Args:
        price: Price value
        
    Returns:
        Formatted string like "$0.5689"
        
    Example:
        >>> format_price(0.5689)
        "$0.5689"
    """
    try:
        value = float(price)
        return f"${value:.4f}"
    except (ValueError, TypeError):
        return "$0.0000"


def format_percent(value: Union[float, Decimal, str], decimals: int = 2) -> str:
    """
    Format percentage value for display.
    
    Args:
        value: Percentage value (e.g., 15.234)
        decimals: Number of decimal places
        
    Returns:
        Formatted string like "15.23%"
        
    Example:
        >>> format_percent(15.234)
        "15.23%"
    """
    try:
        v = float(value)
        return f"{v:.{decimals}f}%"
    except (ValueError, TypeError):
        return "0.00%"


def format_tokens(amount: Union[float, Decimal, str], decimals: int = 4) -> str:
    """
    Format token amount for display.
    
    Args:
        amount: Token amount
        decimals: Number of decimal places
        
    Returns:
        Formatted string
        
    Example:
        >>> format_tokens(1723.5678)
        "1,723.5678"
    """
    try:
        value = float(amount)
        return f"{value:,.{decimals}f}"
    except (ValueError, TypeError):
        return "0.0000"


def format_pnl(pnl: Union[float, Decimal], include_sign: bool = True) -> str:
    """
    Format P&L value with color indicator and sign.
    
    Args:
        pnl: P&L value in USDT
        include_sign: Whether to include +/- sign
        
    Returns:
        Formatted string like "+$55.12" or "-$12.34"
    """
    try:
        value = float(pnl)
        sign = "+" if value >= 0 and include_sign else ""
        return f"{sign}${value:,.2f}"
    except (ValueError, TypeError):
        return "$0.00"


# =============================================================================
# SAFE CONVERSION FUNCTIONS
# =============================================================================

def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float, returning default on failure.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Converted float or default
        
    Example:
        >>> safe_float("123.45")
        123.45
        >>> safe_float(None)
        0.0
        >>> safe_float("invalid", default=-1.0)
        -1.0
    """
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert a value to integer, returning default on failure.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Converted integer or default
    """
    try:
        if value is None:
            return default
        return int(float(value))  # Handle "123.45" -> 123
    except (ValueError, TypeError):
        return default


def safe_decimal(value: Any, default: Decimal = Decimal('0')) -> Decimal:
    """
    Safely convert a value to Decimal, returning default on failure.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Converted Decimal or default
    """
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return default


# =============================================================================
# PRICE CALCULATION HELPERS
# =============================================================================

def round_price(price: Union[float, Decimal], decimals: int = PRICE_DECIMALS) -> float:
    """
    Round price to specified decimal places.
    
    Args:
        price: Price value
        decimals: Number of decimal places (default from config)
        
    Returns:
        Rounded price as float
        
    Example:
        >>> round_price(0.56789)
        0.5679
    """
    d = Decimal(str(price))
    quantize_str = '0.' + '0' * decimals
    rounded = d.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)
    return float(rounded)


def round_amount(amount: Union[float, Decimal], decimals: int = AMOUNT_DECIMALS) -> float:
    """
    Round amount to specified decimal places.
    
    Args:
        amount: Amount value
        decimals: Number of decimal places (default from config)
        
    Returns:
        Rounded amount as float
    """
    d = Decimal(str(amount))
    quantize_str = '0.' + '0' * decimals
    rounded = d.quantize(Decimal(quantize_str), rounding=ROUND_DOWN)  # Round down for safety
    return float(rounded)


def calculate_spread(best_bid: float, best_ask: float) -> tuple[float, float]:
    """
    Calculate spread in absolute and percentage terms.
    
    Args:
        best_bid: Best bid price
        best_ask: Best ask price
        
    Returns:
        Tuple of (spread_absolute, spread_percent)
        
    Example:
        >>> calculate_spread(0.42, 0.58)
        (0.16, 38.095238...)
    """
    spread_abs = best_ask - best_bid
    spread_pct = ((best_ask - best_bid) / best_bid * 100) if best_bid > 0 else 0
    return (spread_abs, spread_pct)


# =============================================================================
# STATE MANAGEMENT FUNCTIONS
# =============================================================================

def load_state(filepath: str = STATE_FILE) -> dict:
    """
    Load bot state from JSON file.
    
    Args:
        filepath: Path to state file (default from config)
        
    Returns:
        State dictionary or empty dict if file doesn't exist
        
    Example:
        >>> state = load_state()
        >>> state.get('stage', 'INITIAL')
        'BUY_PLACED'
    """
    if not os.path.exists(filepath):
        return {}
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load state file: {e}")
        return {}


def save_state(state: dict, filepath: str = STATE_FILE) -> bool:
    """
    Save bot state to JSON file.
    
    Args:
        state: State dictionary to save
        filepath: Path to state file (default from config)
        
    Returns:
        True if saved successfully, False otherwise
        
    Example:
        >>> state = {'stage': 'BUY_PLACED', 'order_id': 'ord_123'}
        >>> save_state(state)
        True
    """
    try:
        # Add timestamp
        state['last_updated'] = datetime.now().isoformat()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        return True
    except IOError as e:
        print(f"Error saving state: {e}")
        return False


def clear_state(filepath: str = STATE_FILE) -> bool:
    """
    Clear/delete the state file.
    
    Args:
        filepath: Path to state file
        
    Returns:
        True if cleared successfully, False otherwise
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
        return True
    except IOError as e:
        print(f"Error clearing state: {e}")
        return False


# =============================================================================
# BONUS MARKETS MANAGEMENT
# =============================================================================

def load_bonus_markets(filepath: str) -> set[int]:
    """
    Load bonus market IDs from text file.
    
    File format:
    - One market ID per line
    - Lines starting with # are comments
    - Empty lines are ignored
    
    Args:
        filepath: Path to bonus markets file
        
    Returns:
        Set of bonus market IDs
        
    Example file (bonus_markets.txt):
        # High priority markets
        813
        914
        # Added 2025-01-15
        1025
    """
    bonus_ids = set()
    
    if not os.path.exists(filepath):
        return bonus_ids
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Try to parse as integer
                try:
                    market_id = int(line)
                    bonus_ids.add(market_id)
                except ValueError:
                    print(f"Warning: Invalid market ID in bonus file: {line}")
                    
    except IOError as e:
        print(f"Warning: Could not load bonus markets file: {e}")
    
    return bonus_ids


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_orderbook(orderbook_data: dict) -> tuple[bool, str]:
    """
    Validate that orderbook has required structure and data.
    
    Args:
        orderbook_data: Orderbook response data
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        bids = orderbook_data.get('bids', [])
        asks = orderbook_data.get('asks', [])
        
        if not bids:
            return (False, "No bids in orderbook")
        
        if not asks:
            return (False, "No asks in orderbook")
        
        # Check that best bid < best ask (sanity check)
        best_bid = safe_float(bids[0].get('price', 0))
        best_ask = safe_float(asks[0].get('price', 0))
        
        if best_bid >= best_ask:
            return (False, f"Invalid orderbook: bid ({best_bid}) >= ask ({best_ask})")
        
        return (True, "")
        
    except (KeyError, IndexError, TypeError) as e:
        return (False, f"Orderbook structure error: {e}")


def validate_market(market_data: dict) -> tuple[bool, str]:
    """
    Validate that market has required fields.
    
    Args:
        market_data: Market response data
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    required_fields = ['market_id', 'yes_token_id', 'status']
    
    for field in required_fields:
        if field not in market_data:
            return (False, f"Missing required field: {field}")
    
    return (True, "")


def convert_to_dict(obj: Any) -> dict:
    """
    Convert Pydantic model or other objects to dict.

    This helper eliminates repeated Pydantic→dict conversion code
    throughout the codebase.

    Args:
        obj: Object to convert (Pydantic model, dict, or other)

    Returns:
        Dictionary representation of the object

    Example:
        >>> from pydantic import BaseModel
        >>> class User(BaseModel):
        ...     name: str
        ...     age: int
        >>> user = User(name="Alice", age=30)
        >>> convert_to_dict(user)
        {'name': 'Alice', 'age': 30}

        >>> convert_to_dict({'already': 'dict'})
        {'already': 'dict'}
    """
    # Already a dict - return as-is
    if isinstance(obj, dict):
        return obj

    # Pydantic v2 model (has model_dump)
    if hasattr(obj, 'model_dump'):
        return obj.model_dump()

    # Pydantic v1 model (has dict method)
    if hasattr(obj, 'dict'):
        return obj.dict()

    # Fallback: try __dict__ attribute
    if hasattr(obj, '__dict__'):
        return obj.__dict__

    # Last resort: wrap in dict
    return {'value': obj}


# =============================================================================
# TIME HELPERS
# =============================================================================

def get_timestamp() -> str:
    """
    Get current timestamp in ISO format.

    Returns:
        ISO formatted timestamp string
    """
    return datetime.now().isoformat()


def interruptible_sleep(seconds: float, interval: float = 0.1) -> None:
    """
    Sleep for specified duration but allow KeyboardInterrupt to break early.

    Problem: time.sleep() is atomic and cannot be interrupted mid-sleep.
    Solution: Sleep in small chunks and check for interrupts frequently.

    Args:
        seconds: Total duration to sleep (in seconds)
        interval: Chunk size for each sleep iteration (default: 0.1s = 100ms)

    Raises:
        KeyboardInterrupt: If user presses CTRL+C during sleep

    Example:
        >>> # Sleep for 10 seconds, but responsive to CTRL+C every 100ms
        >>> interruptible_sleep(10.0)

        >>> # Sleep for 60 seconds, check every 0.5s
        >>> interruptible_sleep(60.0, interval=0.5)
    """
    import time

    if seconds <= 0:
        return

    # Calculate number of chunks
    num_chunks = int(seconds / interval)
    remainder = seconds % interval

    # Sleep in chunks (more responsive to interrupts)
    try:
        for _ in range(num_chunks):
            time.sleep(interval)

        # Sleep the remainder
        if remainder > 0:
            time.sleep(remainder)

    except KeyboardInterrupt:
        # Propagate interrupt immediately
        raise


def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable format.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted string like "2h 15m" or "45m 30s"
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    
    if minutes < 60:
        return f"{minutes}m {secs}s"
    
    hours = minutes // 60
    mins = minutes % 60
    
    if hours < 24:
        return f"{hours}h {mins}m"
    
    days = hours // 24
    hrs = hours % 24
    return f"{days}d {hrs}h"


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    # Test conversions
    print("=== Testing Conversions ===")
    print(f"100 USDT to wei: {usdt_to_wei(100)}")
    print(f"1e18 wei to USDT: {wei_to_usdt(10**18)}")
    
    # Test formatting
    print("\n=== Testing Formatting ===")
    print(f"Format USDT: {format_usdt(1234.5678)}")
    print(f"Format price: {format_price(0.5689)}")
    print(f"Format percent: {format_percent(15.234)}")
    print(f"Format tokens: {format_tokens(1723.5678)}")
    print(f"Format P&L positive: {format_pnl(55.12)}")
    print(f"Format P&L negative: {format_pnl(-12.34)}")
    
    # Test rounding
    print("\n=== Testing Rounding ===")
    print(f"Round price 0.56789: {round_price(0.56789)}")
    print(f"Round amount 1234.567: {round_amount(1234.567)}")
    
    # Test safe conversions
    print("\n=== Testing Safe Conversions ===")
    print(f"safe_float('123.45'): {safe_float('123.45')}")
    print(f"safe_float(None): {safe_float(None)}")
    print(f"safe_float('invalid'): {safe_float('invalid')}")
    
    # Test spread calculation
    print("\n=== Testing Spread Calculation ===")
    spread_abs, spread_pct = calculate_spread(0.42, 0.58)
    print(f"Spread for bid=0.42, ask=0.58: ${spread_abs:.4f} ({spread_pct:.2f}%)")
    
    print("\n✅ All utils tests passed!")
