"""
Liquidity Checker Module
=========================

Monitors orderbook liquidity and detects deterioration.

Key responsibilities:
- Compare current orderbook vs initial conditions
- Calculate bid price drop percentage
- Calculate spread percentage
- Detect liquidity deterioration based on thresholds
- Return structured results with reasons

Used by both BUY and SELL monitors to decide if order should be cancelled
due to worsening market conditions.

Usage:
    from monitoring.liquidity_checker import LiquidityChecker
    
    checker = LiquidityChecker(config, client)
    result = checker.check_liquidity(market_id, token_id, initial_bid)
    
    if not result['ok']:
        print(f"Liquidity deteriorated: {result['deterioration_reason']}")
"""

from typing import Dict, Any, Optional
from logger_config import setup_logger
from utils import safe_float, format_price, format_percent

logger = setup_logger(__name__)


class LiquidityChecker:
    """
    Monitors orderbook liquidity and detects deterioration.
    
    Attributes:
        config: Configuration dictionary
        client: API client instance
    """
    
    def __init__(self, config: Dict[str, Any], client):
        """
        Initialize Liquidity Checker.
        
        Args:
            config: Configuration dictionary with liquidity thresholds
            client: OpinionClient instance (must have get_market_orderbook method)
        
        Example:
            >>> from config import (LIQUIDITY_BID_DROP_THRESHOLD, ...)
            >>> config = {
            ...     'LIQUIDITY_AUTO_CANCEL': True,
            ...     'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
            ...     'LIQUIDITY_SPREAD_THRESHOLD': 15.0
            ... }
            >>> checker = LiquidityChecker(config, client)
        """
        self.config = config
        self.client = client
        
        # Extract config values
        self.auto_cancel = config['LIQUIDITY_AUTO_CANCEL']
        self.bid_drop_threshold = config['LIQUIDITY_BID_DROP_THRESHOLD']
        self.spread_threshold = config['LIQUIDITY_SPREAD_THRESHOLD']
        
        logger.debug(
            f"LiquidityChecker initialized: "
            f"bid_drop<{self.bid_drop_threshold}%, "
            f"spread<{self.spread_threshold}%"
        )
    
    def check_liquidity(
        self, 
        market_id: int, 
        token_id: int, 
        initial_best_bid: float
    ) -> Dict[str, Any]:
        """
        Check if liquidity has deteriorated significantly.
        
        Args:
            market_id: Market ID (for logging)
            token_id: Token ID to fetch orderbook
            initial_best_bid: Initial best bid price when order was placed
            
        Returns:
            Dictionary with structure:
            {
                'ok': bool,                      # False if deteriorated
                'current_best_bid': float,       # Current best bid price
                'current_best_ask': float,       # Current best ask price
                'current_spread_pct': float,     # Current spread percentage
                'bid_drop_pct': float,           # Bid drop from initial (negative = worse)
                'deterioration_reason': str|None # Explanation if deteriorated
            }
        
        Example:
            >>> # Good liquidity
            >>> result = checker.check_liquidity(813, 1626, 0.066)
            >>> result['ok']
            True
            
            >>> # Bad liquidity (bid dropped 30%)
            >>> result = checker.check_liquidity(813, 1626, 0.100)
            >>> result['ok']
            False
            >>> result['deterioration_reason']
            'Bid dropped 30.0% (threshold: 25.0%)'
        """
        logger.debug(
            f"Checking liquidity for market {market_id}, "
            f"initial bid: {format_price(initial_best_bid)}"
        )
        
        # Get fresh orderbook
        orderbook = self.client.get_market_orderbook(token_id)
        
        if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
            logger.warning(f"⚠️  Could not fetch orderbook for token {token_id}")
            # Return neutral result (don't cancel on fetch failure)
            return {
                'ok': True,
                'current_best_bid': initial_best_bid,
                'current_best_ask': initial_best_bid,
                'current_spread_pct': 0.0,
                'bid_drop_pct': 0.0,
                'deterioration_reason': None
            }
        
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        if not bids or not asks:
            logger.warning(f"⚠️  Empty orderbook for token {token_id}")
            return {
                'ok': True,
                'current_best_bid': initial_best_bid,
                'current_best_ask': initial_best_bid,
                'current_spread_pct': 0.0,
                'bid_drop_pct': 0.0,
                'deterioration_reason': None
            }
        
        # Extract current best bid and ask
        # Note: Opinion.trade orderbook may not be sorted, so use max/min
        current_best_bid = max(safe_float(bid.get('price', 0)) for bid in bids)
        current_best_ask = min(safe_float(ask.get('price', 0)) for ask in asks)
        
        # Calculate bid drop percentage (negative = worse)
        if initial_best_bid > 0:
            bid_drop_pct = ((current_best_bid - initial_best_bid) / initial_best_bid) * 100
        else:
            bid_drop_pct = 0.0
        
        # Calculate current spread percentage
        if current_best_bid > 0:
            current_spread_pct = ((current_best_ask - current_best_bid) / current_best_bid) * 100
        else:
            current_spread_pct = 0.0
        
        logger.debug(
            f"   Current bid: {format_price(current_best_bid)} "
            f"(drop: {format_percent(bid_drop_pct)})"
        )
        logger.debug(f"   Current spread: {format_percent(current_spread_pct)}")
        
        # Check deterioration conditions
        deterioration_reason = None
        
        # Check 1: Bid dropped too much (negative drop = price decrease)
        if bid_drop_pct < -self.bid_drop_threshold:
            deterioration_reason = (
                f"Bid dropped {format_percent(abs(bid_drop_pct))} "
                f"(threshold: {format_percent(self.bid_drop_threshold)})"
            )
            logger.warning(f"⚠️  {deterioration_reason}")
        
        # Check 2: Spread too wide
        elif current_spread_pct > self.spread_threshold:
            deterioration_reason = (
                f"Spread widened to {format_percent(current_spread_pct)} "
                f"(threshold: {format_percent(self.spread_threshold)})"
            )
            logger.warning(f"⚠️  {deterioration_reason}")
        
        # Determine if liquidity is OK
        liquidity_ok = (deterioration_reason is None)
        
        if liquidity_ok:
            logger.debug("✅ Liquidity conditions acceptable")
        
        return {
            'ok': liquidity_ok,
            'current_best_bid': current_best_bid,
            'current_best_ask': current_best_ask,
            'current_spread_pct': current_spread_pct,
            'bid_drop_pct': bid_drop_pct,
            'deterioration_reason': deterioration_reason
        }


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("Use test_liquidity_checker.py for comprehensive testing")