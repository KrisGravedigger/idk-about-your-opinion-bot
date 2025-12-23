"""
ADD TO YOUR config.py FILE
===========================

These scoring profiles define different strategies for ranking markets.
Add this section to your existing config.py.
"""

# =============================================================================
# SCORING PROFILES
# =============================================================================

# Available profiles:
# - 'production_farming': Optimize for airdrop points (balance + hourglass)
# - 'test_quick_fill': Optimize for fast order execution (tight spread)
# - 'balanced': General purpose with all factors
# - 'custom': Define your own in market_scanner.py

SCORING_PROFILES = {
    # =========================================================================
    # PRODUCTION: Farming airdrop points
    # =========================================================================
    'production_farming': {
        'description': 'Optimize for maximum airdrop points',
        'weights': {
            'price_balance': 0.45,      # 45% - Critical: 50/50 balance
            'hourglass_advanced': 0.25,  # 25% - Important: Orderbook shape
            'spread': 0.20,              # 20% - Nice: Profit from spread
            'volume_24h': 0.10,          # 10% - Bonus: High volume
        },
        'bonus_multiplier': 1.5,  # 1.5x score for designated markets
        'invert_spread': False,   # Large spread = better
        'hourglass_params': {
            'near_zone_pct': 0.05,   # ±5% from mid
            'far_zone_pct': 0.15,    # ±15% from mid
            'ideal_ratio': 3.0,      # Far/near ratio
        }
    },
    
    # =========================================================================
    # TEST: Quick order execution
    # =========================================================================
    'test_quick_fill': {
        'description': 'Fast execution for testing Stage 4',
        'weights': {
            'spread': 1.0,  # 100% - Only spread matters
            # All other metrics ignored
        },
        'bonus_multiplier': 1.0,  # No bonus (not farming)
        'invert_spread': True,    # Small spread = better
    },
    
    # =========================================================================
    # BALANCED: General trading
    # =========================================================================
    'balanced': {
        'description': 'Balanced approach for general trading',
        'weights': {
            'price_balance': 0.25,
            'spread': 0.25,
            'volume_24h': 0.25,
            'liquidity_depth': 0.25,
        },
        'bonus_multiplier': 1.2,  # Slight bonus
        'invert_spread': False,
    },
    
    # =========================================================================
    # VOLUME HUNTER: High liquidity markets
    # =========================================================================
    'volume_hunter': {
        'description': 'Target high volume, liquid markets',
        'weights': {
            'volume_24h': 0.50,
            'liquidity_depth': 0.30,
            'spread': 0.20,
        },
        'bonus_multiplier': 1.0,
        'invert_spread': True,  # Tight spread for liquid markets
    },
    
    # =========================================================================
    # SPREAD SEEKER: Arbitrage opportunities
    # =========================================================================
    'spread_seeker': {
        'description': 'Find markets with large spreads for profit',
        'weights': {
            'spread': 0.70,
            'volume_24h': 0.20,
            'liquidity_depth': 0.10,
        },
        'bonus_multiplier': 1.0,
        'invert_spread': False,  # Large spread = better
    },
}


# Default profile (used if none specified)
DEFAULT_SCORING_PROFILE = 'production_farming'


# =============================================================================
# HELPER FUNCTION
# =============================================================================

def get_scoring_profile(profile_name: str = None):
    """
    Get scoring profile by name.
    
    Args:
        profile_name: Name of profile (or None for default)
        
    Returns:
        Profile dict
        
    Raises:
        ValueError: If profile doesn't exist
    """
    if profile_name is None:
        profile_name = DEFAULT_SCORING_PROFILE
    
    if profile_name not in SCORING_PROFILES:
        available = ', '.join(SCORING_PROFILES.keys())
        raise ValueError(
            f"Unknown scoring profile: '{profile_name}'\n"
            f"Available profiles: {available}"
        )
    
    return SCORING_PROFILES[profile_name]


# =============================================================================
# USAGE EXAMPLES
# =============================================================================

"""
Example 1: Use in market scanner

from config import get_scoring_profile

# Production farming
profile = get_scoring_profile('production_farming')
top_markets = scanner.scan_and_rank(scoring_profile=profile)

# Test quick fill
profile = get_scoring_profile('test_quick_fill')
liquid_markets = scanner.scan_and_rank(scoring_profile=profile)


Example 2: Override weights dynamically

profile = get_scoring_profile('production_farming')
profile['weights']['price_balance'] = 0.60  # Increase importance
top_markets = scanner.scan_and_rank(scoring_profile=profile)


Example 3: Create custom profile on the fly

custom_profile = {
    'weights': {
        'price_balance': 0.80,
        'hourglass_simple': 0.20,
    },
    'bonus_multiplier': 2.0,
    'invert_spread': False,
}
top_markets = scanner.scan_and_rank(scoring_profile=custom_profile)
"""
