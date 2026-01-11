"""
Opinion Farming Bot - Order Manager Module
==========================================

Handles all order-related operations:
- Price calculation with randomization
- Order placement (BUY/SELL)
- Order monitoring
- Competition detection
- Re-pricing logic

Pricing Strategy:
- BUY: Position calculated FROM bid going UP toward ask
- SELL: Position calculated FROM ask going DOWN toward bid
- Randomization prevents predictable bot behavior
"""

import random
import time
from typing import Optional
from decimal import Decimal

from config_loader import config
from logger_config import setup_logger

FILL_CHECK_INTERVAL_SECONDS = config.FILL_CHECK_INTERVAL_SECONDS
ORDER_MONITOR_INTERVAL_SECONDS = config.ORDER_MONITOR_INTERVAL_SECONDS
CAPITAL_MODE = config.CAPITAL_MODE
CAPITAL_AMOUNT_USDT = config.CAPITAL_AMOUNT_USDT
CAPITAL_PERCENTAGE = config.CAPITAL_PERCENTAGE
from utils import (
    round_price,
    format_price,
    format_percent,
    safe_float,
    save_state,
    load_state,
    get_timestamp
)
from api_client import OpinionClient

# Initialize logger
logger = setup_logger(__name__)


class OrderManager:
    """
    Manages order lifecycle from calculation to fill.
    
    Usage:
        manager = OrderManager(client)
        price = manager.calculate_buy_price(best_bid, best_ask)
        result = manager.place_buy(market_id, token_id, price, amount)
        filled = manager.wait_for_fill(order_id)
    """
    
    def __init__(self, client: OpinionClient):
        """
        Initialize order manager with Opinion client.
        
        Args:
            client: Configured OpinionClient instance
        """
        self.client = client
    
    # =========================================================================
    # PRICE CALCULATION
    # =========================================================================
                
    def calculate_order_amount(self) -> float:
        """
        Calculate order amount based on capital configuration.
        
        Returns:
            Amount in USDT to use for order
        
        Logic:
            1. Get current balance from API
            2. Limit to CAPITAL_AMOUNT_USDT (safety cap)
            3. Apply percentage if CAPITAL_MODE='percentage'
        """
        # Get current balance
        current_balance = self.client.get_usdt_balance()
        
        # Limit to configured capital amount (never exceed this)
        available_capital = min(CAPITAL_AMOUNT_USDT, current_balance)
        
        # Apply capital mode
        if CAPITAL_MODE == 'percentage':
            amount = available_capital * (CAPITAL_PERCENTAGE / 100)
            logger.debug(
                f"Order amount: {amount:.2f} USDT "
                f"({CAPITAL_PERCENTAGE}% of {available_capital:.2f} available capital, "
                f"capped at {CAPITAL_AMOUNT_USDT:.2f})"
            )
        elif CAPITAL_MODE == 'fixed':
            amount = available_capital
            logger.debug(
                f"Order amount: {amount:.2f} USDT "
                f"(fixed mode, capped at {CAPITAL_AMOUNT_USDT:.2f})"
            )
        else:
            raise ValueError(f"Invalid CAPITAL_MODE: {CAPITAL_MODE}")
        
        return amount
    
    # =========================================================================
    # ORDER PLACEMENT
    # =========================================================================
    
    def place_buy(
        self,
        market_id: int,
        token_id: str,
        price: float,
        amount_usdt: float
    ) -> Optional[dict]:
        """
        Place a BUY limit order.
        
        Args:
            market_id: Market ID
            token_id: YES token ID
            price: Limit price
            amount_usdt: Amount in USDT
            
        Returns:
            Order result dict with order_id, or None on failure
        """
        logger.info(f"📤 Placing BUY order on market #{market_id}")
        logger.info(f"   Price: {format_price(price)}")
        logger.info(f"   Amount: {amount_usdt:.2f} USDT")
                      
        # VALIDATION: Check USDT balance before attempting order
        logger.info(f"🔰 Checking USDT balance...")
        current_balance = self.client.get_usdt_balance()
        
        if current_balance < amount_usdt:
            logger.error(f"❌ Insufficient USDT balance!")
            logger.error(f"   Available: {current_balance:.2f} USDT")
            logger.error(f"   Required: {amount_usdt:.2f} USDT")
            logger.error(f"   Shortage: {amount_usdt - current_balance:.2f} USDT")
            logger.error(f"")
            logger.error(f"Please deposit at least {amount_usdt - current_balance:.2f} USDT to your wallet")
            return None
        
        logger.info(f"   ✓ Balance OK: {current_balance:.2f} USDT available")
        logger.info("")
        
        result = self.client.place_buy_order(
            market_id=market_id,
            token_id=token_id,
            price=price,
            amount_usdt=amount_usdt,
            check_approval=False
        )
        
        if result:
            order_id = result.get('order_id', 'unknown')
            logger.info(f"✅ BUY order placed: {order_id}")
        
        return result
    
    def place_sell(
        self,
        market_id: int,
        token_id: str,
        price: float,
        amount_tokens: float,
        outcome_side: str = "YES"
    ) -> Optional[dict]:
        """
        Place a SELL limit order.

        Args:
            market_id: Market ID
            token_id: Token ID (YES or NO)
            price: Limit price
            amount_tokens: Amount of tokens to sell
            outcome_side: Which side we're selling ("YES" or "NO")

        Returns:
            Order result dict with order_id, or None on failure
        """
        logger.info(f"📤 Placing SELL order on market #{market_id}")
        logger.info(f"   Price: {format_price(price)}")
        logger.info(f"   Amount: {amount_tokens:.4f} tokens (requested)")
        
        # =====================================================================
        # CHECK ACTUAL TOKEN BALANCE FROM POSITIONS
        # =====================================================================
        # Shares (YES/NO tokens) are NOT in get_token_balance() endpoint!
        # They must be retrieved from get_my_positions() which returns PositionData
        # with shares_owned field.
        
        try:
            # RETRY LOGIC: API may need time to update position after fill
            actual_balance = 0.0
            max_retries = 3

            # Use the outcome_side parameter to check the correct position
            outcome_side_upper = outcome_side.upper()
            logger.debug(f"   Checking {outcome_side_upper} position for market #{market_id}")

            for attempt in range(1, max_retries + 1):
                # Check the specific outcome_side we're selling
                balance_decimal = self.client.get_position_shares(
                    market_id=market_id,
                    outcome_side=outcome_side_upper
                )
                actual_balance = float(balance_decimal) if balance_decimal else 0.0

                if actual_balance > 0:
                    logger.info(f"✅ Position found on attempt {attempt}: {actual_balance:.10f} {outcome_side_upper} tokens")
                    break
                else:
                    if attempt < max_retries:
                        logger.warning(f"⚠️ Attempt {attempt}/{max_retries}: No {outcome_side_upper} position found, retrying in 2 seconds...")
                        import time
                        time.sleep(2)
                    else:
                        logger.error(f"❌ After {max_retries} attempts, still no {outcome_side_upper} position found!")

            logger.debug(f"   Position shares ({outcome_side_upper}): {actual_balance:.10f}")
            
            # FALLBACK: If API returns 0, use requested amount
            if actual_balance == 0 and amount_tokens > 0:
                logger.warning(f"⚠️ API returned 0 shares but we expect {amount_tokens:.4f}")
                logger.warning(f"   Using requested amount as fallback")
                actual_balance = amount_tokens
            
            # Compare requested vs available
            if amount_tokens > actual_balance:
                difference = amount_tokens - actual_balance
                difference_pct = (difference / amount_tokens) * 100
                
                logger.warning(f"⚠️  Requested {amount_tokens:.4f} tokens")
                logger.warning(f"   Available: {actual_balance:.4f} tokens")
                logger.warning(f"   Difference: {difference:.4f} ({difference_pct:.2f}%)")
                
                # If difference is small (<5%), use actual balance
                # If difference is large, this might indicate a problem
                if difference_pct < 5.0:
                    logger.warning(f"   Difference is small ({difference_pct:.2f}%), adjusting to actual balance")
                    amount_tokens = actual_balance
                else:
                    logger.error(f"   ❌ Difference is too large ({difference_pct:.2f}%)!")
                    logger.error(f"   This might indicate a problem with fill data")
                    logger.warning(f"   Using actual balance anyway to avoid order failure")
                    amount_tokens = actual_balance
            else:
                logger.debug(f"   ✓ Sufficient balance ({actual_balance:.4f} >= {amount_tokens:.4f})")
        
        except AttributeError:
            # get_token_balance() doesn't exist in API client
            logger.debug("   Token balance check not available (API limitation)")
            logger.debug("   Using requested amount - may fail if insufficient")
        
        except Exception as e:
            # Other error (network, API down, etc)
            logger.warning(f"⚠️  Could not verify token balance: {e}")
            logger.warning(f"   Using requested amount - may fail if insufficient")
        
        logger.info(f"   Amount: {amount_tokens:.4f} tokens (final)")
        
        result = self.client.place_sell_order(
            market_id=market_id,
            token_id=token_id,
            price=price,
            amount_tokens=amount_tokens,
            check_approval=True
        )
        
        if result:
            order_id = result.get('order_id', 'unknown')
            logger.info(f"✅ SELL order placed: {order_id}")
        
        return result
    
    # =========================================================================
    # ORDER MONITORING
    # =========================================================================
    
    def wait_for_fill(
        self,
        order_id: str,
        check_interval: float = FILL_CHECK_INTERVAL_SECONDS,
        timeout: Optional[float] = None
    ) -> Optional[dict]:
        """
        Wait for an order to be filled.
        
        Args:
            order_id: Order ID to monitor
            check_interval: Seconds between status checks
            timeout: Maximum seconds to wait (None = wait forever)
            
        Returns:
            Order details dict when filled, or None if cancelled/timeout
        """
        logger.info(f"⏳ Monitoring order {order_id} for fill...")
        
        start_time = time.time()
        check_count = 0
        
        while True:
            check_count += 1
            
            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                logger.warning(f"Timeout waiting for fill after {timeout}s")
                return None
            
            # Get order status
            order = self.client.get_order(order_id)
            
            if not order:
                logger.error("Failed to fetch order status")
                return None
            
            status = order.get('status', 'unknown')
            
            if status == 'filled':
                filled_amount = safe_float(order.get('filled_amount', 0))
                avg_price = safe_float(order.get('average_price', 0))
                
                logger.info(f"✅ Order FILLED!")
                logger.info(f"   Filled amount: {filled_amount:.4f} tokens")
                logger.info(f"   Average price: {format_price(avg_price)}")
                
                return order
            
            elif status in ['cancelled', 'expired']:
                logger.warning(f"❌ Order {status}")
                return None
            
            else:
                # Still pending
                if check_count % 5 == 0:  # Log every 5th check
                    logger.info(f"⏳ Order still pending... (check #{check_count})")
            
            time.sleep(check_interval)     
    

# =============================================================================
# STATE MANAGEMENT HELPERS
# =============================================================================

def create_buy_state(
    market_id: int,
    order_id: str,
    token_id: str,
    price: float,
    position_percent: float,
    amount_usdt: float
) -> dict:
    """
    Create state dictionary for a new BUY order.
    
    Args:
        market_id: Market ID
        order_id: Order ID from placement
        token_id: YES token ID
        price: Order price
        position_percent: Position percentage used
        amount_usdt: Order amount
        
    Returns:
        State dictionary ready for save_state()
    """
    return {
        "stage": "BUY_PLACED",
        "market_id": market_id,
        "order_id": order_id,
        "token_id": token_id,
        "initial_price": price,
        "current_price": price,
        "position_percent": position_percent,
        "side": "BUY",
        "amount_usdt": amount_usdt,
        "repricing_count": 0,
        "filled_amount": None,
        "avg_fill_price": None,
        "timestamp": get_timestamp()
    }


def update_state_for_fill(state: dict, order: dict) -> dict:
    """
    Update state after order is filled.
    
    Args:
        state: Current state dictionary
        order: Filled order data from API
        
    Returns:
        Updated state dictionary
    """
    state["stage"] = "BUY_FILLED" if state.get("side") == "BUY" else "SELL_FILLED"
    # API returns filled_shares (tokens), not filled_amount (USDT)
    state["filled_amount"] = safe_float(order.get("filled_shares", 0))
    # API returns price, not average_price
    state["avg_fill_price"] = safe_float(order.get("price", 0))
    state["fill_timestamp"] = get_timestamp()
    return state


def update_state_for_reprice(state: dict, new_order_id: str, new_price: float) -> dict:
    """
    Update state after re-pricing.
    
    Args:
        state: Current state dictionary
        new_order_id: New order ID
        new_price: New order price
        
    Returns:
        Updated state dictionary
    """
    state["order_id"] = new_order_id
    state["current_price"] = new_price
    state["repricing_count"] = state.get("repricing_count", 0) + 1
    state["last_reprice_timestamp"] = get_timestamp()
    return state


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

# NOTE: place_initial_buy() removed - legacy code not used by autonomous_bot
# autonomous_bot uses PricingStrategy + OrderManager.place_buy() directly


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("=== Order Manager Module Test ===")
    print()
    
    # Test price calculations (no API needed)
    from api_client import OpinionClient
    
    # Create mock client for testing calculations
    class MockClient:
        pass
    
    manager = OrderManager(MockClient())
    
    # Test BUY price calculation
    print("Testing BUY price calculation:")
    print(f"   Bid: $0.4200, Ask: $0.5800")
    for i in range(3):
        price = manager.calculate_buy_price(0.42, 0.58)
        print(f"   Run {i+1}: {format_price(price)}")
    
    print()
    
    # Test SELL price calculation
    print("Testing SELL price calculation:")
    print(f"   Bid: $0.4200, Ask: $0.5800")
    for i in range(3):
        price = manager.calculate_sell_price(0.42, 0.58)
        print(f"   Run {i+1}: {format_price(price)}")
    
    print()
    
    # Test reprice calculation
    print("Testing re-price calculation:")
    initial = 0.5732
    new_bid = 0.5765
    new_ask = 0.5800
    
    for i in range(3):
        new_price = manager.calculate_reprice(initial, new_bid, new_ask, i)
        print(f"   Repricing #{i+1}: {format_price(new_price)}")
    
    
    print()
    print("✅ Order manager calculation tests complete!")
