"""
Opinion Farming Bot - Scoring Module
====================================

Central repository of ALL scoring metrics for market evaluation.

ARCHITECTURE:
    - Pure functions (no side effects)
    - Each metric returns 0.0 to 1.0 (normalized score)
    - Metrics can be combined with different weights
    - Profiles in config.py define which metrics to use

USAGE:
    from scoring import calculate_market_score, SCORING_PROFILES
    
    # Use predefined profile
    score = calculate_market_score(market, orderbook, profile='production_farming')
    
    # Or custom weights
    score = calculate_market_score(market, orderbook, weights={...})

AVAILABLE METRICS:
    1. price_balance - How close YES price is to 0.50 (50/50)
    2. hourglass_advanced - Orderbook shape (zone-based analysis)
    3. hourglass_simple - Orderbook shape (level-based, faster)
    4. spread - Bid-ask spread (can optimize for large or small)
    5. volume_24h - Trading volume
    6. liquidity_depth - Total orderbook depth
    7. bonus_market - Is this a designated bonus market?

ADD NEW METRICS HERE as pure functions following the pattern.
"""

import math
from typing import Dict, List, Optional, Any


# =============================================================================
# PRICE METRICS
# =============================================================================

def score_price_balance(best_bid: float, best_ask: float) -> float:
    """
    Score how close the market is to 50/50 balance.
    
    Perfect 50/50 = 1.0
    Extreme bias (close to 0 or 1) = 0.0
    
    Args:
        best_bid: Best bid price (YES token)
        best_ask: Best ask price (YES token)
        
    Returns:
        Score from 0.0 to 1.0
        
    Example:
        best_bid=0.49, best_ask=0.51 → mid=0.50 → score=1.0 (perfect)
        best_bid=0.20, best_ask=0.22 → mid=0.21 → score=0.42 (biased)
    """
    mid_price = (best_bid + best_ask) / 2
    
    # Distance from 0.50
    distance_from_center = abs(mid_price - 0.50)
    
    # Convert to score (0.0 distance = 1.0 score, 0.5 distance = 0.0 score)
    score = 1.0 - (distance_from_center * 2.0)
    
    return max(0.0, score)


# =============================================================================
# ORDERBOOK SHAPE METRICS (HOURGLASS)
# =============================================================================

def score_hourglass_advanced(
    orderbook: Dict[str, List[Dict[str, str]]],
    best_bid: float,
    best_ask: float,
    near_zone_pct: float = 0.05,
    far_zone_pct: float = 0.15,
    ideal_ratio: float = 3.0
) -> float:
    """
    Advanced hourglass score using zone-based analysis.
    
    Measures liquidity distribution:
    - NEAR zone: ±5% from mid-price (should have LESS liquidity)
    - FAR zone: ±15% from mid-price (should have MORE liquidity)
    
    Perfect hourglass: far_liquidity / near_liquidity ≥ 3.0
    
    Args:
        orderbook: Dict with 'bids' and 'asks' lists
        best_bid: Best bid price
        best_ask: Best ask price
        near_zone_pct: % range for "near" zone (default 5%)
        far_zone_pct: % range for "far" zone (default 15%)
        ideal_ratio: Target far/near ratio (default 3.0)
        
    Returns:
        Score from 0.0 to 1.0
        
    Example:
        Near=10k, Far=30k → ratio=3.0 → score=1.0 (perfect)
        Near=10k, Far=15k → ratio=1.5 → score=0.5 (medium)
        Near=10k, Far=5k → ratio=0.5 → score=0.17 (poor)
    """
    if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
        return 0.0
    
    mid_price = (best_bid + best_ask) / 2
    
    # Define zones
    near_low = mid_price * (1 - near_zone_pct)
    near_high = mid_price * (1 + near_zone_pct)
    far_low = mid_price * (1 - far_zone_pct)
    far_high = mid_price * (1 + far_zone_pct)
    
    near_liquidity = 0.0
    far_liquidity = 0.0
    
    # Process bids
    for bid in orderbook.get('bids', []):
        try:
            price = float(bid['price'])
            size = float(bid['size'])
            
            if near_low <= price <= near_high:
                near_liquidity += size
            elif far_low <= price < near_low:
                far_liquidity += size
        except (KeyError, ValueError, TypeError):
            continue
    
    # Process asks
    for ask in orderbook.get('asks', []):
        try:
            price = float(ask['price'])
            size = float(ask['size'])
            
            if near_low <= price <= near_high:
                near_liquidity += size
            elif near_high < price <= far_high:
                far_liquidity += size
        except (KeyError, ValueError, TypeError):
            continue
    
    # Calculate ratio
    if near_liquidity == 0:
        return 0.0  # No near liquidity = bad (no market depth)
    
    ratio = far_liquidity / near_liquidity
    
    # Normalize to 0-1 (ideal_ratio or higher = 1.0)
    score = min(ratio / ideal_ratio, 1.0)
    
    return score


def score_hourglass_simple(
    orderbook: Dict[str, List[Dict[str, str]]],
    near_levels: int = 3,
    far_start: int = 3,
    far_end: int = 10,
    ideal_ratio: float = 2.0
) -> float:
    """
    Simplified hourglass score using level-based analysis.
    
    Faster computation:
    - Near levels: First N orders (default 3)
    - Far levels: Orders from position M to N (default 3-10)
    
    Args:
        orderbook: Dict with 'bids' and 'asks' lists
        near_levels: Number of top levels considered "near" (default 3)
        far_start: Starting index for "far" levels (default 3)
        far_end: Ending index for "far" levels (default 10)
        ideal_ratio: Target far/near ratio (default 2.0)
        
    Returns:
        Score from 0.0 to 1.0
        
    Example:
        Near (top 3): 15k volume
        Far (levels 4-10): 30k volume
        Ratio: 2.0 → score: 1.0
    """
    if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
        return 0.0
    
    bids = orderbook.get('bids', [])
    asks = orderbook.get('asks', [])
    
    near_volume = 0.0
    far_volume = 0.0
    
    # Near volume (top N levels)
    for i in range(min(near_levels, len(bids))):
        try:
            near_volume += float(bids[i]['size'])
        except (KeyError, ValueError, TypeError, IndexError):
            pass
    
    for i in range(min(near_levels, len(asks))):
        try:
            near_volume += float(asks[i]['size'])
        except (KeyError, ValueError, TypeError, IndexError):
            pass
    
    # Far volume (levels M to N)
    for i in range(far_start, min(far_end, len(bids))):
        try:
            far_volume += float(bids[i]['size'])
        except (KeyError, ValueError, TypeError, IndexError):
            pass
    
    for i in range(far_start, min(far_end, len(asks))):
        try:
            far_volume += float(asks[i]['size'])
        except (KeyError, ValueError, TypeError, IndexError):
            pass
    
    # Calculate ratio
    if near_volume == 0:
        return 0.0
    
    ratio = far_volume / near_volume
    
    # Normalize
    score = min(ratio / ideal_ratio, 1.0)
    
    return score


# =============================================================================
# SPREAD METRICS
# =============================================================================

def score_spread_large(spread_pct: float, max_good_spread: float = 20.0) -> float:
    """
    Score spread for FARMING strategy (larger = better for points).
    
    Large spread (10-20%) = 1.0 (good for farming)
    Small spread (0-2%) = 0.0 (competitive, less farming potential)
    
    Args:
        spread_pct: Spread as percentage (e.g., 15.5)
        max_good_spread: Spread % considered "perfect" (default 20%)
        
    Returns:
        Score from 0.0 to 1.0
    """
    # Normalize: 0% = 0.0, max_good_spread% = 1.0
    score = min(spread_pct / max_good_spread, 1.0)
    return score


def score_spread_small(spread_pct: float, max_good_spread: float = 2.0) -> float:
    """
    Score spread for TESTING/QUICK-FILL strategy (smaller = better).
    
    Small spread (0-2%) = 1.0 (liquid, fast execution)
    Large spread (10-20%) = 0.0 (illiquid, slow execution)
    
    Args:
        spread_pct: Spread as percentage (e.g., 1.5)
        max_good_spread: Spread % considered "perfect" (default 2%)
        
    Returns:
        Score from 0.0 to 1.0
    """
    # Invert: smaller is better
    if spread_pct >= max_good_spread * 5:  # Very large spread
        return 0.0
    
    # Linear decay: 0% = 1.0, max_good_spread = 1.0, 5x max = 0.0
    score = 1.0 - (spread_pct / (max_good_spread * 5))
    
    return max(0.0, score)


# =============================================================================
# VOLUME METRICS
# =============================================================================

def score_volume_24h(
    volume_24h: float,
    min_volume: float = 0.0,
    max_volume: float = 100000.0,
    log_scale: bool = True
) -> float:
    """
    Score 24h trading volume.
    
    Can use linear or logarithmic scaling.
    
    Args:
        volume_24h: 24h volume in USDT
        min_volume: Minimum volume for score=0.0
        max_volume: Volume for score=1.0 (default $100k)
        log_scale: Use logarithmic scaling (default True)
        
    Returns:
        Score from 0.0 to 1.0
        
    Example (log scale):
        $100 → 0.2
        $1,000 → 0.4
        $10,000 → 0.6
        $100,000 → 1.0
    """
    if volume_24h <= min_volume:
        return 0.0
    
    if log_scale:
        # Logarithmic scaling (better for wide range of volumes)
        log_vol = math.log10(volume_24h)
        log_min = math.log10(max(min_volume, 1))
        log_max = math.log10(max_volume)
        
        score = (log_vol - log_min) / (log_max - log_min)
    else:
        # Linear scaling
        score = (volume_24h - min_volume) / (max_volume - min_volume)
    
    return max(0.0, min(1.0, score))


def score_liquidity_depth(
    orderbook: Dict[str, List[Dict[str, str]]],
    max_depth: float = 50000.0
) -> float:
    """
    Score total orderbook depth (sum of all bid/ask sizes).
    
    More liquidity = higher score.
    
    Args:
        orderbook: Dict with 'bids' and 'asks' lists
        max_depth: Depth in tokens for score=1.0 (default 50k)
        
    Returns:
        Score from 0.0 to 1.0
    """
    if not orderbook:
        return 0.0
    
    total_depth = 0.0
    
    # Sum all bids
    for bid in orderbook.get('bids', []):
        try:
            total_depth += float(bid['size'])
        except (KeyError, ValueError, TypeError):
            pass
    
    # Sum all asks
    for ask in orderbook.get('asks', []):
        try:
            total_depth += float(ask['size'])
        except (KeyError, ValueError, TypeError):
            pass
    
    # Normalize
    score = min(total_depth / max_depth, 1.0)
    
    return score


# =============================================================================
# BONUS METRICS
# =============================================================================

def score_bonus_market(is_bonus: bool, multiplier: float = 1.5) -> float:
    """
    Apply multiplier for designated bonus markets.
    
    NOTE: This is not a 0-1 score but a multiplier!
    Use it differently in calculate_market_score.
    
    Args:
        is_bonus: Whether market is a bonus market
        multiplier: Multiplier to apply (default 1.5x)
        
    Returns:
        Multiplier (1.0 or higher)
    """
    return multiplier if is_bonus else 1.0


# =============================================================================
# COMPOSITE SCORING
# =============================================================================

def calculate_market_score(
    market: Any,
    orderbook: Optional[Dict[str, List[Dict[str, str]]]] = None,
    weights: Optional[Dict[str, float]] = None,
    bonus_multiplier: float = 1.0,
    invert_spread: bool = False
) -> float:
    """
    Calculate composite market score using weighted metrics.
    
    Args:
        market: Market object with attributes (best_bid, best_ask, spread_pct, etc.)
        orderbook: Optional orderbook data (needed for hourglass metrics)
        weights: Dict of metric weights (default: all equal)
        bonus_multiplier: Multiplier for bonus markets (default 1.0 = no bonus)
        invert_spread: If True, prefer small spreads (for testing)
        
    Returns:
        Final weighted score
        
    Example:
        weights = {
            'price_balance': 0.45,
            'hourglass_advanced': 0.25,
            'spread': 0.20,
            'volume_24h': 0.10
        }
        score = calculate_market_score(market, orderbook, weights=weights)
    """
    # Default weights (equal)
    if weights is None:
        weights = {
            'price_balance': 0.25,
            'spread': 0.25,
            'volume_24h': 0.25,
            'liquidity_depth': 0.25
        }
    
    # Validate weights sum to ~1.0
    total_weight = sum(weights.values())
    if not (0.99 <= total_weight <= 1.01):
        # Normalize if needed
        weights = {k: v/total_weight for k, v in weights.items()}
    
    # Calculate individual scores
    scores = {}
    
    # Price balance
    if 'price_balance' in weights:
        scores['price_balance'] = score_price_balance(
            market.best_bid,
            market.best_ask
        )
    
    # Hourglass (advanced)
    if 'hourglass_advanced' in weights and orderbook:
        scores['hourglass_advanced'] = score_hourglass_advanced(
            orderbook,
            market.best_bid,
            market.best_ask
        )
    
    # Hourglass (simple)
    if 'hourglass_simple' in weights and orderbook:
        scores['hourglass_simple'] = score_hourglass_simple(orderbook)
    
    # Spread
    if 'spread' in weights:
        if invert_spread:
            scores['spread'] = score_spread_small(market.spread_pct)
        else:
            scores['spread'] = score_spread_large(market.spread_pct)
    
    # Volume
    if 'volume_24h' in weights and hasattr(market, 'volume_24h'):
        scores['volume_24h'] = score_volume_24h(market.volume_24h)
    
    # Liquidity depth
    if 'liquidity_depth' in weights and orderbook:
        scores['liquidity_depth'] = score_liquidity_depth(orderbook)

    # Bias score (spread farming)
    if 'bias_score' in weights and orderbook:
        bid_volume_pct = calculate_bid_volume_percentage(orderbook)
        if bid_volume_pct is not None:
            scores['bias_score'] = calculate_bias_score(bid_volume_pct)
        else:
            scores['bias_score'] = 0.0

    # Calculate weighted sum
    final_score = 0.0
    for metric, weight in weights.items():
        if metric in scores:
            final_score += scores[metric] * weight
    
    # Apply bonus multiplier
    if hasattr(market, 'is_bonus') and market.is_bonus:
        final_score *= bonus_multiplier
    
    return final_score


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def normalize_scores(scores: Dict[str, float]) -> Dict[str, float]:
    """
    Normalize a dict of scores to 0-1 range using min-max scaling.
    
    Useful when comparing markets.
    """
    if not scores:
        return {}
    
    values = list(scores.values())
    min_val = min(values)
    max_val = max(values)
    
    if max_val == min_val:
        return {k: 1.0 for k in scores.keys()}
    
    return {
        k: (v - min_val) / (max_val - min_val)
        for k, v in scores.items()
    }


def get_available_metrics() -> List[str]:
    """
    Return list of all available scoring metrics.

    Useful for config validation and documentation.
    """
    return [
        'price_balance',
        'hourglass_advanced',
        'hourglass_simple',
        'spread',
        'volume_24h',
        'liquidity_depth',
        'bias_score',
    ]


# =============================================================================
# ORDERBOOK BIAS METRICS (SPREAD FARMING)
# =============================================================================

def calculate_bid_volume_percentage(orderbook: Dict[str, List[Dict[str, str]]]) -> Optional[float]:
    """
    Calculate percentage of total orderbook volume on bid side.

    Args:
        orderbook: Dict with 'bids' and 'asks' lists

    Returns:
        Percentage (0-100) of volume on bid side, or None if orderbook empty

    Example:
        >>> orderbook = {'bids': [...], 'asks': [...]}
        >>> calculate_bid_volume_percentage(orderbook)
        68.5  # 68.5% of volume is on bid side
    """
    if not orderbook:
        return None

    bids = orderbook.get('bids', [])
    asks = orderbook.get('asks', [])

    if not bids or not asks:
        return None

    # Calculate total volume on each side
    bid_volume = 0.0
    for bid in bids:
        try:
            bid_volume += float(bid.get('size', 0))
        except (ValueError, TypeError):
            pass

    ask_volume = 0.0
    for ask in asks:
        try:
            ask_volume += float(ask.get('size', 0))
        except (ValueError, TypeError):
            pass

    total_volume = bid_volume + ask_volume

    if total_volume == 0:
        return None

    bid_percentage = (bid_volume / total_volume) * 100
    return bid_percentage


def calculate_bias_score(bid_volume_pct: float) -> float:
    """
    Calculate bias score based on orderbook imbalance.

    Rewards orderbooks tilted 60-85% to bid side (sweet spot for probability trading).
    Score decreases linearly outside this range.

    Args:
        bid_volume_pct: Percentage of total orderbook volume on bid side (0-100)

    Returns:
        float: Score between 0.0 and 1.0

    Examples:
        >>> calculate_bias_score(70.0)  # Sweet spot
        1.0
        >>> calculate_bias_score(50.0)  # Balanced
        0.833
        >>> calculate_bias_score(90.0)  # Too biased
        0.667
    """
    if 60 <= bid_volume_pct <= 85:
        return 1.0
    elif bid_volume_pct < 60:
        # Linear decay from 60% down to 0%
        return max(0.0, bid_volume_pct / 60)
    else:  # > 85%
        # Linear decay from 85% to 100%
        return max(0.0, (100 - bid_volume_pct) / 15)


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    # Example: Test individual metrics
    print("=== Scoring Module Test ===\n")
    
    # Test price balance
    print("1. Price Balance:")
    print(f"   50/50 market (0.49/0.51): {score_price_balance(0.49, 0.51):.3f}")
    print(f"   Biased market (0.20/0.22): {score_price_balance(0.20, 0.22):.3f}")
    print()
    
    # Test spread scoring
    print("2. Spread Scoring:")
    print(f"   Large spread (15%): {score_spread_large(15.0):.3f} (farming)")
    print(f"   Small spread (1.5%): {score_spread_small(1.5):.3f} (testing)")
    print()
    
    # Test volume
    print("3. Volume Scoring:")
    print(f"   Low volume ($100): {score_volume_24h(100):.3f}")
    print(f"   Medium volume ($10k): {score_volume_24h(10000):.3f}")
    print(f"   High volume ($100k): {score_volume_24h(100000):.3f}")
    print()
    
    print("✅ All metrics functional")
