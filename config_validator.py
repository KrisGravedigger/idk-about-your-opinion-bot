"""
Configuration Validation Utilities
===================================

Validators for all configuration fields.
Used by GUI for real-time validation and configuration testing.

Returns validation results with:
- is_valid: bool
- message: str (error message if invalid)
- warning: Optional[str] (warning if valid but not recommended)
"""

from typing import Tuple, Optional, List, Dict, Any
import re


def validate_capital_mode(value: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate capital mode selection.

    Returns:
        (is_valid, error_message, warning_message)
    """
    valid_modes = ['fixed', 'percentage']
    if value.lower() not in valid_modes:
        return False, f"Must be one of: {', '.join(valid_modes)}", None
    return True, None, None


def validate_positive_number(value: Any, field_name: str = "Value",
                            min_val: float = 0.0, max_val: float = None) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate positive numeric value with optional range."""
    try:
        num = float(value)
    except (ValueError, TypeError):
        return False, f"{field_name} must be a number", None

    if num < min_val:
        return False, f"{field_name} must be >= {min_val}", None

    if max_val is not None and num > max_val:
        return False, f"{field_name} must be <= {max_val}", None

    return True, None, None


def validate_percentage(value: Any, min_val: float = 0.0, max_val: float = 100.0) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate percentage value (0-100)."""
    try:
        num = float(value)
    except (ValueError, TypeError):
        return False, "Must be a number", None

    if num < min_val or num > max_val:
        return False, f"Must be between {min_val} and {max_val}", None

    # Warning if extreme values
    warning = None
    if num < 10 and min_val == 0:
        warning = "Very low percentage - bot may underutilize capital"
    elif num > 95:
        warning = "Very high percentage - leaves little buffer"

    return True, None, warning


def validate_scoring_profile(value: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate scoring profile selection."""
    valid_profiles = ['production_farming', 'test_quick_fill', 'balanced', 'liquidity_farming', 'custom']
    if value not in valid_profiles:
        return False, f"Must be one of: {', '.join(valid_profiles)}", None
    return True, None, None


def validate_scoring_weights(weights: Dict[str, float]) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate custom scoring weights.

    Weights should sum to approximately 1.0.
    """
    if not isinstance(weights, dict):
        return False, "Weights must be a dictionary", None

    # Check each weight is valid
    for key, value in weights.items():
        try:
            val = float(value)
            if val < 0 or val > 1:
                return False, f"Weight '{key}' must be between 0.0 and 1.0", None
        except (ValueError, TypeError):
            return False, f"Weight '{key}' must be a number", None

    # Check sum
    total = sum(float(v) for v in weights.values())

    if abs(total - 1.0) > 0.1:
        return False, f"Weights must sum to ~1.0 (current: {total:.2f})", None

    warning = None
    if abs(total - 1.0) > 0.01:
        warning = f"Weights sum to {total:.2f} (ideally should be 1.00)"

    return True, None, warning


def validate_spread_thresholds(threshold1: float, threshold2: float, threshold3: float) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate spread threshold progression."""
    try:
        t1, t2, t3 = float(threshold1), float(threshold2), float(threshold3)
    except (ValueError, TypeError):
        return False, "All thresholds must be numbers", None

    if not (t1 < t2 < t3):
        return False, "Thresholds must be in ascending order (tiny < small < medium)", None

    if t1 < 0 or t2 < 0 or t3 < 0:
        return False, "Thresholds must be positive", None

    return True, None, None


def validate_probability_range(min_prob: float, max_prob: float) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate probability range (0.0-1.0)."""
    try:
        min_p, max_p = float(min_prob), float(max_prob)
    except (ValueError, TypeError):
        return False, "Probabilities must be numbers", None

    if min_p < 0 or min_p > 1:
        return False, "Minimum probability must be between 0.0 and 1.0", None

    if max_p < 0 or max_p > 1:
        return False, "Maximum probability must be between 0.0 and 1.0", None

    if min_p >= max_p:
        return False, "Minimum must be less than maximum", None

    warning = None
    if max_p - min_p < 0.1:
        warning = "Very narrow probability range - may limit opportunities"

    return True, None, warning


def validate_hours(value: Any, allow_none: bool = True) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate hours value (positive number or None)."""
    if value is None and allow_none:
        return True, None, None

    try:
        hours = float(value)
    except (ValueError, TypeError):
        return False, "Must be a positive number or leave empty", None

    if hours <= 0:
        return False, "Hours must be positive", None

    warning = None
    if hours < 1:
        warning = "Very short timeframe - may limit opportunities"
    elif hours > 720:  # 30 days
        warning = "Very long timeframe - markets may be too far in future"

    return True, None, warning


def validate_log_level(value: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate log level."""
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    if value.upper() not in valid_levels:
        return False, f"Must be one of: {', '.join(valid_levels)}", None
    return True, None, None


def validate_api_key(value: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate API key format."""
    if not value or not value.strip():
        return False, "API key is required", None

    # Basic validation - should be non-empty string
    if len(value.strip()) < 10:
        return False, "API key seems too short", None

    return True, None, None


def validate_private_key(value: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate private key format."""
    if not value or not value.strip():
        return False, "Private key is required for trading", None

    key = value.strip()

    # Remove 0x prefix if present
    if key.startswith('0x'):
        key = key[2:]

    # Should be 64 hex characters
    if len(key) != 64:
        return False, "Private key must be 64 hex characters (with or without 0x prefix)", None

    # Check if valid hex
    if not re.match(r'^[0-9a-fA-F]{64}$', key):
        return False, "Private key must contain only hexadecimal characters", None

    return True, None, "⚠️ NEVER share your private key!"


def validate_wallet_address(value: str, allow_empty: bool = True) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate Ethereum wallet address."""
    if not value or not value.strip():
        if allow_empty:
            return True, None, "Empty address = READ-ONLY mode (no trading)"
        return False, "Wallet address is required", None

    addr = value.strip()

    # Should start with 0x
    if not addr.startswith('0x'):
        return False, "Address must start with 0x", None

    # Should be 42 characters (0x + 40 hex chars)
    if len(addr) != 42:
        return False, "Address must be 42 characters (0x + 40 hex digits)", None

    # Check if valid hex
    if not re.match(r'^0x[0-9a-fA-F]{40}$', addr):
        return False, "Address must contain only hexadecimal characters", None

    return True, None, None


def validate_url(value: str, field_name: str = "URL") -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate URL format."""
    if not value or not value.strip():
        return False, f"{field_name} is required", None

    url = value.strip()

    if not (url.startswith('http://') or url.startswith('https://')):
        return False, f"{field_name} must start with http:// or https://", None

    return True, None, None


def validate_telegram_token(value: str, allow_empty: bool = True) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate Telegram bot token format."""
    if not value or not value.strip():
        if allow_empty:
            return True, None, "Empty = Telegram notifications disabled"
        return False, "Telegram bot token is required", None

    # Basic format: should contain : separator
    if ':' not in value:
        return False, "Invalid token format (should be: 123456789:ABCdef...)", None

    return True, None, None


def validate_telegram_chat_id(value: str, allow_empty: bool = True) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate Telegram chat ID."""
    if not value or not value.strip():
        if allow_empty:
            return True, None, "Empty = Telegram notifications disabled"
        return False, "Telegram chat ID is required", None

    # Can be numeric or @username
    if not (value.strip().lstrip('-').isdigit() or value.strip().startswith('@')):
        return False, "Chat ID must be a number or @username", None

    return True, None, None


def validate_full_config(config_dict: dict) -> Tuple[bool, List[str], List[str]]:
    """
    Validate entire configuration.

    Args:
        config_dict: Configuration dictionary (lowercase keys)

    Returns:
        (is_valid, errors, warnings)
    """
    errors = []
    warnings = []

    # Capital Management
    if 'capital_mode' in config_dict:
        valid, err, warn = validate_capital_mode(config_dict['capital_mode'])
        if not valid:
            errors.append(f"Capital Mode: {err}")
        if warn:
            warnings.append(f"Capital Mode: {warn}")

    if config_dict.get('capital_mode') == 'fixed' and 'capital_amount_usdt' in config_dict:
        valid, err, warn = validate_positive_number(
            config_dict['capital_amount_usdt'],
            "Capital Amount",
            min_val=1.0
        )
        if not valid:
            errors.append(f"Capital Amount: {err}")
        if warn:
            warnings.append(f"Capital Amount: {warn}")

        # Check against minimum position size
        if config_dict['capital_amount_usdt'] < config_dict.get('min_position_size_usdt', 50):
            warnings.append(
                f"Capital Amount ({config_dict['capital_amount_usdt']}) is below "
                f"minimum position size ({config_dict.get('min_position_size_usdt', 50)})"
            )

    if 'capital_percentage' in config_dict:
        valid, err, warn = validate_percentage(config_dict['capital_percentage'])
        if not valid:
            errors.append(f"Capital Percentage: {err}")
        if warn:
            warnings.append(f"Capital Percentage: {warn}")

    # Trading Strategy
    if all(k in config_dict for k in ['spread_threshold_1', 'spread_threshold_2', 'spread_threshold_3']):
        valid, err, warn = validate_spread_thresholds(
            config_dict['spread_threshold_1'],
            config_dict['spread_threshold_2'],
            config_dict['spread_threshold_3']
        )
        if not valid:
            errors.append(f"Spread Thresholds: {err}")

    # Risk Management
    if 'stop_loss_trigger_percent' in config_dict:
        val = config_dict['stop_loss_trigger_percent']
        if val > 0:
            errors.append("Stop-Loss Trigger: Must be negative (e.g., -10 for -10%)")
        elif val < -50:
            warnings.append("Stop-Loss Trigger: Very aggressive stop-loss (<-50%)")

    # Probability Range
    if 'outcome_min_probability' in config_dict and 'outcome_max_probability' in config_dict:
        valid, err, warn = validate_probability_range(
            config_dict['outcome_min_probability'],
            config_dict['outcome_max_probability']
        )
        if not valid:
            errors.append(f"Probability Range: {err}")
        if warn:
            warnings.append(f"Probability Range: {warn}")

    # Hours validation
    if 'min_hours_until_close' in config_dict and config_dict['min_hours_until_close'] is not None:
        valid, err, warn = validate_hours(config_dict['min_hours_until_close'])
        if not valid:
            errors.append(f"Min Hours Until Close: {err}")
        if warn:
            warnings.append(f"Min Hours Until Close: {warn}")

    # Scoring weights (if custom profile)
    if config_dict.get('scoring_profile') == 'custom' and 'scoring_weights' in config_dict:
        valid, err, warn = validate_scoring_weights(config_dict['scoring_weights'])
        if not valid:
            errors.append(f"Scoring Weights: {err}")
        if warn:
            warnings.append(f"Scoring Weights: {warn}")

    # Check minimum balance vs capital
    if 'min_balance_to_continue_usdt' in config_dict and 'capital_amount_usdt' in config_dict:
        if config_dict['min_balance_to_continue_usdt'] > config_dict['capital_amount_usdt']:
            warnings.append(
                "Minimum Balance is higher than Capital Amount - bot may stop immediately"
            )

    return (len(errors) == 0, errors, warnings)


def validate_credentials(api_key: str, private_key: str, multi_sig_address: str = "") -> Tuple[bool, List[str], List[str]]:
    """
    Validate API credentials.

    Returns:
        (is_valid, errors, warnings)
    """
    errors = []
    warnings = []

    # API Key
    valid, err, warn = validate_api_key(api_key)
    if not valid:
        errors.append(f"API Key: {err}")
    if warn:
        warnings.append(f"API Key: {warn}")

    # Private Key
    valid, err, warn = validate_private_key(private_key)
    if not valid:
        errors.append(f"Private Key: {err}")
    if warn:
        warnings.append(f"Private Key: {warn}")

    # Multi-sig Address (optional)
    if multi_sig_address:
        valid, err, warn = validate_wallet_address(multi_sig_address, allow_empty=False)
        if not valid:
            errors.append(f"Multi-sig Address: {err}")
        if warn:
            warnings.append(f"Multi-sig Address: {warn}")
    else:
        warnings.append("Multi-sig Address: Empty - bot will run in READ-ONLY mode")

    return (len(errors) == 0, errors, warnings)
