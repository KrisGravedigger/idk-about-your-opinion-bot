"""
Pricing Strategy Module
=======================

Simple threshold-based pricing strategy.
No percentages, no complex calculations - just spread thresholds and fixed improvements.

BUY Logic:
    spread ≤ $0.20 → bid + $0.00 (join queue)
    spread $0.21-$0.50 → bid + $0.10
    spread $0.51-$1.00 → bid + $0.20
    spread > $1.00 → bid + $0.30

SELL Logic:
    spread ≤ $0.20 → ask - $0.00 (join queue)
    spread $0.21-$0.50 → ask - $0.10
    spread $0.51-$1.00 → ask - $0.20
    spread > $1.00 → ask - $0.30

Usage:
    from strategies.pricing import PricingStrategy
    
    strategy = PricingStrategy(config)
    buy_price = strategy.calculate_buy_price(best_bid, best_ask)
    sell_price = strategy.calculate_sell_price(best_bid, best_ask)
"""

from typing import Dict, Any
from logger_config import setup_logger
from utils import round_price, format_price

logger = setup_logger(__name__)


class PricingStrategy:
    """
    Simple threshold-based market making pricing.
    
    Uses spread size (in dollars) to determine how much to improve bid/ask.
    No complex percentage calculations - just lookup table based on spread.
    
    Attributes:
        config: Configuration dictionary
        safety_margin: Minimum distance from opposite side (dollars)
        min_tick: Minimum price increment ($0.001)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Simple Pricing Strategy.
        
        Args:
            config: Configuration dictionary with pricing parameters
        
        Example:
            >>> config = {
            ...     'SPREAD_THRESHOLD_1': 0.20,
            ...     'SPREAD_THRESHOLD_2': 0.50,
            ...     'SPREAD_THRESHOLD_3': 1.00,
            ...     'IMPROVEMENT_TINY': 0.00,
            ...     'IMPROVEMENT_SMALL': 0.10,
            ...     'IMPROVEMENT_MEDIUM': 0.20,
            ...     'IMPROVEMENT_WIDE': 0.30,
            ...     'SAFETY_MARGIN_CENTS': 0.001
            ... }
            >>> strategy = PricingStrategy(config)
        """
        self.config = config
        
        # Extract thresholds from config
        self.threshold_1 = config.get('SPREAD_THRESHOLD_1', 0.20)
        self.threshold_2 = config.get('SPREAD_THRESHOLD_2', 0.50)
        self.threshold_3 = config.get('SPREAD_THRESHOLD_3', 1.00)
        
        # Extract improvements from config
        self.improvement_tiny = config.get('IMPROVEMENT_TINY', 0.00)
        self.improvement_small = config.get('IMPROVEMENT_SMALL', 0.10)
        self.improvement_medium = config.get('IMPROVEMENT_MEDIUM', 0.20)
        self.improvement_wide = config.get('IMPROVEMENT_WIDE', 0.30)
        
        # Safety settings
        self.safety_margin = config.get('SAFETY_MARGIN_CENTS', 0.001)
        self.min_tick = 0.001  # $0.001
        
        logger.debug(
            f"PricingStrategy initialized (SIMPLE THRESHOLD): "
            f"≤${self.threshold_1:.2f}→+${self.improvement_tiny:.2f}, "
            f"${self.threshold_1:.2f}-${self.threshold_2:.2f}→+${self.improvement_small:.2f}, "
            f"${self.threshold_2:.2f}-${self.threshold_3:.2f}→+${self.improvement_medium:.2f}, "
            f">${self.threshold_3:.2f}→+${self.improvement_wide:.2f}"
        )
    
    def _get_improvement_for_spread(self, spread: float) -> tuple[float, str]:
        """
        Determine improvement amount based on spread size.
        
        Args:
            spread: Spread in dollars (ask - bid)
            
        Returns:
            Tuple of (improvement_amount, category_name)
            
        Example:
            >>> strategy._get_improvement_for_spread(0.15)
            (0.00, 'TINY')
            >>> strategy._get_improvement_for_spread(0.35)
            (0.10, 'SMALL')
        """
        if spread <= self.threshold_1:
            return self.improvement_tiny, 'TINY'
        elif spread <= self.threshold_2:
            return self.improvement_small, 'SMALL'
        elif spread <= self.threshold_3:
            return self.improvement_medium, 'MEDIUM'
        else:
            return self.improvement_wide, 'WIDE'
    
    def calculate_buy_price(self, best_bid: float, best_ask: float) -> float:
        """
        Calculate BUY order price using simple threshold-based strategy.
        
        Strategy:
        1. Calculate spread (ask - bid)
        2. Look up improvement amount based on spread
        3. price = best_bid + improvement
        4. Safety checks: don't cross ask, stay above bid
        
        Args:
            best_bid: Current best bid price
            best_ask: Current best ask price
            
        Returns:
            Calculated BUY price (rounded to 3 decimals)
            
        Raises:
            ValueError: If best_bid >= best_ask (crossed book)
            
        Example:
            >>> # Tiny spread: bid=$0.500, ask=$0.515 ($0.15 spread)
            >>> strategy.calculate_buy_price(0.500, 0.515)
            0.500  # $0.500 + $0.00 = $0.500 (join queue)
            
            >>> # Wide spread: bid=$0.476, ask=$1.50 ($1.024 spread)
            >>> strategy.calculate_buy_price(0.476, 1.50)
            0.776  # $0.476 + $0.30 = $0.776
        """
        # Validate inputs
        if best_bid <= 0 or best_ask <= 0:
            raise ValueError(f"Invalid prices: bid={best_bid}, ask={best_ask}")
        
        if best_bid >= best_ask:
            raise ValueError(
                f"Crossed orderbook: bid ({best_bid}) >= ask ({best_ask})"
            )
        
        # Calculate spread in dollars
        spread = best_ask - best_bid
        
        # Get improvement based on spread
        improvement, category = self._get_improvement_for_spread(spread)
        
        # Calculate price: bid + improvement
        price = best_bid + improvement
        
        # Safety check 1: If improvement is 0, ensure we're at least 1 tick above bid
        # (otherwise we won't improve queue position)
        if improvement == 0:
            # For tiny spreads, we join the queue at exactly best_bid
            # No adjustment needed - we want to be AT best_bid
            pass
        else:
            # For other cases, ensure we're visibly better
            if price - best_bid < self.min_tick:
                price = best_bid + self.min_tick
                logger.debug(f"   Adjusted to minimum tick above bid: {format_price(price)}")
        
        # Safety check 2: Don't cross the ask
        max_safe_price = best_ask - self.safety_margin
        
        if price >= max_safe_price:
            logger.warning(
                f"⚠️  Calculated BUY price {format_price(price)} "
                f"would cross ask {format_price(best_ask)}"
            )
            price = max_safe_price
            logger.warning(f"   Adjusted to safe price: {format_price(price)}")
        
        # Round to standard precision (3 decimals)
        price = round_price(price)
        
        logger.debug(
            f"BUY price ({category} spread ${spread:.2f}): "
            f"bid={format_price(best_bid)} + ${improvement:.2f} = {format_price(price)}"
        )
        
        return price
    
    def calculate_sell_price(self, best_bid: float, best_ask: float) -> float:
        """
        Calculate SELL order price using simple threshold-based strategy.
        
        Strategy:
        1. Calculate spread (ask - bid)
        2. Look up improvement amount based on spread
        3. price = best_ask - improvement
        4. Safety checks: don't cross bid, stay below ask
        
        Args:
            best_bid: Current best bid price
            best_ask: Current best ask price
            
        Returns:
            Calculated SELL price (rounded to 3 decimals)
            
        Raises:
            ValueError: If best_bid >= best_ask (crossed book)
            
        Example:
            >>> # Tiny spread: bid=$0.500, ask=$0.515 ($0.15 spread)
            >>> strategy.calculate_sell_price(0.500, 0.515)
            0.515  # $0.515 - $0.00 = $0.515 (join queue)
            
            >>> # Wide spread: bid=$0.476, ask=$1.50 ($1.024 spread)
            >>> strategy.calculate_sell_price(0.476, 1.50)
            1.200  # $1.50 - $0.30 = $1.20
        """
        # Validate inputs
        if best_bid <= 0 or best_ask <= 0:
            raise ValueError(f"Invalid prices: bid={best_bid}, ask={best_ask}")
        
        if best_bid >= best_ask:
            raise ValueError(
                f"Crossed orderbook: bid ({best_bid}) >= ask ({best_ask})"
            )
        
        # Calculate spread in dollars
        spread = best_ask - best_bid
        
        # Get improvement based on spread
        improvement, category = self._get_improvement_for_spread(spread)
        
        # Calculate price: ask - improvement
        price = best_ask - improvement
        
        # Safety check 1: If improvement is 0, ensure we're at exactly best_ask
        if improvement == 0:
            # For tiny spreads, we join the queue at exactly best_ask
            # No adjustment needed
            pass
        else:
            # For other cases, ensure we're visibly better
            if best_ask - price < self.min_tick:
                price = best_ask - self.min_tick
                logger.debug(f"   Adjusted to minimum tick below ask: {format_price(price)}")
        
        # Safety check 2: Don't cross the bid
        min_safe_price = best_bid + self.safety_margin
        
        if price <= min_safe_price:
            logger.warning(
                f"⚠️  Calculated SELL price {format_price(price)} "
                f"would cross bid {format_price(best_bid)}"
            )
            price = min_safe_price
            logger.warning(f"   Adjusted to safe price: {format_price(price)}")
        
        # Round to standard precision (3 decimals)
        price = round_price(price)
        
        logger.debug(
            f"SELL price ({category} spread ${spread:.2f}): "
            f"ask={format_price(best_ask)} - ${improvement:.2f} = {format_price(price)}"
        )
        
        return price


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("=== Pricing Strategy Test ===\n")
    
    # Mock config
    config = {
        'SPREAD_THRESHOLD_1': 0.20,
        'SPREAD_THRESHOLD_2': 0.50,
        'SPREAD_THRESHOLD_3': 1.00,
        'IMPROVEMENT_TINY': 0.00,
        'IMPROVEMENT_SMALL': 0.10,
        'IMPROVEMENT_MEDIUM': 0.20,
        'IMPROVEMENT_WIDE': 0.30,
        'SAFETY_MARGIN_CENTS': 0.001
    }
    
    strategy = PricingStrategy(config)
    
    # Test cases
    test_cases = [
        (0.500, 0.515, "Tiny spread ($0.015)"),
        (0.476, 0.500, "SMALL spread ($0.024)"),
        (0.300, 0.400, "SMALL spread ($0.10)"),
        (0.200, 0.750, "MEDIUM spread ($0.55)"),
        (0.100, 0.900, "MEDIUM spread ($0.80)"),
        (0.476, 1.500, "WIDE spread ($1.024)"),
    ]
    
    print("BUY PRICES:")
    print("-" * 60)
    for bid, ask, desc in test_cases:
        buy_price = strategy.calculate_buy_price(bid, ask)
        spread = ask - bid
        print(f"{desc}")
        print(f"  Bid: ${bid:.3f}, Ask: ${ask:.3f}, Spread: ${spread:.3f}")
        print(f"  BUY: ${buy_price:.3f}\n")
    
    print("\nSELL PRICES:")
    print("-" * 60)
    for bid, ask, desc in test_cases:
        sell_price = strategy.calculate_sell_price(bid, ask)
        spread = ask - bid
        print(f"{desc}")
        print(f"  Bid: ${bid:.3f}, Ask: ${ask:.3f}, Spread: ${spread:.3f}")
        print(f"  SELL: ${sell_price:.3f}\n")