"""
SELL Monitor Module
===================

Monitors SELL order until filled, cancelled, expired, timeout, or stop-loss triggered.

Key responsibilities:
- Poll order status at regular intervals
- Detect fill, cancellation, expiration, timeout
- **NEW: Stop-loss protection** - cancel and place aggressive limit if losing too much
- Periodic liquidity checks (every 5th iteration)
- Extract fill data from order or trades fallback
- Return structured result dict

Extracted from mvp_stage4.py with stop-loss enhancement.

Usage:
    from monitoring.sell_monitor import SellMonitor
    
    monitor = SellMonitor(config, client, state)
    result = monitor.monitor_until_filled(order_id, timeout_at)
    
    if result['status'] == 'filled':
        print(f"Sold {result['filled_amount']} tokens at {result['avg_fill_price']}")
    elif result['status'] == 'stop_loss_triggered':
        print("Stop-loss activated - position closed at loss")
"""

import time
from typing import Dict, Any, Tuple
from datetime import datetime, timedelta
from logger_config import setup_logger
from utils import safe_float, format_price, format_percent, round_price, get_timestamp, interruptible_sleep
from monitoring.liquidity_checker import LiquidityChecker

logger = setup_logger(__name__)


class SellMonitor:
    """
    Monitors SELL order status with stop-loss protection.
    
    Attributes:
        config: Configuration dictionary
        client: API client instance
        state: Current bot state dictionary
        liquidity_checker: LiquidityChecker instance
    """
    
    def __init__(self, config: Dict[str, Any], client, state: Dict[str, Any], heartbeat_callback=None):
        """
        Initialize SELL Monitor.

        Args:
            config: Configuration dictionary
            client: OpinionClient instance
            state: Current state dictionary (must have buy_price, filled_amount)
            heartbeat_callback: Optional callback function to send heartbeat notifications

        Example:
            >>> monitor = SellMonitor(config, client, state)
        """
        self.config = config
        self.client = client
        self.state = state
        self.heartbeat_callback = heartbeat_callback

        # Initialize liquidity checker
        self.liquidity_checker = LiquidityChecker(config, client)

        # Extract config values
        self.check_interval = config['FILL_CHECK_INTERVAL_SECONDS']
        self.timeout_hours = config['SELL_ORDER_TIMEOUT_HOURS']
        self.enable_stop_loss = config.get('ENABLE_STOP_LOSS', True)
        self.stop_loss_trigger = config.get('STOP_LOSS_TRIGGER_PERCENT', -10.0)
        self.stop_loss_offset = config.get('STOP_LOSS_AGGRESSIVE_OFFSET', 0.001)
        self.stop_loss_spread_filter = config.get('STOP_LOSS_SPREAD_FILTER_PCT', 10.0)
        self.stop_loss_confirmation_checks = config.get('STOP_LOSS_CONFIRMATION_CHECKS', 3)

        # Track consecutive bad price checks for confirmation delay
        self.bad_price_streak = 0

        # Sell order repricing config
        self.enable_repricing = config.get('ENABLE_SELL_ORDER_REPRICING', True)
        self.reprice_threshold_pct = config.get('SELL_REPRICE_LIQUIDITY_THRESHOLD_PCT', 50.0)
        self.allow_below_buy = config.get('ALLOW_SELL_BELOW_BUY_PRICE', False)
        self.max_reduction_pct = config.get('MAX_SELL_PRICE_REDUCTION_PCT', 5.0)
        self.reprice_mode = config.get('SELL_REPRICE_SCALE_MODE', 'best')
        self.liq_target_pct = config.get('SELL_REPRICE_LIQUIDITY_TARGET_PCT', 30.0)
        self.liq_return_pct = config.get('SELL_REPRICE_LIQUIDITY_RETURN_PCT', 20.0)
        self.enable_dynamic = config.get('ENABLE_DYNAMIC_SELL_PRICE_ADJUSTMENT', True)

        logger.debug(
            f"SellMonitor initialized: "
            f"check_interval={self.check_interval}s, "
            f"timeout={self.timeout_hours}h, "
            f"stop_loss={self.enable_stop_loss} ({self.stop_loss_trigger}%), "
            f"repricing={self.enable_repricing} (mode={self.reprice_mode}, threshold={self.reprice_threshold_pct}%)"
        )
    
    def monitor_until_filled(
        self,
        order_id: str
    ) -> Dict[str, Any]:
        """
        Monitor SELL order until filled, cancelled, expired, deteriorated, or stop-loss triggered.

        NOTE: SELL monitoring has NO timeout - orders stay active indefinitely for
        market making rewards. Only repricing and stop-loss can change/cancel orders.

        Args:
            order_id: Order ID to monitor

        Returns:
            Dictionary with structure:
            {
                'status': 'filled' | 'cancelled' | 'expired' | 'deteriorated',
                'filled_amount': float (tokens, if filled),
                'avg_fill_price': float (if filled),
                'filled_usdt': float (if filled),
                'fill_timestamp': str (if filled),
                'reason': str (if not filled)
            }

        Example:
            >>> result = monitor.monitor_until_filled('ord_456')
            >>> if result['status'] == 'filled':
            ...     print(f"Sold {result['filled_amount']} tokens")
        """
        logger.info("🔄 Starting SELL order monitoring")
        logger.info(f"   Order ID: {order_id}")
        logger.info(f"   Check interval: {self.check_interval}s")
        logger.info(f"   No timeout - order stays active until filled")
        if self.enable_stop_loss:
            logger.info(f"   Stop-loss: {format_percent(self.stop_loss_trigger)}")
        logger.info("")
        
        # Validate state has required fields in current_position
        position = self.state.get('current_position', {})
        required_fields = ['token_id', 'market_id', 'avg_fill_price', 'filled_amount']
        missing = [f for f in required_fields if not position.get(f)]
        if missing:
            error_msg = f"State missing required fields in current_position: {missing}"
            logger.error(f"❌ {error_msg}")
            return {
                'status': 'error',
                'filled_amount': None,
                'avg_fill_price': None,
                'filled_usdt': None,
                'fill_timestamp': None,
                'reason': error_msg
            }
        
        # Extract position info from state
        position = self.state.get('current_position', {})
        market_id = position.get('market_id')
        token_id = position.get('token_id')
        buy_price = safe_float(position.get('avg_fill_price', 0))
        filled_amount = safe_float(position.get('filled_amount', 0))
        sell_price = position.get('sell_price', 0)

        # CRITICAL: Validate and fix avg_fill_price if suspicious
        # This handles cases where state.json has 0.01$ from failed recovery
        if buy_price <= 0.02:  # Suspiciously low (0.01$ is clearly wrong)
            logger.warning(f"⚠️  avg_fill_price is suspiciously low: ${buy_price:.4f}")
            logger.info("   Attempting to recalculate from available data...")

            # Try to get price from orderbook
            recalculated = False
            try:
                orderbook = self.client.get_market_orderbook(token_id)
                if orderbook and 'bids' in orderbook:
                    bids = orderbook.get('bids', [])
                    if bids:
                        best_bid = max(safe_float(bid.get('price', 0)) for bid in bids)
                        if best_bid > 0:
                            logger.info(f"   Using current market bid as avg_fill_price: ${best_bid:.4f}")
                            buy_price = best_bid
                            position['avg_fill_price'] = best_bid
                            position['filled_usdt'] = filled_amount * best_bid

                            # Save corrected state
                            from core.state_manager import StateManager
                            state_file = self.config.get('STATE_FILE', 'state.json')
                            state_manager = StateManager(state_file)
                            state_manager.save_state(self.state)

                            logger.info(f"   ✅ Corrected avg_fill_price: ${buy_price:.4f}")
                            logger.warning(f"   ⚠️  P&L may still be inaccurate (estimate from current market)")
                            recalculated = True
            except Exception as e:
                logger.warning(f"   Could not get market price: {e}")

            if not recalculated:
                logger.warning("   ❌ Could not recalculate avg_fill_price")
                logger.warning("   Continuing with existing value - P&L will be VERY inaccurate")

        check_count = 0
        last_liquidity_check = 0
        LIQUIDITY_CHECK_INTERVAL = 5  # Check every 5th iteration
        
        try:
            while True:
                check_count += 1
                check_time = datetime.now().strftime("%H:%M:%S")

                # =============================================================
                # CHECK: STOP-LOSS (if enabled)
                # =============================================================
                if self.enable_stop_loss and check_count % 3 == 0:  # Check every 3rd iteration
                    should_stop, unrealized_loss_pct = self.check_stop_loss(buy_price)

                    if should_stop:
                        # Increment bad price streak counter
                        self.bad_price_streak += 1

                        logger.warning("")
                        logger.warning("=" * 70)
                        logger.warning("⚠️  STOP-LOSS THRESHOLD MET")
                        logger.warning("=" * 70)
                        logger.warning(f"   Buy price: {format_price(buy_price)}")
                        logger.warning(f"   Unrealized loss: {format_percent(unrealized_loss_pct)}")
                        logger.warning(f"   Threshold: {format_percent(self.stop_loss_trigger)}")
                        logger.warning(f"   Confirmation: {self.bad_price_streak}/{self.stop_loss_confirmation_checks} checks")
                        logger.warning("")

                        # Check if we've met the confirmation requirement
                        if self.bad_price_streak >= self.stop_loss_confirmation_checks:
                            logger.warning("=" * 70)
                            logger.warning("🛑 STOP-LOSS CONFIRMED - EXECUTING")
                            logger.warning("=" * 70)
                            logger.warning(f"   Sustained bad price for {self.bad_price_streak} consecutive checks")
                            logger.warning(f"   Triggering stop-loss exit")
                            logger.warning("")

                            # Execute stop-loss: cancel and place aggressive limit
                            result = self.execute_stop_loss(order_id)

                            if result.get('success'):
                                # Successfully placed aggressive order - continue monitoring it
                                new_order_id = result.get('new_order_id')
                                new_price = result.get('new_price')

                                logger.info("✅ Stop-loss executed successfully")
                                logger.info(f"   New aggressive order placed: {new_order_id}")
                                logger.info(f"   New price: {format_price(new_price)}")
                                logger.info("")

                                # Update tracking variables to monitor new order
                                order_id = new_order_id
                                sell_price = new_price

                                # Reset bad price streak for new order
                                self.bad_price_streak = 0

                                # CRITICAL: Continue monitoring the new order until it fills
                                # Do NOT return or reset position - order must fill first
                                logger.info("🔄 Continuing monitoring of aggressive stop-loss order...")
                                logger.info("")

                                # Continue the main monitoring loop with new order
                                continue

                            else:
                                # Stop-loss execution failed - continue monitoring original order
                                logger.error("❌ Stop-loss execution failed")
                                logger.error(f"   Reason: {result.get('reason', 'Unknown')}")
                                logger.warning("   Continuing to monitor original order")
                                logger.warning("")
                                # Keep bad price streak to retry next check
                        else:
                            # Not yet confirmed - need more consecutive bad checks
                            remaining_checks = self.stop_loss_confirmation_checks - self.bad_price_streak
                            logger.warning(f"   Waiting for {remaining_checks} more confirmation(s)...")
                            logger.warning(f"   Next check in {self.check_interval}s (check #{check_count + 1})")
                            logger.warning("=" * 70)
                            logger.warning("")

                    else:
                        # Price is OK or spread filter blocked check
                        # Reset bad price streak if it was previously set
                        if self.bad_price_streak > 0:
                            logger.info("")
                            logger.info("=" * 70)
                            logger.info("✅ PRICE RECOVERED - STOP-LOSS COUNTER RESET")
                            logger.info("=" * 70)
                            logger.info(f"   Previous bad streak: {self.bad_price_streak} check(s)")
                            logger.info(f"   Price is now above stop-loss threshold")
                            logger.info(f"   Counter reset to 0")
                            logger.info("=" * 70)
                            logger.info("")
                            self.bad_price_streak = 0
                
                # =============================================================
                # PERIODIC REPRICING CHECK
                # =============================================================
                REPRICING_CHECK_INTERVAL = 3  # Check every 3rd iteration
                if check_count % REPRICING_CHECK_INTERVAL == 0:
                    # Get current order price from API to ensure accuracy
                    try:
                        order_details = self.client.get_order(order_id)
                        if order_details:
                            current_order_price = safe_float(order_details.get('price', sell_price))
                        else:
                            current_order_price = sell_price
                    except:
                        current_order_price = sell_price

                    repricing_result = self.check_and_execute_repricing(order_id, current_order_price)

                    if repricing_result and repricing_result.get('status') == 'repriced':
                        # Order was repriced - update tracking variables
                        order_id = repricing_result.get('new_order_id')
                        sell_price = repricing_result.get('new_price')
                        logger.info(f"✅ Order repriced successfully, continuing monitoring with new order {order_id}")
                        # Continue monitoring the new order
                        continue

                # =============================================================
                # PERIODIC LIQUIDITY CHECK
                # =============================================================
                if check_count - last_liquidity_check >= LIQUIDITY_CHECK_INTERVAL:
                    logger.debug(f"[{check_time}] 🔍 Checking liquidity...")

                    # Get initial spread from state (stored when SELL order was placed)
                    initial_spread_pct = position.get('initial_spread_pct')
                    initial_best_bid = position.get('initial_best_bid', buy_price)

                    liquidity = self.liquidity_checker.check_liquidity(
                        market_id=market_id,
                        token_id=token_id,
                        initial_best_bid=initial_best_bid,
                        buy_price=buy_price,  # Use ACTUAL buy price for stop-loss calculation
                        initial_spread_pct=initial_spread_pct  # Check if spread WIDENED
                    )

                    if not liquidity['ok']:
                        logger.warning("")
                        logger.warning("=" * 50)
                        logger.warning("⚠️  LIQUIDITY DETERIORATED")
                        logger.warning("=" * 50)
                        logger.warning(f"   Reason: {liquidity['deterioration_reason']}")
                        logger.warning(f"   Current bid: {format_price(liquidity['current_best_bid'])}")
                        logger.warning(f"   Current spread: {format_percent(liquidity['current_spread_pct'])}")
                        logger.warning("")

                        # If auto-cancel enabled, return deteriorated status
                        if self.config.get('LIQUIDITY_AUTO_CANCEL', True):
                            logger.warning("   Auto-cancel enabled - exiting monitoring")
                            logger.warning("   Bot will cancel order and find new market")
                            logger.warning("")

                            return {
                                'status': 'deteriorated',
                                'filled_amount': None,
                                'avg_fill_price': None,
                                'filled_usdt': None,
                                'fill_timestamp': None,
                                'reason': liquidity['deterioration_reason']
                            }
                    else:
                        logger.debug(
                            f"[{check_time}] ✅ Liquidity OK - "
                            f"Bid: {format_price(liquidity['current_best_bid'])}, "
                            f"Spread: {format_percent(liquidity['current_spread_pct'])}"
                        )

                    last_liquidity_check = check_count

                # =============================================================
                # SEND HEARTBEAT IF CALLBACK PROVIDED
                # =============================================================
                if self.heartbeat_callback:
                    try:
                        self.heartbeat_callback()
                    except Exception as e:
                        logger.debug(f"Heartbeat callback failed: {e}")

                # =============================================================
                # GET ORDER STATUS
                # =============================================================
                order = self.client.get_order(order_id)

                if not order:
                    logger.warning(f"[{check_time}] ⚠️  Failed to fetch order status")
                    interruptible_sleep(self.check_interval)
                    continue
                
                status = order.get('status')  # int: 0=pending, 1=partial, 2=finished, 3=cancelled, 4=expired
                status_enum = order.get('status_enum', 'unknown')
                
                # =============================================================
                # CHECK: ORDER FILLED
                # =============================================================
                if status_enum == 'Finished' or status == 2:
                    logger.info("")
                    logger.info("=" * 50)
                    logger.info("✅ SELL ORDER FILLED!")
                    logger.info("=" * 50)
                    
                    # Extract fill data
                    filled_amount, avg_fill_price, filled_usdt = self._extract_fill_data(order)
                    
                    logger.info(f"   Sold: {filled_amount:.4f} YES tokens")
                    logger.info(f"   Avg price: {format_price(avg_fill_price)}")
                    logger.info(f"   Proceeds: ${filled_usdt:.2f}")
                    logger.info("")
                    
                    return {
                        'status': 'filled',
                        'filled_amount': filled_amount,
                        'avg_fill_price': avg_fill_price,
                        'filled_usdt': filled_usdt,
                        'fill_timestamp': get_timestamp(),
                        'reason': None
                    }
                
                # =============================================================
                # CHECK: PARTIAL FILL WITH DUST REMAINING
                # =============================================================
                # If order is partially filled and remaining < dust threshold,
                # cancel the order and proceed with filled amount
                filled_shares = safe_float(order.get('filled_shares', 0))
                order_shares = safe_float(order.get('order_shares', 0))

                if filled_shares > 0 and order_shares > 0:
                    remaining_shares = order_shares - filled_shares
                    dust_threshold = 5.0  # Same as config dust threshold

                    # Check if remaining is dust
                    if 0 < remaining_shares < dust_threshold:
                        logger.info("")
                        logger.info("=" * 70)
                        logger.warning("⚠️  PARTIAL FILL WITH DUST REMAINING")
                        logger.info("=" * 70)
                        logger.info(f"   Ordered: {order_shares:.4f} tokens")
                        logger.info(f"   Filled: {filled_shares:.4f} tokens")
                        logger.info(f"   Remaining: {remaining_shares:.4f} tokens (< {dust_threshold} dust threshold)")
                        logger.info("")
                        logger.info("   🎯 Strategy: Cancel remaining dust and proceed with filled amount")
                        logger.info("")

                        # Cancel the order to clear the remaining dust
                        try:
                            logger.info(f"   🧹 Cancelling order to clear dust...")
                            self.client.cancel_order(order_id)
                            logger.info(f"   ✅ Order cancelled")
                        except Exception as e:
                            logger.warning(f"   ⚠️  Could not cancel order: {e}")
                            logger.warning(f"   Proceeding anyway with filled amount")

                        # Extract fill data for the filled portion
                        filled_amount, avg_fill_price, filled_usdt = self._extract_fill_data(order)

                        logger.info("")
                        logger.info(f"   📊 Proceeding with filled portion:")
                        logger.info(f"   Sold: {filled_amount:.4f} tokens")
                        logger.info(f"   Avg price: {format_price(avg_fill_price)}")
                        logger.info(f"   Proceeds: ${filled_usdt:.2f}")
                        logger.info("")

                        return {
                            'status': 'filled',
                            'filled_amount': filled_amount,
                            'avg_fill_price': avg_fill_price,
                            'filled_usdt': filled_usdt,
                            'fill_timestamp': get_timestamp(),
                            'reason': f'Partial fill - cancelled {remaining_shares:.4f} dust'
                        }

                # =============================================================
                # CHECK: ORDER CANCELLED/EXPIRED
                # =============================================================
                # Support both US spelling (Canceled) and UK spelling (Cancelled)
                if status_enum in ['Cancelled', 'Canceled', 'Expired'] or status in [3, 4]:
                    logger.error(f"[{check_time}] ❌ Order {status_enum}!")
                    logger.warning("")
                    logger.warning(f"⚠️  Order was {status_enum.lower()}")
                    logger.warning(f"   Possible reasons:")
                    logger.warning(f"   - Market was resolved before order filled")
                    logger.warning(f"   - Order was manually canceled")
                    logger.warning(f"   - Exchange/platform canceled the order")
                    logger.warning("")
                    logger.warning(f"📊 Diagnostics:")
                    logger.warning(f"   Market ID: {market_id}")
                    logger.warning(f"   Token ID: {token_id}")
                    logger.warning(f"   Order ID: {order_id}")
                    logger.warning(f"   You still have tokens - bot will retry SELL order")
                    logger.warning("")

                    return {
                        'status': status_enum.lower(),
                        'filled_amount': None,
                        'avg_fill_price': None,
                        'filled_usdt': None,
                        'fill_timestamp': None,
                        'reason': f'Order {status_enum.lower()}'
                    }
                
                # =============================================================
                # ORDER STILL PENDING
                # =============================================================
                logger.info(f"[{check_time}] ⏳ SELL {status_enum}... (check #{check_count})")

                interruptible_sleep(self.check_interval)
        
        except KeyboardInterrupt:
            logger.info("")
            logger.info("⛔ Monitoring stopped by user")
            logger.info("")
            # Re-raise KeyboardInterrupt so main loop can send shutdown notification
            raise
        
        except Exception as e:
            logger.exception(f"Unexpected error during monitoring: {e}")
            
            return {
                'status': 'error',
                'filled_amount': None,
                'avg_fill_price': None,
                'filled_usdt': None,
                'fill_timestamp': None,
                'reason': f'Error: {str(e)}'
            }
    
    def check_stop_loss(self, buy_price: float) -> Tuple[bool, float]:
        """
        Check if stop-loss should trigger based on current market price.
        
        Compares current best bid vs buy price. If loss exceeds threshold,
        returns True to trigger stop-loss.
        
        Args:
            buy_price: Original buy price (avg fill price from BUY order)
            
        Returns:
            Tuple of (should_trigger: bool, unrealized_loss_pct: float)
        
        Example:
            >>> # buy_price = $0.100, current_bid = $0.088, threshold = -10%
            >>> # loss = -12% (exceeds -10% threshold)
            >>> should_stop, loss_pct = monitor.check_stop_loss(0.100)
            >>> should_stop  # True
            >>> loss_pct     # -12.0
        """
        # VALIDATION: Verify buy_price is real price, not fallback
        if buy_price <= 0.02:  # Suspiciously low (likely fallback $0.01)
            logger.warning(f"⚠️ buy_price={buy_price:.4f} appears to be fallback value")
            logger.warning(f"   Stop-loss may not work correctly")
            logger.warning(f"   Continuing with check but results may be inaccurate")
        
        # Get fresh orderbook to check current market price
        # Note: token_id is stored in current_position, not directly in state
        position = self.state.get('current_position', {})
        token_id = position.get('token_id')
        
        if not token_id:
            logger.warning("Token ID missing from current_position - cannot check stop-loss")
            return (False, 0.0)
        
        try:
            orderbook = self.client.get_market_orderbook(token_id)

            if not orderbook or 'bids' not in orderbook:
                logger.warning("Failed to fetch orderbook for stop-loss check")
                return (False, 0.0)

            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])

            if not bids:
                logger.warning("Empty orderbook - cannot check stop-loss")
                return (False, 0.0)

            # Extract best bid (orderbook is NOT sorted)
            current_best_bid = max(safe_float(bid.get('price', 0)) for bid in bids)

            # Assertion: Verify we got a valid price
            if current_best_bid <= 0:
                logger.warning("check_stop_loss() failed to get valid current price from orderbook")
                return (False, 0.0)

            # FLASH CRASH PROTECTION: Check spread before triggering stop-loss
            # If spread is abnormally wide, this is likely a temporary liquidity drain, not a real market crash
            if asks:
                current_best_ask = min(safe_float(ask.get('price', 999)) for ask in asks)

                if current_best_ask > current_best_bid:
                    spread_pct = ((current_best_ask - current_best_bid) / current_best_bid) * 100

                    if spread_pct > self.stop_loss_spread_filter:
                        logger.warning("")
                        logger.warning("=" * 70)
                        logger.warning("⚠️  SPREAD FILTER TRIGGERED - STOP-LOSS BLOCKED")
                        logger.warning("=" * 70)
                        logger.warning(f"   Current spread: {format_percent(spread_pct)}")
                        logger.warning(f"   Filter threshold: {format_percent(self.stop_loss_spread_filter)}")
                        logger.warning(f"   Best bid: {format_price(current_best_bid)}")
                        logger.warning(f"   Best ask: {format_price(current_best_ask)}")
                        logger.warning("")
                        logger.warning("   This is likely a liquidity drain/flash crash, not a real market move.")
                        logger.warning("   Skipping stop-loss check to avoid selling during temporary illiquidity.")
                        logger.warning("=" * 70)
                        logger.warning("")

                        # Reset bad price streak since this is not a valid check
                        if self.bad_price_streak > 0:
                            logger.info(f"   Resetting bad price streak (was {self.bad_price_streak})")
                            self.bad_price_streak = 0

                        return (False, 0.0)

        except Exception as e:
            logger.error(f"Error fetching orderbook for stop-loss: {e}")
            return (False, 0.0)
        
        # Safety check
        if current_best_bid <= 0 or buy_price <= 0:
            return (False, 0.0)
        
        # Calculate unrealized loss percentage
        unrealized_loss_pct = ((current_best_bid - buy_price) / buy_price) * 100
        
        logger.info(
            f"Stop-loss check: buy={format_price(buy_price)}, "
            f"current_bid={format_price(current_best_bid)}, "
            f"price_change={format_percent(unrealized_loss_pct)}"
        )
        
        # Check if loss exceeds threshold (both are negative, so <=)
        should_trigger = unrealized_loss_pct <= self.stop_loss_trigger
        
        return (should_trigger, unrealized_loss_pct)
    
    def execute_stop_loss(self, order_id: str) -> dict:
        """
        Execute stop-loss: cancel order and place aggressive limit.

        Steps:
        1. Cancel existing limit order
        2. Get fresh orderbook
        3. Place aggressive limit: best_bid + STOP_LOSS_AGGRESSIVE_OFFSET

        This is NOT a market order - it's an aggressive limit to minimize slippage
        while still getting filled quickly.

        NOTE: This function does NOT wait for the new order to fill. The caller
        should continue monitoring the new order until it fills.

        Args:
            order_id: Order ID to cancel

        Returns:
            Dict with new order info: {'success': True, 'new_order_id': '...', 'new_price': 0.123}
            or {'success': False, 'reason': '...'} on failure

        Example:
            >>> # Current best_bid = $0.080
            >>> # Offset = $0.001
            >>> # Aggressive limit = $0.081 (slightly above best bid)
            >>> result = monitor.execute_stop_loss('ord_456')
            >>> if result['success']:
            ...     new_order_id = result['new_order_id']
        """
        try:
            # Step 1: Cancel existing order
            logger.info("   Cancelling existing SELL order...")
            cancel_success = self.client.cancel_order(order_id)

            if not cancel_success:
                logger.error("   Failed to cancel order")
                return {'success': False, 'reason': 'Failed to cancel existing order'}

            logger.info("   ✓ Order cancelled")
            time.sleep(1)  # Brief pause

            # Step 2: Get fresh orderbook
            position = self.state.get('current_position', {})
            token_id = position.get('token_id')
            market_id = position.get('market_id')

            orderbook = self.client.get_market_orderbook(token_id)

            if not orderbook or 'bids' not in orderbook:
                logger.error("   Failed to fetch orderbook")
                return {'success': False, 'reason': 'Failed to fetch orderbook'}

            bids = orderbook.get('bids', [])
            if not bids:
                logger.error("   Empty orderbook")
                return {'success': False, 'reason': 'Empty orderbook - no bids'}

            # Get best bid (unsorted)
            best_bid = max(safe_float(bid.get('price', 0)) for bid in bids)

            # Step 3: Calculate aggressive limit price
            aggressive_price = best_bid + self.stop_loss_offset
            aggressive_price = round_price(aggressive_price)

            logger.info(f"   Placing aggressive limit order...")
            logger.info(f"   Best bid: {format_price(best_bid)}")
            logger.info(f"   Aggressive price: {format_price(aggressive_price)}")

            # Get amount from state
            position = self.state.get('current_position', {})
            amount_tokens = safe_float(position.get('filled_amount', 0))

            if amount_tokens <= 0:
                logger.error("   Invalid token amount in state")
                return {'success': False, 'reason': 'Invalid token amount in state'}

            # Place aggressive limit order using OrderManager
            try:
                from order_manager import OrderManager
                order_manager = OrderManager(self.client)
                outcome_side = position.get('outcome_side', 'YES')

                result = order_manager.place_sell(
                    market_id=market_id,
                    token_id=token_id,
                    price=aggressive_price,
                    amount_tokens=amount_tokens,
                    outcome_side=outcome_side
                )

                if not result:
                    logger.error("   Failed to place aggressive limit order")
                    return {'success': False, 'reason': 'Failed to place new order'}

                new_order_id = result.get('order_id', result.get('orderId', 'unknown'))

            except Exception as e:
                logger.error(f"   Failed to place order: {e}")
                return {'success': False, 'reason': f'Exception placing order: {e}'}

            logger.info(f"   ✓ Aggressive limit order placed: {new_order_id}")
            logger.info("")
            logger.info("   ⏳ IMPORTANT: Order placed but NOT yet filled")
            logger.info("   📊 Continuing monitoring until order fills")
            logger.info("")

            # Update state with new order
            position['sell_order_id'] = new_order_id
            position['sell_price'] = aggressive_price
            position['stop_loss_triggered'] = True
            position['stop_loss_timestamp'] = get_timestamp()

            # Save state
            from core.state_manager import StateManager
            state_file = self.config.get('STATE_FILE', 'state.json')
            state_manager = StateManager(state_file)
            state_manager.save_state(self.state)

            # Return new order info so caller can continue monitoring
            return {
                'success': True,
                'new_order_id': new_order_id,
                'new_price': aggressive_price,
                'unrealized_loss_pct': None  # Will be set by caller
            }

        except Exception as e:
            logger.error(f"   Error executing stop-loss: {e}")
            return {'success': False, 'reason': f'Exception: {e}'}
    
    def _extract_fill_data(self, order: Dict[str, Any]) -> Tuple[float, float, float]:
        """
        Extract fill data from order response.

        Tries primary fields first (filled_shares, price, filled_amount).
        Falls back to extracting from trades[] array if primary data missing.
        Finally tries order_shares/order_amount fields (for API bug workaround).

        Args:
            order: Order dictionary from API

        Returns:
            Tuple of (filled_amount_tokens, avg_fill_price, filled_usdt)
        """
        # Try primary fields
        filled_shares = safe_float(order.get('filled_shares', 0))
        fill_price = safe_float(order.get('price', 0))
        filled_usdt = safe_float(order.get('filled_amount', 0))

        # Validation: if data is missing, extract from trades
        if filled_shares == 0 or fill_price == 0:
            logger.warning("⚠️  Missing fill data in order, extracting from trades...")

            trades = order.get('trades', [])
            if trades:
                total_shares = 0.0
                total_proceeds = 0.0

                for trade in trades:
                    # Extract shares and amount
                    # IMPORTANT: trades[] returns values in WEI (18 decimals)
                    # Must divide by 1e18 to get human-readable values
                    shares_wei = safe_float(trade.get('shares', 0))
                    proceeds_wei = safe_float(trade.get('amount', 0))

                    shares = shares_wei / 1e18
                    proceeds = proceeds_wei / 1e18

                    total_shares += shares
                    total_proceeds += proceeds

                filled_shares = total_shares
                fill_price = (total_proceeds / total_shares) if total_shares > 0 else 0
                filled_usdt = total_proceeds

                logger.info(f"   ✅ Extracted from {len(trades)} trade(s)")
            else:
                logger.error("   ❌ No trades data available")

        # FALLBACK 1: Try order_shares and order_amount (API bug workaround)
        # Sometimes API returns filled_shares=0 but order_shares has the real value
        if filled_shares == 0:
            logger.warning("⚠️  FALLBACK 1: Trying order_shares/order_amount fields...")

            order_shares = safe_float(order.get('order_shares', 0))
            order_amount = safe_float(order.get('order_amount', 0))
            price = safe_float(order.get('price', 0))

            # Validate: for a Finished order, these should be non-zero
            if order_shares > 0 and price > 0:
                filled_shares = order_shares
                fill_price = price
                # Calculate USDT from shares * price if order_amount missing
                filled_usdt = order_amount if order_amount > 0 else (order_shares * price)

                logger.info(f"   ✅ Extracted from order_shares/order_amount")
                logger.info(f"   Result: shares={filled_shares:.4f}, price={fill_price:.4f}, usdt={filled_usdt:.2f}")
            else:
                logger.warning(f"   ⚠️  order_shares={order_shares}, price={price} - insufficient data")

        # FALLBACK 2: Calculate from order amount and price if still missing
        if filled_shares == 0:
            logger.warning("⚠️  FALLBACK 2: Calculating fill data from order fields")

            # Try to get from order amount (tokens to sell) and price
            amount_tokens = safe_float(order.get('amount', 0))
            price = safe_float(order.get('price', 0))

            if amount_tokens > 0 and price > 0:
                filled_shares = amount_tokens
                fill_price = price
                filled_usdt = amount_tokens * price

                logger.info(f"   ✅ Calculated from order: tokens={amount_tokens}, price={price}")
                logger.info(f"   Result: shares={filled_shares:.4f}, price={fill_price:.4f}, usdt={filled_usdt:.2f}")
            else:
                logger.error(f"   ❌ ALL FALLBACKS FAILED - insufficient order data")
                logger.error(f"   amount={amount_tokens}, price={price}")
                logger.error(f"   Full order: {order}")

        # VALIDATION: For a Finished order, shares should NEVER be zero
        status_enum = order.get('status_enum', 'unknown')
        if status_enum == 'Finished' and filled_shares == 0:
            logger.error("")
            logger.error("=" * 70)
            logger.error("❌ CRITICAL: API returned Finished order with 0 shares!")
            logger.error("=" * 70)
            logger.error(f"   This is an API bug. Order claims to be filled but has no fill data.")
            logger.error(f"   Order ID: {order.get('order_id', 'N/A')}")
            logger.error(f"   Market ID: {order.get('market_id', 'N/A')}")
            logger.error(f"   Status: {status_enum}")
            logger.error(f"   Please check the web UI to verify actual transaction.")
            logger.error("=" * 70)
            logger.error("")

        return (filled_shares, fill_price, filled_usdt)

    def check_and_execute_repricing(self, order_id: str, current_price: float) -> dict:
        """
        Check if repricing is needed and execute if necessary.

        Args:
            order_id: Current sell order ID
            current_price: Current sell order price

        Returns:
            Dict with status and new_order_id if repriced, None if no change
            {'status': 'repriced', 'new_order_id': '...', 'new_price': 0.123}
            or None if no repricing needed
        """
        # Skip if repricing disabled
        if not self.enable_repricing:
            return None

        position = self.state.get('current_position', {})
        token_id = position.get('token_id')
        buy_price = safe_float(position.get('avg_fill_price', 0))
        original_price = safe_float(position.get('original_sell_price', current_price))
        filled_amount = safe_float(position.get('filled_amount', 0))

        if not token_id or buy_price <= 0 or filled_amount <= 0:
            logger.warning("Cannot check repricing: missing required position data")
            return None

        try:
            # Get fresh orderbook
            orderbook = self.client.get_market_orderbook(token_id)
            if not orderbook or 'asks' not in orderbook:
                return None

            asks = orderbook.get('asks', [])
            if not asks:
                return None

            # Debug: Show current price and orderbook
            logger.info(f"🔍 Repricing check: current_order_price=${current_price:.4f}, total_asks={len(asks)}")
            if asks:
                best_ask_price = safe_float(asks[0].get('price', 0))
                logger.info(f"   Best ask in orderbook: ${best_ask_price:.4f}")

            # Filter out our own order and get competing asks (better prices = lower prices)
            competing_asks = [ask for ask in asks if safe_float(ask.get('price', 999)) < current_price]

            logger.info(f"   Competing asks found: {len(competing_asks)}")
            if competing_asks and len(competing_asks) <= 5:
                for i, ask in enumerate(competing_asks[:5]):
                    logger.info(f"     Ask #{i+1}: price=${safe_float(ask.get('price', 0)):.4f}, shares={safe_float(ask.get('size', 0)):.2f}")

            if not competing_asks:
                # No better prices - check if we should return to higher price (dynamic adjustment)
                if self.enable_dynamic and current_price < original_price:
                    return self._check_dynamic_price_increase(order_id, current_price, original_price, asks)
                return None

            # Calculate total competing liquidity
            total_competing_shares = sum(safe_float(ask.get('size', 0)) for ask in competing_asks)

            # Calculate threshold
            threshold_shares = filled_amount * (self.reprice_threshold_pct / 100.0)

            logger.debug(f"Repricing check: competing={total_competing_shares:.2f} shares, threshold={threshold_shares:.2f} shares")

            # Check if threshold met
            if total_competing_shares < threshold_shares:
                # Not enough competition - check dynamic increase
                if self.enable_dynamic and current_price < original_price:
                    return self._check_dynamic_price_increase(order_id, current_price, original_price, asks)
                return None

            # Threshold met - calculate new target price
            target_price = self._calculate_target_price(competing_asks, total_competing_shares)

            if target_price is None:
                return None

            # Apply price floor if configured
            min_allowed_price = self._calculate_min_allowed_price(buy_price)
            if target_price < min_allowed_price:
                logger.info(f"Target price ${target_price:.4f} below floor ${min_allowed_price:.4f}, using floor")
                target_price = min_allowed_price

            # Check if price change is significant (avoid tiny adjustments)
            price_change_pct = abs((target_price - current_price) / current_price * 100)
            if price_change_pct < 0.5:  # Less than 0.5% change
                logger.debug(f"Price change too small ({price_change_pct:.2f}%), skipping")
                return None

            # Execute repricing
            logger.info("")
            logger.info("=" * 70)
            logger.info("🔄 REPRICING SELL ORDER")
            logger.info("=" * 70)
            logger.info(f"   Current price: {format_price(current_price)}")
            logger.info(f"   Target price: {format_price(target_price)}")
            logger.info(f"   Change: {format_percent((target_price - current_price) / current_price * 100)}")
            logger.info(f"   Reason: {total_competing_shares:.2f} shares at better prices (threshold: {threshold_shares:.2f})")
            logger.info("")

            return self._execute_repricing(order_id, target_price, filled_amount)

        except Exception as e:
            logger.error(f"Error checking repricing: {e}")
            return None

    def _calculate_min_allowed_price(self, buy_price: float) -> float:
        """Calculate minimum allowed sell price based on configuration."""
        if not self.allow_below_buy:
            return buy_price

        # Allow reduction up to max_reduction_pct below buy price
        min_price = buy_price * (1 - self.max_reduction_pct / 100.0)
        return round_price(min_price)

    def _calculate_target_price(self, competing_asks: list, total_shares: float) -> float:
        """
        Calculate target price based on repricing mode.

        Args:
            competing_asks: List of ask orders with better prices than ours
            total_shares: Total shares in competing asks

        Returns:
            Target price or None if cannot calculate
        """
        if not competing_asks:
            return None

        # Sort by price (ascending - best prices first)
        sorted_asks = sorted(competing_asks, key=lambda x: safe_float(x.get('price', 999)))

        if self.reprice_mode == 'best':
            # Match best (lowest) competing price
            target = safe_float(sorted_asks[0].get('price', 0))
            logger.debug(f"Mode='best': targeting ${target:.4f}")
            return round_price(target)

        elif self.reprice_mode == 'second_best':
            # Match second best price
            if len(sorted_asks) >= 2:
                target = safe_float(sorted_asks[1].get('price', 0))
                logger.debug(f"Mode='second_best': targeting ${target:.4f}")
                return round_price(target)
            else:
                # Fallback to best if only one level
                target = safe_float(sorted_asks[0].get('price', 0))
                logger.debug(f"Mode='second_best' (fallback to best): targeting ${target:.4f}")
                return round_price(target)

        elif self.reprice_mode == 'liquidity_percent':
            # Target price level that captures X% of total liquidity
            target_shares = total_shares * (self.liq_target_pct / 100.0)
            cumulative_shares = 0.0

            for ask in sorted_asks:
                cumulative_shares += safe_float(ask.get('size', 0))
                if cumulative_shares >= target_shares:
                    target = safe_float(ask.get('price', 0))
                    logger.debug(f"Mode='liquidity_percent': targeting ${target:.4f} (captures {self.liq_target_pct}%)")
                    return round_price(target)

            # Fallback to worst competing price if we didn't reach threshold
            target = safe_float(sorted_asks[-1].get('price', 0))
            logger.debug(f"Mode='liquidity_percent' (fallback): targeting ${target:.4f}")
            return round_price(target)

        return None

    def _check_dynamic_price_increase(self, order_id: str, current_price: float,
                                      original_price: float, asks: list) -> dict:
        """
        Check if we should increase price back toward original price.
        Only applies when mode is 'second_best' or 'liquidity_percent'.

        Returns:
            Dict with repricing info or None
        """
        if self.reprice_mode not in ['second_best', 'liquidity_percent']:
            return None

        # Get competing asks at better prices
        competing_asks = [ask for ask in asks if safe_float(ask.get('price', 999)) < current_price]

        if self.reprice_mode == 'second_best':
            # If we're second best but now could be first best, move up
            if len(competing_asks) == 0:
                # No competition - can return to original
                target = original_price
                logger.info(f"Dynamic adjustment: no competition, returning to original ${target:.4f}")
            elif len(competing_asks) == 1:
                # Only one competitor - we should be second best (stay where we are)
                return None
            else:
                # Multiple competitors - could move up one level
                sorted_asks = sorted(competing_asks, key=lambda x: safe_float(x.get('price', 999)))
                target = safe_float(sorted_asks[1].get('price', 0))  # Second best

                if target <= current_price:
                    return None  # No improvement

                logger.info(f"Dynamic adjustment: moving to second best ${target:.4f}")

            return self._execute_repricing(order_id, round_price(target),
                                          safe_float(self.state.get('current_position', {}).get('filled_amount', 0)))

        elif self.reprice_mode == 'liquidity_percent':
            # Check if liquidity dropped below return threshold
            total_competing_shares = sum(safe_float(ask.get('size', 0)) for ask in competing_asks)
            position = self.state.get('current_position', {})
            filled_amount = safe_float(position.get('filled_amount', 0))

            return_threshold_shares = filled_amount * (self.liq_return_pct / 100.0)

            if total_competing_shares < return_threshold_shares:
                # Liquidity dropped - move up to next level
                if not competing_asks:
                    target = original_price
                else:
                    # Find next level up
                    sorted_asks = sorted(competing_asks, key=lambda x: safe_float(x.get('price', 999)), reverse=True)
                    target = safe_float(sorted_asks[0].get('price', 0))
                    target = min(target, original_price)  # Don't exceed original

                if target <= current_price:
                    return None

                logger.info(f"Dynamic adjustment: liquidity dropped to {total_competing_shares:.2f} shares (< {return_threshold_shares:.2f}), moving to ${target:.4f}")

                return self._execute_repricing(order_id, round_price(target), filled_amount)

        return None

    def _execute_repricing(self, old_order_id: str, new_price: float, amount_tokens: float) -> dict:
        """
        Execute repricing: cancel old order and place new one.

        Returns:
            Dict with new order info or None if failed
        """
        try:
            # Cancel old order
            logger.info(f"   Cancelling old order {old_order_id}...")
            success = self.client.cancel_order(old_order_id)

            if not success:
                logger.error("   Failed to cancel old order")
                return None

            logger.info("   ✓ Old order cancelled")
            time.sleep(1)  # Brief pause

            # Place new order
            position = self.state.get('current_position', {})
            market_id = position.get('market_id')
            token_id = position.get('token_id')
            outcome_side = position.get('outcome_side', 'YES')

            logger.info(f"   Placing new order at {format_price(new_price)}...")

            # Use order_manager if available
            from order_manager import OrderManager
            order_manager = OrderManager(self.client)

            result = order_manager.place_sell(
                market_id=market_id,
                token_id=token_id,
                price=new_price,
                amount_tokens=amount_tokens,
                outcome_side=outcome_side
            )

            if not result:
                logger.error("   Failed to place new order")
                return None

            new_order_id = result.get('order_id', result.get('orderId', 'unknown'))

            logger.info(f"   ✓ New order placed: {new_order_id}")
            logger.info("")

            # Update state
            position['sell_order_id'] = new_order_id
            position['sell_price'] = new_price
            # Note: original_sell_price is preserved

            from core.state_manager import StateManager
            state_file = self.config.get('STATE_FILE', 'state.json')
            state_manager = StateManager(state_file)
            state_manager.save_state(self.state)

            return {
                'status': 'repriced',
                'new_order_id': new_order_id,
                'new_price': new_price
            }

        except Exception as e:
            logger.error(f"   Error executing repricing: {e}")
            return None


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("Use test_sell_monitor.py for comprehensive testing")