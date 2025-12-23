"""
Opinion Farming Bot - Configuration Module
==========================================

All configurable parameters for the trading bot.
Modify these values to adjust bot behavior.

IMPORTANT: Sensitive credentials (API keys, private keys) should be stored
in .env file, NOT in this config file.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# API & BLOCKCHAIN CONFIGURATION
# =============================================================================

# Opinion.trade API endpoint
API_HOST = "https://proxy.opinion.trade:8443"

# BNB Chain (BSC) network settings
CHAIN_ID = 56  # BSC Mainnet
RPC_URL = os.getenv("RPC_URL", "https://bsc-dataseed.binance.org")

# Smart contract addresses (DO NOT MODIFY unless Opinion.trade updates them)
CONDITIONAL_TOKEN_ADDR = "0xAD1a38cEc043e70E83a3eC30443dB285ED10D774"
MULTISEND_ADDR = "0x998739BFdAAdde7C933B942a68053933098f9EDa"

# =============================================================================
# CREDENTIALS (loaded from .env file - NEVER hardcode these!)
# =============================================================================

# Your Opinion.trade API key
API_KEY = os.getenv("API_KEY", "")

# Your wallet's private key (for signing transactions)
# SECURITY WARNING: Never share or commit this value!
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")

# Your multi-sig wallet address (Gnosis Safe compatible)
# For regular EOA wallets: set to your wallet address
# For Gnosis Safe: set to Safe contract address
# Can be left empty for read-only mode (no trading)
_multi_sig_raw = os.getenv("MULTI_SIG_ADDRESS", "").strip()
MULTI_SIG_ADDRESS = _multi_sig_raw if _multi_sig_raw else None

# =============================================================================
# CAPITAL MANAGEMENT
# =============================================================================

# Total capital available for the bot (in USDT)
# This is the maximum amount the bot can deploy
TOTAL_CAPITAL_USDT = 15

# Percentage of total capital to allocate per market
# 100 = use all capital on one market at a time
# 50 = split capital across two markets (future feature)
CAPITAL_ALLOCATION_PERCENT = 90

# Automatically reinvest capital after closing a position?
# True = bot searches for next market after SELL fills
# False = bot exits after completing one full cycle
AUTO_REINVEST = True

# Capital management mode
# 'fixed' = use CAPITAL_AMOUNT_USDT for every position
# 'percentage' = use CAPITAL_PERCENTAGE of current balance
CAPITAL_MODE = 'percentage'           # 'fixed' | 'percentage'
CAPITAL_AMOUNT_USDT = 10.0           # Used when CAPITAL_MODE = 'fixed'
CAPITAL_PERCENTAGE = 90.0           # Used when CAPITAL_MODE = 'percentage' (1-100)

# Safety thresholds
MIN_BALANCE_TO_CONTINUE_USDT = 10.0   # Bot exits if balance drops below this

# Platform Constraints (Opinion.trade requirements)
MIN_POSITION_SIZE_USDT = 10.0         # Minimum order size allowed by platform
MIN_POSITION_FOR_POINTS_USDT = 10.0  # Minimum size to earn airdrop points
WARN_IF_BELOW_POINTS_THRESHOLD = True  # Log warning if position < 10 USDT

# =============================================================================
# BONUS MARKETS CONFIGURATION
# =============================================================================

# File containing bonus market IDs (one per line)
# Bonus markets earn extra airdrop points
BONUS_MARKETS_FILE = "bonus_markets.txt"

# Score multiplier for bonus markets
# Example: 2.0 means bonus markets score 2x higher than regular markets
BONUS_MULTIPLIER = 2.0

# =============================================================================
# PRICING STRATEGY - SIMPLE THRESHOLD-BASED
# =============================================================================

# Simple pricing based on spread size (in dollars, not percentages).
# We improve bid/ask by fixed amounts depending on how wide the spread is.

# Spread thresholds (in dollars)
SPREAD_THRESHOLD_1 = 0.20  # $0.00-$0.20 = tiny spread
SPREAD_THRESHOLD_2 = 0.50  # $0.21-$0.50 = small spread
SPREAD_THRESHOLD_3 = 1.00  # $0.51-$1.00 = medium spread
                           # > $1.00 = wide spread

# Improvement amounts (in dollars) for each threshold
# BUY: how much ABOVE best_bid to place order
# SELL: how much BELOW best_ask to place order
IMPROVEMENT_TINY = 0.00    # Join the queue (no improvement)
IMPROVEMENT_SMALL = 0.10   # $0.10 better than best
IMPROVEMENT_MEDIUM = 0.20  # $0.20 better than best
IMPROVEMENT_WIDE = 0.30    # $0.30 better than best

# Safety margin: minimum distance (in cents) from opposite side
# Prevents accidentally crossing the spread
SAFETY_MARGIN_CENTS = 0.001  # $0.001 minimum distance

# =============================================================================
# MARKET FILTERS
# =============================================================================

# Minimum number of orders required on each side of orderbook
# Markets with fewer orders are skipped (too illiquid)
MIN_ORDERBOOK_ORDERS = 1

# Time-based filters for BUY orders only
# Skip markets closing within this timeframe (hours)
# Set to None to disable filter
# Example: 30 = skip markets closing in < 30 hours
MIN_HOURS_UNTIL_CLOSE = 30

# Skip markets closing after this timeframe (hours)
# Set to None to disable filter
# Example: 720 = skip markets closing in > 720 hours (30 days)
# Use case: avoid very long-term markets if farming short-term
MAX_HOURS_UNTIL_CLOSE = None

# Orderbook balance filter for BUY orders only
# Skip markets where one side dominates too heavily
# Format: (min_percentage, max_percentage) for BID side volume
# Example: (20, 80) = skip if bids are <20% or >80% of total volume
# Set to None to disable filter
ORDERBOOK_BALANCE_RANGE = (20, 80)  # Skip if <20% or >80% bids

# =============================================================================
# TIMING / INTERVALS
# =============================================================================

# How often to scan for new markets (seconds)
# Used when searching for opportunities
MARKET_SCAN_INTERVAL_SECONDS = 9

# How often to check orderbook for competition (seconds)
# Used during competitive monitoring in Stage 5
ORDER_MONITOR_INTERVAL_SECONDS = 9

# How often to check if order is filled (seconds)
# Used during fill monitoring in Stage 3
FILL_CHECK_INTERVAL_SECONDS = 9

# =============================================================================
# LIQUIDITY MONITORING
# =============================================================================

# Automatically cancel orders if liquidity deteriorates significantly?
# True = cancel and find new market if conditions worsen
# False = let order sit even if liquidity drops
LIQUIDITY_AUTO_CANCEL = True

# Maximum bid price drop before considering liquidity deteriorated
# Example: 25% means if best bid drops >25% from initial, cancel order
LIQUIDITY_BID_DROP_THRESHOLD = 25.0

# Maximum spread percentage before considering liquidity deteriorated
# Example: 15% means if spread exceeds 15%, cancel order
LIQUIDITY_SPREAD_THRESHOLD = 15.0

# =============================================================================
# ORDER TIMEOUTS
# =============================================================================

# Maximum time to wait for BUY order to fill (hours)
# After this time, monitor will return 'timeout' status
BUY_ORDER_TIMEOUT_HOURS = 24

# Maximum time to wait for SELL order to fill (hours)
SELL_ORDER_TIMEOUT_HOURS = 24

# =============================================================================
# STOP-LOSS PROTECTION (SELL orders)
# =============================================================================

# Enable stop-loss protection for SELL orders?
# If enabled, bot will cancel losing positions and place aggressive limit orders
ENABLE_STOP_LOSS = True

# Stop-loss trigger threshold (percentage)
# Example: -10.0 means bot will trigger stop-loss if position is down 10%
STOP_LOSS_TRIGGER_PERCENT = -10.0

# Aggressive limit order offset (cents)
# When stop-loss triggers, place limit at: best_bid + this offset
# This is NOT a market order, but an aggressive limit near best bid
STOP_LOSS_AGGRESSIVE_OFFSET = 0.001  # 0.1¢ above best bid

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

# Log file path (relative to bot directory)
LOG_FILE = "opinion_farming_bot.log"

# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
# DEBUG = maximum verbosity (includes all API calls)
# INFO = normal operation (recommended for production)
LOG_LEVEL = "DEBUG"

# =============================================================================
# ALERTS CONFIGURATION
# =============================================================================

# Enable/disable specific alert types
ALERT_ON_ORDER_FILLED = True
ALERT_ON_POSITION_CLOSED = True
ALERT_ON_ERROR = True
ALERT_ON_INSUFFICIENT_BALANCE = True

# =============================================================================
# TELEGRAM NOTIFICATIONS (Future Feature)
# =============================================================================

# Telegram bot token (get from @BotFather)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Your Telegram chat ID (where to send notifications)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# =============================================================================
# PRECISION SETTINGS
# =============================================================================

# Number of decimal places for prices
# Opinion.trade uses 3 decimals for prices
PRICE_DECIMALS = 3

# Number of decimal places for amounts (USDT)
AMOUNT_DECIMALS = 2

# =============================================================================
# SAFETY LIMITS
# =============================================================================

# Minimum BNB balance required for gas fees
# Bot will warn (but continue) if below this threshold
# Note: Order placement doesn't need gas, only split/merge/redeem operations
MIN_BNB_BALANCE_FOR_GAS = 0.01

# Minimum USDT balance required to operate
# Bot will exit if balance falls below this
MIN_USDT_BALANCE = 4

# =============================================================================
# STATE MANAGEMENT
# =============================================================================

# File to persist bot state between restarts
STATE_FILE = "state.json"

# =============================================================================
# VALIDATION FUNCTION
# =============================================================================

def validate_config():
    """
    Validate critical configuration values.
    Call this at bot startup to catch configuration errors early.
    
    Returns:
        tuple: (is_valid: bool, errors: list[str], warnings: list[str])
    """
    errors = []
    warnings = []
    
    # Check required credentials
    if not API_KEY:
        errors.append("API_KEY not set in .env file")
    
    if not PRIVATE_KEY:
        errors.append("PRIVATE_KEY not set in .env file")
    
    # MULTI_SIG_ADDRESS is optional - warn if not set
    if not MULTI_SIG_ADDRESS:
        warnings.append("MULTI_SIG_ADDRESS not set - bot will run in READ-ONLY mode (no trading)")
    
    # Validate numeric ranges
    if CAPITAL_ALLOCATION_PERCENT < 1 or CAPITAL_ALLOCATION_PERCENT > 100:
        errors.append(f"CAPITAL_ALLOCATION_PERCENT must be 1-100, got {CAPITAL_ALLOCATION_PERCENT}")
     
    if TOTAL_CAPITAL_USDT < MIN_USDT_BALANCE:
        errors.append(f"TOTAL_CAPITAL_USDT ({TOTAL_CAPITAL_USDT}) must be >= MIN_USDT_BALANCE ({MIN_USDT_BALANCE})")
    
    # Validate market making parameters (percentage-based)
    
    if SAFETY_MARGIN_CENTS < 0.0001 or SAFETY_MARGIN_CENTS > 0.01:
        errors.append(f"SAFETY_MARGIN_CENTS must be 0.0001-0.01, got {SAFETY_MARGIN_CENTS}")
    
    return (len(errors) == 0, errors, warnings)


# =============================================================================
# SCORING PROFILES
# =============================================================================

SCORING_PROFILES = {
    'production_farming': {
        'description': 'Optimize for maximum airdrop points',
        'weights': {
            'price_balance': 0.45,
            'hourglass_advanced': 0.25,
            'spread': 0.20,
            'volume_24h': 0.10,
        },
        'bonus_multiplier': 1.5,
        'invert_spread': False,
    },
    'test_quick_fill': {
        'description': 'Fast execution for testing Stage 4',
        'weights': {
            'spread': 1.0,
        },
        'bonus_multiplier': 1.0,
        'invert_spread': True,
    },
    'balanced': {
        'description': 'Balanced approach for general trading',
        'weights': {
            'price_balance': 0.25,
            'spread': 0.25,
            'volume_24h': 0.25,
            'liquidity_depth': 0.25,
        },
        'bonus_multiplier': 1.2,
        'invert_spread': False,
    },
}

DEFAULT_SCORING_PROFILE = 'production_farming'

def get_scoring_profile(profile_name: str = None):
    """Get scoring profile by name."""
    if profile_name is None:
        profile_name = DEFAULT_SCORING_PROFILE
    
    if profile_name not in SCORING_PROFILES:
        available = ', '.join(SCORING_PROFILES.keys())
        raise ValueError(
            f"Unknown scoring profile: '{profile_name}'\n"
            f"Available profiles: {available}"
        )
    
    return SCORING_PROFILES[profile_name]

# ============================================================================
# PRICING STRATEGY - ADVANCED TUNING (OPTIONAL)
# ============================================================================
# These are already set as defaults in pricing.py, but you can override:

# PRICING_NARROW_IMPROVEMENT_PCT = 0.15   # For spreads <2%
# PRICING_MEDIUM_IMPROVEMENT_PCT = 0.40   # For spreads 2-5%
# PRICING_WIDE_IMPROVEMENT_PCT = 0.80     # For spreads >5%
# PRICING_NARROW_THRESHOLD_PCT = 2.0      # Narrow/medium boundary
# PRICING_MEDIUM_THRESHOLD_PCT = 5.0      # Medium/wide boundary

# =============================================================================
# QUICK REFERENCE
# =============================================================================
"""
MARKET MAKING STRATEGY QUICK REFERENCE [FOR LEGACY]:

For BUY orders (Stage 2):
- Place bid slightly ABOVE current best bid
- price = best_bid + BUY_IMPROVEMENT_CENTS
- Example: bid=6.1¢, improvement=0.3¢ → order @ 6.4¢
- This makes you the NEW best bid while staying within spread (maker)

For SELL orders (Stage 4):
- Place ask slightly BELOW current best ask
- price = best_ask - SELL_IMPROVEMENT_CENTS
- Example: ask=10.9¢, improvement=0.7¢ → order @ 10.2¢
- This makes you the NEW best ask while staying within spread (maker)

SAFETY CHECKS:
- Orders never cross the spread (prevents taker execution)
- Minimum SAFETY_MARGIN_CENTS distance from opposite side
- Example: if calculated buy=10.8¢ but ask=10.9¢, adjust to 10.8¢ (safe)

RE-PRICING LOGIC:
- Uses same market making strategy (bid + improvement)
- Capitulation limit prevents racing to the bottom
- min_acceptable_price = initial_price * (capitulation_percent / 100)
- New price = max(competitive_price, min_acceptable_price)

SCORING FORMULA:
- score = spread_percent × bonus_multiplier
- Higher spread = less competition = more attractive
- Bonus markets get 2x multiplier (configurable)
- Large spreads give more room for price improvements
"""