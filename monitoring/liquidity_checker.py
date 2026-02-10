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
            config: Configuration dictionary with stop-loss threshold
            client: OpinionClient instance (must have get_market_orderbook method)

        Example:
            >>> from config import STOP_LOSS_TRIGGER_PERCENT, LIQUIDITY_AUTO_CANCEL
            >>> config = {
            ...     'LIQUIDITY_AUTO_CANCEL': True,
            ...     'STOP_LOSS_TRIGGER_PERCENT': -15.0
            ... }
            >>> checker = LiquidityChecker(config, client)
        """
        self.config = config
        self.client = client

        # Extract config values
        self.auto_cancel = config['LIQUIDITY_AUTO_CANCEL']
        # Use stop-loss threshold (convert negative to positive for comparison)
        self.stop_loss_threshold = abs(config['STOP_LOSS_TRIGGER_PERCENT'])

        logger.debug(
            f"LiquidityChecker initialized: stop_loss<{self.stop_loss_threshold}%"
        )
    
    def check_liquidity(
        self,
        market_id: int,
        token_id: int,
        initial_best_bid: float,
        buy_price: Optional[float] = None,
        initial_spread_pct: Optional[float] = None,
        stop_loss_spread_filter: Optional[float] = None,
        outcome_side: str = 'YES'
    ) -> Dict[str, Any]:
        """
        Check if liquidity has deteriorated significantly.

        Args:
            market_id: Market ID (for logging)
            token_id: Token ID to fetch orderbook (DEPRECATED - use market_id + outcome_side)
            initial_best_bid: Initial best bid price when order was placed (for compatibility)
            buy_price: Actual price paid for position (used for stop-loss calculation)
            initial_spread_pct: Initial spread percentage when order was placed
            stop_loss_spread_filter: Spread filter threshold to prevent stop-loss during flash crashes
            outcome_side: "YES" or "NO" (default "YES")

        Returns:
            Dictionary with structure:
            {
                'ok': bool,                      # False if deteriorated
                'current_best_bid': float,       # Current best bid price
                'current_best_ask': float,       # Current best ask price
                'current_spread_pct': float,     # Current spread percentage
                'bid_drop_pct': float,           # Bid drop from BUY PRICE (negative = worse)
                'deterioration_reason': str|None # Explanation if deteriorated
            }

        Example:
            >>> # Good liquidity
            >>> result = checker.check_liquidity(813, 1626, 0.066, buy_price=0.072, initial_spread_pct=12.0, outcome_side='YES')
            >>> result['ok']
            True

            >>> # Bad liquidity (price dropped 30% from buy price)
            >>> result = checker.check_liquidity(813, 1626, 0.100, buy_price=0.150, initial_spread_pct=10.0, outcome_side='YES')
            >>> result['ok']
            False
            >>> result['deterioration_reason']
            'Bid dropped 33.3% from buy price (threshold: -25.0%)'
        """
        logger.debug(
            f"Checking liquidity for market {market_id} ({outcome_side}), "
            f"initial bid: {format_price(initial_best_bid)}"
        )

        # Get fresh orderbook using abstract interface
        orderbook = self.client.get_orderbook(market_id=str(market_id), outcome_side=outcome_side)
        
        if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
            logger.warning(f"⚠️  Could not fetch orderbook for market {market_id} ({outcome_side})")
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
            logger.warning(f"⚠️  Empty orderbook for market {market_id} ({outcome_side})")
            return {
                'ok': True,
                'current_best_bid': initial_best_bid,
                'current_best_ask': initial_best_bid,
                'current_spread_pct': 0.0,
                'bid_drop_pct': 0.0,
                'deterioration_reason': None
            }

        # Extract current best bid and ask from normalized orderbook
        # Adapter returns bids sorted descending, asks sorted ascending
        current_best_bid = safe_float(bids[0].get('price', 0)) if bids else 0
        current_best_ask = safe_float(asks[0].get('price', 0)) if asks else 0

        # Calculate current spread percentage
        if current_best_bid > 0:
            current_spread_pct = ((current_best_ask - current_best_bid) / current_best_bid) * 100
        else:
            current_spread_pct = 0.0

        # Calculate bid drop from BUY PRICE (for stop-loss detection)
        # This is the TRUE price drop that matters to the trader
        reference_price = buy_price if buy_price and buy_price > 0 else initial_best_bid

        if reference_price > 0:
            bid_drop_pct = ((current_best_bid - reference_price) / reference_price) * 100
        else:
            bid_drop_pct = 0.0

        logger.debug(
            f"   Current bid: {format_price(current_best_bid)} "
            f"(drop from buy price: {format_percent(bid_drop_pct)})"
        )
        logger.debug(f"   Current spread: {format_percent(current_spread_pct)}")

        # Check deterioration conditions
        deterioration_reason = None

        # ONLY CHECK: TRUE STOP-LOSS - Bid dropped below buy price by threshold
        # This is a real price crash that requires exiting the position
        #
        # NOTE: We do NOT check spread widening anymore!
        # Rationale: If market has wide spread but stable price, we should:
        # - Keep the order active (don't cancel)
        # - Wait for timeout (8h default)
        # - After timeout, repricing can adjust if needed
        #
        # Spread widening is NOT a reason to cancel - it's just illiquidity.
        # Only a true price crash (bid drop from entry price) triggers stop-loss.
        if bid_drop_pct < -self.stop_loss_threshold:
            # BEFORE setting deterioration_reason, check spread filter
            # If spread is too wide, this is temporary illiquidity, not a real crash
            if stop_loss_spread_filter and current_spread_pct > stop_loss_spread_filter:
                # Spread too wide - this is flash crash/temporary illiquidity
                logger.debug(
                    f"   Spread {format_percent(current_spread_pct)} > filter "
                    f"{format_percent(stop_loss_spread_filter)} - ignoring bid drop"
                )
                # Don't trigger deterioration
            else:
                # Spread OK - this is a real price crash
                deterioration_reason = (
                    f"Bid dropped {format_percent(abs(bid_drop_pct))} from buy price "
                    f"(stop-loss threshold: {format_percent(self.stop_loss_threshold)})"
                )
                logger.warning(f"⚠️  {deterioration_reason}")
        else:
            # Liquidity is acceptable (no price crash)
            # Log spread info for debugging, but don't trigger deterioration
            if initial_spread_pct is not None and current_spread_pct > initial_spread_pct * 1.5:
                logger.debug(
                    f"   Note: Spread widened from {format_percent(initial_spread_pct)} "
                    f"to {format_percent(current_spread_pct)}, but price is stable (no action)"
                )
            elif current_spread_pct > 20.0:  # Just for logging - not used for decisions
                logger.debug(
                    f"   Note: Spread is wide ({format_percent(current_spread_pct)}), "
                    f"but this is normal for illiquid markets (no action)"
                )
        
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