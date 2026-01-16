"""
Opinion Farming Bot - Position Tracker Module
=============================================

Handles position tracking and P&L calculations.
Uses Decimal for all financial calculations to ensure accuracy.

P&L Calculation:
    buy_cost = amount_usdt (what we spent)
    sell_proceeds = filled_tokens × sell_price (what we received)
    pnl = sell_proceeds - buy_cost
    pnl_percent = (pnl / buy_cost) × 100
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from dataclasses import dataclass

from logger_config import setup_logger, log_pnl_summary
from utils import (
    safe_float,
    safe_decimal,
    format_usdt,
    format_price,
    format_pnl,
    format_percent
)

# Initialize logger
logger = setup_logger(__name__)


@dataclass
class PositionPnL:
    """
    Data class holding P&L calculation results.

    Attributes:
        buy_tokens: Number of tokens bought
        buy_price: Average buy price per token
        buy_cost: Cost of SOLD tokens (for P&L calculation)
        total_buy_cost: Total cost of ALL bought tokens (informational)
        sell_tokens: Number of tokens sold
        sell_price: Average sell price per token
        sell_proceeds: Total proceeds in USDT
        pnl: Net profit/loss in USDT
        pnl_percent: Profit/loss as percentage
        duration_seconds: Time position was open (optional)
    """
    buy_tokens: Decimal
    buy_price: Decimal
    buy_cost: Decimal  # Cost of sold tokens only
    total_buy_cost: Decimal  # Total cost of all bought tokens
    sell_tokens: Decimal
    sell_price: Decimal
    sell_proceeds: Decimal
    pnl: Decimal
    pnl_percent: Decimal
    duration_seconds: Optional[float] = None

    def is_profitable(self) -> bool:
        """Check if position was profitable."""
        return self.pnl > 0

    def is_partial_sell(self) -> bool:
        """Check if this was a partial sell (didn't sell all bought tokens)."""
        return self.sell_tokens < self.buy_tokens

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/display."""
        return {
            'buy_tokens': float(self.buy_tokens),
            'buy_price': float(self.buy_price),
            'buy_cost': float(self.buy_cost),
            'total_buy_cost': float(self.total_buy_cost),
            'sell_tokens': float(self.sell_tokens),
            'sell_price': float(self.sell_price),
            'sell_proceeds': float(self.sell_proceeds),
            'pnl': float(self.pnl),
            'pnl_percent': float(self.pnl_percent),
            'duration_seconds': self.duration_seconds,
            'is_partial_sell': self.is_partial_sell()
        }


class PositionTracker:
    """
    Tracks positions and calculates P&L.
    
    Usage:
        tracker = PositionTracker()
        pnl = tracker.calculate_pnl(buy_state, sell_order)
        tracker.display_pnl(pnl)
    """
    
    def __init__(self):
        """Initialize position tracker."""
        self.positions = []  # History of positions (for future analytics)
    
    def calculate_pnl(
        self,
        buy_cost_usdt: float,
        buy_tokens: float,
        buy_price: float,
        sell_tokens: float,
        sell_price: float
    ) -> PositionPnL:
        """
        Calculate P&L for a completed position.
        
        Args:
            buy_cost_usdt: Total USDT spent on buy
            buy_tokens: Number of tokens bought
            buy_price: Average buy price per token
            sell_tokens: Number of tokens sold
            sell_price: Average sell price per token
            
        Returns:
            PositionPnL object with all calculations
            
        Example:
            >>> pnl = tracker.calculate_pnl(
            ...     buy_cost_usdt=1000,
            ...     buy_tokens=1723.54,
            ...     buy_price=0.5804,
            ...     sell_tokens=1723.54,
            ...     sell_price=0.6121
            ... )
            >>> print(f"P&L: ${pnl.pnl:.2f} ({pnl.pnl_percent:.2f}%)")
        """
        # Convert to Decimal for precision
        d_buy_cost = safe_decimal(buy_cost_usdt)
        d_buy_tokens = safe_decimal(buy_tokens)
        d_buy_price = safe_decimal(buy_price)
        d_sell_tokens = safe_decimal(sell_tokens)
        d_sell_price = safe_decimal(sell_price)

        # Calculate sell proceeds
        d_sell_proceeds = d_sell_tokens * d_sell_price

        # CRITICAL: Calculate cost of SOLD tokens only (not all bought tokens)
        # This is crucial for partial sells!
        # Example: bought 488 tokens for $376.75, sold only 183 tokens
        # -> Cost of sold tokens = 183 * $0.7720 = $141.42 (not $376.75!)
        d_cost_of_sold_tokens = d_sell_tokens * d_buy_price

        # Calculate P&L based on sold tokens only
        d_pnl = d_sell_proceeds - d_cost_of_sold_tokens

        # Calculate percentage based on cost of sold tokens (not total buy cost)
        if d_cost_of_sold_tokens > 0:
            d_pnl_percent = (d_pnl / d_cost_of_sold_tokens) * Decimal('100')
        else:
            d_pnl_percent = Decimal('0')
        
        # Round for display
        d_pnl = d_pnl.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        d_pnl_percent = d_pnl_percent.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        d_sell_proceeds = d_sell_proceeds.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        d_cost_of_sold_tokens = d_cost_of_sold_tokens.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        return PositionPnL(
            buy_tokens=d_buy_tokens,
            buy_price=d_buy_price,
            buy_cost=d_cost_of_sold_tokens,  # Cost of sold tokens (used in P&L calculation)
            total_buy_cost=d_buy_cost,  # Total cost of all bought tokens (informational)
            sell_tokens=d_sell_tokens,
            sell_price=d_sell_price,
            sell_proceeds=d_sell_proceeds,
            pnl=d_pnl,
            pnl_percent=d_pnl_percent
        )
    
    def calculate_pnl_from_state(self, state: dict, sell_order: dict) -> PositionPnL:
        """
        Calculate P&L from state dictionary and sell order data.
        
        Convenience method that extracts values from typical state/order format.
        
        Args:
            state: Bot state dictionary with buy info
            sell_order: Sell order response with fill info
            
        Returns:
            PositionPnL object
        """
        return self.calculate_pnl(
            buy_cost_usdt=safe_float(state.get('amount_usdt', 0)),
            buy_tokens=safe_float(state.get('filled_amount', 0)),
            buy_price=safe_float(state.get('avg_fill_price', 0)),
            sell_tokens=safe_float(sell_order.get('filled_amount', 0)),
            sell_price=safe_float(sell_order.get('average_price', 0))
        )
    
    def display_pnl(self, pnl: PositionPnL):
        """
        Display P&L summary in formatted output.
        
        Args:
            pnl: PositionPnL object to display
        """
        log_pnl_summary(logger, pnl.to_dict())
    
    def log_pnl_inline(self, pnl: PositionPnL):
        """
        Log P&L in a single-line format (for compact output).

        Args:
            pnl: PositionPnL object to log
        """
        pnl_sign = "+" if pnl.pnl >= 0 else ""
        emoji = "💰" if pnl.pnl >= 0 else "📉"

        # For partial sells, show both cost of sold tokens and total cost
        cost_str = f"{format_usdt(float(pnl.buy_cost))}"
        if pnl.is_partial_sell():
            cost_str = f"{format_usdt(float(pnl.buy_cost))} of {format_usdt(float(pnl.total_buy_cost))}"

        logger.info(
            f"{emoji} POSITION CLOSED | "
            f"Cost: {cost_str} | "
            f"Proceeds: {format_usdt(float(pnl.sell_proceeds))} | "
            f"P&L: {pnl_sign}{float(pnl.pnl):.2f} USDT ({pnl_sign}{float(pnl.pnl_percent):.2f}%)"
        )
    
    def add_to_history(self, pnl: PositionPnL, market_id: int):
        """
        Add completed position to history (for analytics).
        
        Args:
            pnl: PositionPnL object
            market_id: Market ID where position was held
        """
        record = {
            'market_id': market_id,
            **pnl.to_dict()
        }
        self.positions.append(record)
    
    def get_total_pnl(self) -> Decimal:
        """
        Get total P&L across all positions in history.
        
        Returns:
            Sum of all P&L in USDT
        """
        total = Decimal('0')
        for pos in self.positions:
            total += safe_decimal(pos.get('pnl', 0))
        return total
    
    def get_win_rate(self) -> float:
        """
        Calculate win rate (percentage of profitable trades).
        
        Returns:
            Win rate as percentage (0-100)
        """
        if not self.positions:
            return 0.0
        
        wins = sum(1 for p in self.positions if safe_float(p.get('pnl', 0)) > 0)
        return (wins / len(self.positions)) * 100
    
    def display_session_summary(self):
        """
        Display summary of all positions in current session.
        """
        if not self.positions:
            logger.info("No positions recorded in this session")
            return
        
        total_pnl = self.get_total_pnl()
        win_rate = self.get_win_rate()
        num_trades = len(self.positions)
        
        pnl_sign = "+" if total_pnl >= 0 else ""
        
        logger.info("")
        logger.info("=" * 50)
        logger.info("SESSION SUMMARY".center(50))
        logger.info("=" * 50)
        logger.info(f"   Total trades: {num_trades}")
        logger.info(f"   Win rate: {win_rate:.1f}%")
        logger.info(f"   Total P&L: {pnl_sign}{float(total_pnl):.2f} USDT")
        logger.info("=" * 50)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def calculate_simple_pnl(buy_cost: float, sell_proceeds: float) -> tuple[float, float]:
    """
    Simple P&L calculation without full tracking.
    
    Args:
        buy_cost: What we spent
        sell_proceeds: What we received
        
    Returns:
        Tuple of (pnl_usdt, pnl_percent)
    """
    pnl = sell_proceeds - buy_cost
    pnl_pct = (pnl / buy_cost * 100) if buy_cost > 0 else 0
    return (pnl, pnl_pct)


def estimate_tokens_for_usdt(usdt_amount: float, price: float) -> float:
    """
    Estimate number of tokens for a given USDT amount and price.
    
    Args:
        usdt_amount: Amount in USDT
        price: Price per token
        
    Returns:
        Estimated number of tokens
    """
    if price <= 0:
        return 0.0
    return usdt_amount / price


def estimate_proceeds(tokens: float, price: float) -> float:
    """
    Estimate USDT proceeds for selling tokens at a price.
    
    Args:
        tokens: Number of tokens to sell
        price: Price per token
        
    Returns:
        Estimated USDT proceeds
    """
    return tokens * price


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("=== Position Tracker Module Test ===")
    print()
    
    tracker = PositionTracker()
    
    # Test P&L calculation (profitable trade)
    print("Test 1: Profitable trade")
    pnl1 = tracker.calculate_pnl(
        buy_cost_usdt=1000,
        buy_tokens=1723.54,
        buy_price=0.5804,
        sell_tokens=1723.54,
        sell_price=0.6121
    )
    
    print(f"   Buy: {pnl1.buy_tokens:.4f} tokens @ ${pnl1.buy_price:.4f} = ${pnl1.buy_cost:.2f}")
    print(f"   Sell: {pnl1.sell_tokens:.4f} tokens @ ${pnl1.sell_price:.4f} = ${pnl1.sell_proceeds:.2f}")
    print(f"   P&L: ${pnl1.pnl:+.2f} ({pnl1.pnl_percent:+.2f}%)")
    print(f"   Profitable: {pnl1.is_profitable()}")
    print()
    
    # Test P&L calculation (losing trade)
    print("Test 2: Losing trade")
    pnl2 = tracker.calculate_pnl(
        buy_cost_usdt=1000,
        buy_tokens=1694.92,
        buy_price=0.59,
        sell_tokens=1694.92,
        sell_price=0.55
    )
    
    print(f"   Buy: {pnl2.buy_tokens:.4f} tokens @ ${pnl2.buy_price:.4f} = ${pnl2.buy_cost:.2f}")
    print(f"   Sell: {pnl2.sell_tokens:.4f} tokens @ ${pnl2.sell_price:.4f} = ${pnl2.sell_proceeds:.2f}")
    print(f"   P&L: ${pnl2.pnl:+.2f} ({pnl2.pnl_percent:+.2f}%)")
    print(f"   Profitable: {pnl2.is_profitable()}")
    print()
    
    # Test history tracking
    print("Test 3: Session tracking")
    tracker.add_to_history(pnl1, market_id=813)
    tracker.add_to_history(pnl2, market_id=914)
    
    print(f"   Total P&L: ${tracker.get_total_pnl():.2f}")
    print(f"   Win rate: {tracker.get_win_rate():.1f}%")
    print()
    
    # Test estimation functions
    print("Test 4: Estimation functions")
    tokens = estimate_tokens_for_usdt(1000, 0.58)
    print(f"   1000 USDT at $0.58 = {tokens:.2f} tokens")
    
    proceeds = estimate_proceeds(1724, 0.61)
    print(f"   1724 tokens at $0.61 = ${proceeds:.2f}")
    
    print()
    print("✅ Position tracker tests complete!")
