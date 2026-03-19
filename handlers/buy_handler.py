"""
BUY Handler
===========

Handles all BUY-related stages:
- BUY_PLACED: Transition to monitoring
- BUY_MONITORING: Monitor order until filled
- BUY_FILLED: Prepare and place SELL order

Extracted from AutonomousBot to improve code organization.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from logger_config import setup_logger
from utils import format_price, format_usdt, get_timestamp, round_price, safe_float
from monitoring.buy_monitor import BuyMonitor

logger = setup_logger(__name__)


class BuyHandler:
    """
    Handles BUY-related trading stages.

    Manages order placement monitoring and position validation for BUY orders.
    """

    def __init__(self, bot):
        """
        Initialize BUY handler.

        Args:
            bot: AutonomousBot instance (for access to client, config, etc.)
        """
        self.bot = bot
        self.client = bot.client
        self.config = bot.config
        # REMOVED: self.state = bot.state (use self.bot.state instead to avoid stale references)
        self.state_manager = bot.state_manager
        self.validator = bot.validator
        self.recovery = bot.recovery
        self.scanner = bot.scanner
        self.pricing = bot.pricing
        self.order_manager = bot.order_manager
        self.telegram = bot.telegram

    def _calculate_avg_fill_price(self, position: dict, filled_amount: float) -> float:
        """
        Calculate avg_fill_price using best available data.

        Priority:
        1. Calculate from filled_usdt / filled_amount
        2. Use order price from position
        3. Get current market price
        4. Last resort: reject (don't use 0.01)

        Args:
            position: Position dict with order data
            filled_amount: Filled tokens amount

        Returns:
            Calculated avg_fill_price
        """
        # Try #1: Calculate from filled_usdt
        filled_usdt = position.get('filled_usdt', 0)
        if filled_usdt > 0 and filled_amount > 0:
            avg_price = filled_usdt / filled_amount
            logger.info(f"   💰 Calculated avg_fill_price from filled_usdt: ${avg_price:.4f}")
            return avg_price

        # Try #2: Use order price
        order_price = position.get('price', 0)
        if order_price > 0:
            logger.info(f"   💰 Using order price as avg_fill_price: ${order_price:.4f}")
            return order_price

        # Try #3: Get current market price
        market_id = position.get('market_id')
        outcome_side = position.get('outcome_side', 'YES')
        if market_id:
            try:
                orderbook = self.client.get_orderbook(market_id=str(market_id), outcome_side=outcome_side)
                if orderbook and 'bids' in orderbook:
                    bids = orderbook.get('bids', [])
                    if bids:
                        best_bid = safe_float(bids[0].get('price', 0))  # Already sorted descending
                        if best_bid > 0:
                            logger.warning(f"   ⚠️  Using current market bid as avg_fill_price: ${best_bid:.4f}")
                            logger.warning(f"   P&L calculations may be slightly inaccurate")
                            return best_bid
            except Exception as e:
                logger.warning(f"   Could not get market price: {e}")

        # Last resort: This shouldn't happen - reject
        logger.error(f"   ❌ Cannot determine avg_fill_price!")
        logger.error(f"   No filled_usdt, no order price, no market data")
        raise ValueError("Cannot determine avg_fill_price - insufficient data")

    def handle_buy_placed(self) -> bool:
        """
        BUY_PLACED stage: BUY order placed, ready to monitor.

        Transitions to: BUY_MONITORING
        """
        logger.info("📋 BUY_PLACED - Transitioning to monitoring")

        # Simply transition to monitoring
        self.bot.state['stage'] = 'BUY_MONITORING'
        self.state_manager.save_state(self.bot.state)

        return True

    def handle_buy_monitoring(self) -> bool:
        """
        BUY_MONITORING stage: Monitor BUY order until filled.

        Transitions to: BUY_FILLED (if filled)
        Transitions to: SCANNING (if cancelled/deteriorated)
        """
        logger.info("⏳ BUY_MONITORING - Waiting for fill...")

        position = self.bot.state['current_position']
        order_id = position['order_id']
        market_id = position['market_id']

        # SELF-HEALING: If order_id is 'unknown', find it from API
        if order_id == 'unknown':
            # Use PositionRecovery to find order_id from API
            result = self.recovery.recover_order_id_from_api(market_id, expected_side="BUY")

            if result.success:
                # Update state with recovered order_id
                position['order_id'] = result.order_id
                order_id = result.order_id

                self.state_manager.save_state(self.bot.state)
                logger.info("✅ order_id recovered and saved to state")
                logger.info("📍 Continuing with normal BUY monitoring...")
                logger.info("")

                # Fall through to normal monitoring code below
            else:
                # No pending orders found - check if already filled
                is_filled, tokens = self.recovery.check_if_already_filled(market_id, "YES")

                if is_filled:
                    logger.info(f"✅ Order already filled! Found {tokens:.4f} tokens")
                    logger.info("   Skipping monitoring - moving to BUY_FILLED")

                    # Update state with filled data
                    position['filled_amount'] = tokens

                    # Calculate avg_fill_price intelligently
                    try:
                        position['avg_fill_price'] = self._calculate_avg_fill_price(position, tokens)
                        position['filled_usdt'] = tokens * position['avg_fill_price']
                    except ValueError as e:
                        logger.error(f"   Failed to calculate avg_fill_price: {e}")
                        logger.info("   Resetting to SCANNING")
                        self.state_manager.reset_position(self.bot.state)
                        self.bot.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.bot.state)
                        return True

                    position['fill_timestamp'] = get_timestamp()

                    self.bot.state['stage'] = 'BUY_FILLED'
                    self.state_manager.save_state(self.bot.state)
                    return True
                else:
                    logger.warning(f"⚠️ No pending order AND no filled position")
                    logger.warning(f"   Order may have been cancelled or doesn't exist")
                    logger.info("   Resetting to SCANNING to find new market")

                self.state_manager.reset_position(self.bot.state)
                self.bot.state['stage'] = 'SCANNING'
                self.state_manager.save_state(self.bot.state)
                return True

        # SELF-HEALING: Verify order is still active before starting monitor
        logger.info("🔍 Verifying order status before monitoring...")
        try:
            order_status = self.client.get_order_status(order_id)

            # If order doesn't exist or is in terminal state (can't be monitored)
            # OFFICIAL STATUS NAMES: 'PENDING', 'FINISHED', 'CANCELLED', 'EXPIRED', 'FAILED'
            terminal_statuses = ['CANCELLED', 'FINISHED', 'EXPIRED', 'FAILED']

            if order_status is None or order_status in terminal_statuses:
                if order_status == 'CANCELLED':
                    logger.warning(f"⚠️ BUY order is CANCELLED")
                elif order_status == 'FINISHED':
                    logger.info(f"✅ BUY order already completed")
                else:
                    logger.warning("⚠️ BUY order not found in API")

                logger.info("🔄 Checking if position exists (tokens to sell)...")

                # Check if we have tokens from this position
                # RETRY LOGIC: Position may not be visible immediately after fill
                verified_shares = None
                max_retries = 3
                retry_delay = 2  # seconds

                for attempt in range(1, max_retries + 1):
                    verified_shares = self.client.get_position_shares(
                        market_id=str(market_id),
                        outcome_side="YES"
                    )
                    tokens = float(verified_shares)

                    if tokens > 0:
                        logger.info(f"✅ Position found on attempt {attempt}: {tokens:.4f} tokens")
                        break

                    if attempt < max_retries:
                        logger.info(f"⚠️ Attempt {attempt}/{max_retries}: Position not visible yet")
                        logger.info(f"   Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        logger.warning(f"⚠️ After {max_retries} attempts, still no position")

                if verified_shares is None:
                    tokens = 0.0
                else:
                    tokens = float(verified_shares)

                if tokens >= 1.0:  # Have significant position
                    outcome_side = position.get('outcome_side', 'YES')
                    logger.info(f"✅ Found position with {tokens:.4f} {outcome_side} tokens")

                    if order_status == 'FINISHED':
                        logger.info(f"   Order was {order_status} - switching to BUY_FILLED")
                    else:
                        logger.info(f"   Order was {order_status or 'not found'} but position exists")
                        logger.info(f"   This may be partial fill - switching to SELL")

                    # Update state as if BUY was filled
                    position['filled_amount'] = tokens

                    # Calculate avg_fill_price intelligently
                    try:
                        position['avg_fill_price'] = self._calculate_avg_fill_price(position, tokens)
                        position['filled_usdt'] = tokens * position['avg_fill_price']
                    except ValueError as e:
                        logger.error(f"   Failed to calculate avg_fill_price: {e}")
                        logger.info("   Resetting to SCANNING")
                        self.state_manager.reset_position(self.bot.state)
                        self.bot.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.bot.state)
                        return True

                    position['fill_timestamp'] = get_timestamp()

                    self.bot.state['stage'] = 'BUY_FILLED'
                    self.state_manager.save_state(self.bot.state)
                    return True

                else:
                    logger.warning(f"⚠️ No significant position found (only {tokens:.4f} tokens)")

                    # CRITICAL: This may be API timing delay!
                    if order_status == 'FINISHED':
                        # Check if order has been FINISHED for too long to be just API lag
                        # If placed_at exists, calculate time since placement
                        placed_at_str = position.get('placed_at')
                        is_stale = False

                        if placed_at_str:
                            try:
                                placed_at = datetime.fromisoformat(placed_at_str.replace('Z', '+00:00'))
                                time_since_placement = datetime.now() - placed_at

                                # If order was placed more than 5 minutes ago and still dust, it's not API lag
                                if time_since_placement.total_seconds() > 300:  # 5 minutes
                                    is_stale = True
                                    logger.warning(f"   Order was placed {time_since_placement.total_seconds()/60:.1f} minutes ago")
                                    logger.warning(f"   Position is still dust after {time_since_placement.total_seconds()/60:.1f} minutes")
                                    logger.warning(f"   This is NOT API timing delay - position was likely already sold")
                            except Exception as e:
                                logger.debug(f"Could not parse placed_at: {e}")

                        if is_stale:
                            logger.warning(f"   Dust position after extended time indicates completed trade")
                            logger.info(f"   Resetting to SCANNING to find new market")

                            self.state_manager.reset_position(self.bot.state)
                            self.bot.state['stage'] = 'SCANNING'
                            self.state_manager.save_state(self.bot.state)
                            return True
                        else:
                            logger.info(f"   Order status='FINISHED' but position not visible yet")
                            logger.info(f"   This is likely API timing delay (position update lag)")
                            logger.info(f"   🔄 RETRYING: Will check again in next monitoring cycle")
                            logger.info(f"   Bot will proceed to normal monitoring which includes retry logic")
                            logger.info(f"✅ Order is active (timing issue) - proceeding to monitor")
                            # Fall through to normal monitoring code below

                    elif order_status == 'CANCELLED':
                        logger.info(f"   Order was CANCELLED without fill - reset to find new market")

                        self.state_manager.reset_position(self.bot.state)
                        self.bot.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.bot.state)
                        return True

                    else:
                        logger.warning(f"   Order not found in API and no position exists")
                        logger.info(f"   Resetting to SCANNING for new market")

                        self.state_manager.reset_position(self.bot.state)
                        self.bot.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.bot.state)
                        return True

            # Order exists and is active - proceed with normal monitoring
            logger.info(f"✅ Order is active (status: {order_status}) - starting monitor")

        except Exception as e:
            logger.warning(f"⚠️ Could not verify order status: {e}")
            logger.info("   Proceeding with normal monitoring (may fail if order doesn't exist)")

        # Calculate timeout based on when order was originally placed
        timeout_hours = self.config['BUY_ORDER_TIMEOUT_HOURS']

        placed_at_str = position.get('placed_at')
        if placed_at_str:
            try:
                placed_at = datetime.fromisoformat(placed_at_str.replace('Z', '+00:00'))
                timeout_at = placed_at + timedelta(hours=timeout_hours)
                logger.debug(f"Using placed_at from state: {placed_at_str}")
                logger.debug(f"Timeout at: {timeout_at.strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception as e:
                logger.warning(f"Could not parse placed_at '{placed_at_str}': {e}")
                logger.info("Falling back to current time for timeout calculation")
                timeout_at = datetime.now() + timedelta(hours=timeout_hours)
        else:
            logger.debug("No placed_at in state, using current time for timeout")
            timeout_at = datetime.now() + timedelta(hours=timeout_hours)

        # Create monitor and start monitoring
        monitor = BuyMonitor(self.config, self.client, self.bot.state, heartbeat_callback=self.bot._check_and_send_heartbeat)

        result = monitor.monitor_until_filled(order_id, timeout_at)

        # Re-fetch position reference - heartbeat callback may have reloaded self.bot.state from disk
        position = self.bot.state['current_position']

        status = result['status']

        # Handle different outcomes
        if status == 'filled':
            logger.info("✅ BUY order filled!")

            # Record transaction in history for audit trail
            order_id = position.get('order_id', 'unknown')
            market_id = position.get('market_id', 0)
            market_title = position.get('market_title', 'Unknown market')
            outcome = position.get('outcome_side', 'YES')
            # token_id no longer stored in state (adapter handles token_id lookup internally)
            token_id = ''  # Not needed for transaction history

            # Update state with fill data
            filled_from_monitor = result.get('filled_amount', 0)

            # Double-check with actual position shares
            try:
                market_id = position['market_id']
                outcome_side = position.get('outcome_side', 'YES')
                verified_shares = self.client.get_position_shares(
                    market_id=str(market_id),
                    outcome_side=outcome_side
                )
                verified_amount = float(verified_shares)

                if verified_amount > 0:
                    logger.info(f"✅ Verified filled_amount from position: {verified_amount:.10f} tokens")
                    position['filled_amount'] = verified_amount
                else:
                    logger.warning(f"⚠️ Position check returned 0, using monitor value: {filled_from_monitor}")
                    position['filled_amount'] = filled_from_monitor

            except Exception as e:
                logger.warning(f"⚠️ Could not verify position, using monitor value: {e}")
                position['filled_amount'] = filled_from_monitor

            position['avg_fill_price'] = result.get('avg_fill_price', position.get('price', 0))
            position['filled_usdt'] = result.get('filled_usdt', 0)
            position['fill_timestamp'] = result.get('fill_timestamp')

            # VALIDATION: Check if avg_fill_price is suspiciously low
            if position['avg_fill_price'] <= 0.02:
                logger.warning(f"⚠️ avg_fill_price={position['avg_fill_price']:.4f} is suspiciously low!")
                logger.warning(f"   This may be fallback value from failed extraction")
                logger.warning(f"   Attempting to calculate from filled_usdt and filled_amount...")

                filled_usdt = position.get('filled_usdt', 0)
                filled_amount = position.get('filled_amount', 0)

                if filled_usdt > 0 and filled_amount > 0:
                    calculated_price = filled_usdt / filled_amount
                    logger.info(f"✅ Calculated avg_fill_price: ${calculated_price:.4f}")
                    logger.info(f"   (filled_usdt=${filled_usdt:.2f} / filled_amount={filled_amount:.4f})")
                    position['avg_fill_price'] = calculated_price
                else:
                    # Try using original order price as last resort
                    order_price = position.get('price', 0)
                    if order_price > 0:
                        logger.warning(f"⚠️ Using original order price as fallback: ${order_price:.4f}")
                        logger.warning(f"   This may not reflect actual fill price!")
                        position['avg_fill_price'] = order_price
                    else:
                        logger.error(f"❌ Cannot determine avg_fill_price!")
                        logger.error(f"   Stop-loss and P&L will be INACCURATE")
                        logger.error(f"   Using minimal fallback $0.01")

            # Record BUY transaction in history
            self.bot.transaction_history.record_buy(
                market_id=market_id,
                market_title=market_title,
                token_id=token_id,
                shares=position.get('filled_amount', 0),
                price=position.get('avg_fill_price', 0),
                amount_usdt=position.get('filled_usdt', 0),
                order_id=order_id,
                outcome=outcome
            )

            self.bot.state['stage'] = 'BUY_FILLED'
            self.state_manager.save_state(self.bot.state)

            # Send Telegram notification about BUY fill
            if self.bot.telegram:
                try:
                    self.bot.telegram.send_state_change(
                        new_stage='BUY_FILLED',
                        market_id=market_id,
                        market_title=market_title,
                        price=position.get('avg_fill_price', 0),
                        amount=position.get('filled_usdt', 0),
                        shares=position.get('filled_amount', 0)
                    )
                except Exception as e:
                    logger.warning(f"Failed to send Telegram notification: {e}")

            return True

        elif status in ['cancelled', 'canceled', 'expired', 'timeout', 'deteriorated']:
            logger.warning(f"BUY order {status}: {result.get('reason')}")
            logger.info("Resetting to find new market...")

            # Cancel order if still active
            if status in ['timeout', 'deteriorated']:
                try:
                    self.client.cancel_order(order_id)
                    logger.info("Order cancelled")
                except:
                    pass

            # Reset position and go back to scanning
            self.state_manager.reset_position(self.bot.state)
            self.bot.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.bot.state)

            return True

        else:
            logger.error(f"Unexpected monitoring result: {status}")
            return False

    def handle_buy_filled(self) -> bool:
        """
        BUY_FILLED stage: BUY filled, ready to place SELL.

        Transitions to: SELL_PLACED
        """
        logger.info("💰 BUY_FILLED - Preparing SELL order...")

        position = self.bot.state['current_position']
        market_id = position['market_id']

        # CRITICAL: Use .get() to handle case where filled_amount is missing
        # This can happen if state is reconstructed by reconciliation or reset between stages
        filled_amount = position.get('filled_amount', 0)

        if filled_amount == 0:
            # filled_amount is missing - attempt recovery from API
            logger.warning("⚠️ filled_amount missing from state, attempting recovery...")

            try:
                outcome_side = position.get('outcome_side', 'YES')

                if not market_id:
                    logger.error("❌ Cannot recover - market_id is missing")
                    logger.info("   Resetting to SCANNING")
                    self.state_manager.reset_position(self.bot.state)
                    self.bot.state['stage'] = 'SCANNING'
                    self.state_manager.save_state(self.bot.state)
                    return False

                # Try to get position from API
                shares = self.client.get_position_shares(str(market_id), outcome_side)
                filled_amount = float(shares) if shares else 0

                if filled_amount > 0:
                    logger.info(f"✅ Recovered filled_amount from API: {filled_amount:.4f} tokens")
                    position['filled_amount'] = filled_amount

                    # Also try to recover avg_fill_price if missing
                    if not position.get('avg_fill_price') or position.get('avg_fill_price') <= 0.02:
                        logger.info("   Also attempting to recover avg_fill_price...")
                        try:
                            recalculated_price = self._calculate_avg_fill_price(position, filled_amount)
                            position['avg_fill_price'] = recalculated_price
                            position['filled_usdt'] = filled_amount * recalculated_price
                            logger.info(f"   ✅ Recovered avg_fill_price: ${recalculated_price:.4f}")
                        except ValueError as e:
                            logger.error(f"   ❌ Could not recover avg_fill_price: {e}")
                            logger.info("   Resetting to SCANNING")
                            self.state_manager.reset_position(self.bot.state)
                            self.bot.state['stage'] = 'SCANNING'
                            self.state_manager.save_state(self.bot.state)
                            return False

                    # Save recovered state
                    self.state_manager.save_state(self.bot.state)
                else:
                    logger.error("❌ Cannot recover filled_amount - no position found in API")
                    logger.info("   Resetting to SCANNING")
                    self.state_manager.reset_position(self.bot.state)
                    self.bot.state['stage'] = 'SCANNING'
                    self.state_manager.save_state(self.bot.state)
                    return False

            except Exception as e:
                logger.error(f"❌ Failed to recover filled_amount: {e}")
                logger.info("   Resetting to SCANNING")
                self.state_manager.reset_position(self.bot.state)
                self.bot.state['stage'] = 'SCANNING'
                self.state_manager.save_state(self.bot.state)
                return False

        # CRITICAL: Validate and fix avg_fill_price if suspicious
        # This handles cases where state.json has 0.01$ from failed recovery
        avg_fill_price = position.get('avg_fill_price', 0)
        if avg_fill_price <= 0.02:  # Suspiciously low (0.01$ is clearly wrong)
            logger.warning(f"⚠️  avg_fill_price is suspiciously low: ${avg_fill_price:.4f}")
            logger.info("   Recalculating avg_fill_price from available data...")

            try:
                recalculated_price = self._calculate_avg_fill_price(position, filled_amount)
                position['avg_fill_price'] = recalculated_price
                position['filled_usdt'] = filled_amount * recalculated_price
                self.state_manager.save_state(self.bot.state)
                logger.info(f"   ✅ Corrected avg_fill_price: ${avg_fill_price:.4f} → ${recalculated_price:.4f}")
            except ValueError as e:
                logger.error(f"   ❌ Could not recalculate avg_fill_price: {e}")
                logger.info("   Resetting to SCANNING")
                self.state_manager.reset_position(self.bot.state)
                self.bot.state['stage'] = 'SCANNING'
                self.state_manager.save_state(self.bot.state)
                return False

        # Validate/recover token_id (not stored in state anymore, adapter handles it)
        outcome_side = position.get('outcome_side', 'YES')
        token_id = None  # token_id no longer in state, will be recovered by validator
        is_valid, recovered_token_id = self.validator.validate_token_id(token_id, market_id, outcome_side)

        if not is_valid:
            logger.error(f"❌ Could not validate or recover token_id")
            logger.error(f"   Cannot place SELL without valid token_id")
            logger.info(f"   Resetting to SCANNING")

            self.state_manager.reset_position(self.bot.state)
            self.bot.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.bot.state)
            return False

        # Update token_id if it was recovered (use local var, don't store in state)
        if recovered_token_id and recovered_token_id != token_id:
            token_id = recovered_token_id
            logger.info(f"   ✅ token_id recovered: {token_id[:20]}...")

        logger.info(f"✅ token_id validated: {token_id[:20]}...")

        # Check for manual sale
        has_position, actual_tokens, error_msg = self.validator.verify_actual_position(
            market_id, outcome_side, expected_tokens=filled_amount
        )

        if not has_position:
            logger.warning(f"⚠️ Position verification failed: {error_msg}")
            logger.info("   Resetting to SCANNING to find new market")

            self.state_manager.reset_position(self.bot.state)
            self.bot.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.bot.state)
            return True

        # Update filled_amount if actual differs from expected
        if abs(actual_tokens - filled_amount) > 0.01:
            logger.info(f"   Updating filled_amount: {filled_amount:.4f} → {actual_tokens:.4f}")
            filled_amount = actual_tokens
            position['filled_amount'] = actual_tokens
            self.state_manager.save_state(self.bot.state)

        # Check if position is dust
        dust_result = self.validator.check_dust_position_by_shares(filled_amount)

        if not dust_result.is_valid:
            # Reset and find new market
            self.state_manager.reset_position(self.bot.state)
            self.bot.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.bot.state)
            return True

        # Get fresh orderbook for SELL pricing
        try:
            fresh_orderbook = self.scanner.get_fresh_orderbook(market_id, token_id, outcome_side)

            if not fresh_orderbook:
                logger.error("Failed to get orderbook for SELL")
                return False

            best_bid = fresh_orderbook['best_bid']
            best_ask = fresh_orderbook['best_ask']

            # Check if order value meets minimum
            value_result = self.validator.check_dust_position_by_value(filled_amount, best_ask)

            if not value_result.is_valid:
                # Reset and find new market
                self.state_manager.reset_position(self.bot.state)
                self.bot.state['stage'] = 'SCANNING'
                self.state_manager.save_state(self.bot.state)
                return True

            # Handle edge case: empty orderbook
            if not best_ask or best_ask == 0:
                logger.warning("⚠️ ⚠️  No asks in orderbook (lopsided 99:1 market)")
                logger.warning("   Using fallback: SELL at $0.96 (near-maximum price)")
                best_ask = 0.96

                if not best_bid or best_bid == 0:
                    logger.warning("   No bids either - using synthetic bid $0.95")
                    best_bid = 0.95

            logger.info(f"   Bid: {format_price(best_bid)} | Ask: {format_price(best_ask)}")

            # Calculate and store initial spread for liquidity monitoring
            # This helps differentiate between:
            # - Wide spread at entry (normal for illiquid markets)
            # - Spread widening after entry (liquidity deteriorating)
            if best_bid > 0:
                initial_spread_pct = ((best_ask - best_bid) / best_bid) * 100
                position['initial_spread_pct'] = initial_spread_pct
                position['initial_best_bid'] = best_bid
                logger.debug(f"   Initial spread: {initial_spread_pct:.1f}%")

            # Store timestamp when SELL order is placed
            # Used for showing "order age" in Telegram notifications
            position['sell_placed_timestamp'] = get_timestamp()
            logger.debug(f"   SELL order timestamp: {position['sell_placed_timestamp']}")

            # Check if stop-loss was triggered (need to exit quickly)
            stop_loss_triggered = position.get('stop_loss_triggered', False)

            if stop_loss_triggered:
                # Stop-loss scenario: Use aggressive pricing to exit position quickly
                # Place sell order at best bid (instant fill) or slightly above
                logger.warning("⚠️ Stop-loss triggered - using aggressive pricing to exit position")
                sell_price = best_bid  # Sell at best bid for quick fill
                logger.info(f"   Using best bid for quick exit: {format_price(sell_price)}")

                # Clear the flag after using it
                position['stop_loss_triggered'] = False
            else:
                # Normal scenario: Use market-making pricing strategy
                sell_price = self.pricing.calculate_sell_price(best_bid, best_ask)

            # Apply minimum price floor to prevent selling below buy price
            # This is critical when retrying after order cancellation
            # EXCEPT when stop-loss is triggered - then we need to exit at market price
            buy_price = position.get('avg_fill_price', 0)
            if buy_price > 0:
                # Calculate minimum allowed price based on config
                allow_below_buy = self.config.get('ALLOW_SELL_BELOW_BUY_PRICE', False)
                max_reduction_pct = self.config.get('MAX_SELL_PRICE_REDUCTION_PCT', 5.0)

                if not allow_below_buy:
                    min_allowed_price = round_price(buy_price)
                else:
                    # Allow reduction up to max_reduction_pct below buy price
                    min_allowed_price = buy_price * (1 - max_reduction_pct / 100.0)
                    min_allowed_price = round_price(min_allowed_price)

                # Enforce floor (but OVERRIDE if stop-loss triggered and market is below floor)
                if sell_price < min_allowed_price:
                    if stop_loss_triggered:
                        # Stop-loss scenario: market price is below floor
                        # We MUST override the floor to exit the position
                        logger.warning("⚠️ Stop-loss triggered but price floor prevents market exit")
                        logger.warning(f"   Market bid: {format_price(sell_price)} vs Floor: {format_price(min_allowed_price)}")
                        logger.warning("⚠️ OVERRIDING floor to accept loss and exit position at market price")
                        logger.info(f"   Selling at: {format_price(sell_price)} (below buy price of {format_price(buy_price)})")
                        # sell_price stays at best_bid - don't adjust to floor
                    else:
                        # Normal scenario: respect floor
                        logger.warning(f"⚠️  Calculated SELL price {format_price(sell_price)} is below minimum floor {format_price(min_allowed_price)}")
                        logger.warning(f"   Buy price: {format_price(buy_price)}, Allow below: {allow_below_buy}, Max reduction: {max_reduction_pct}%")
                        logger.info(f"   Adjusting to floor: {format_price(min_allowed_price)}")
                        sell_price = min_allowed_price

            logger.info(f"   SELL price: {format_price(sell_price)}")

            # Check for dust accumulation
            logger.info("🔍 Checking for existing dust position on this market...")

            try:
                existing_shares = self.client.get_position_shares(
                    market_id=str(market_id),
                    outcome_side=outcome_side
                )
                existing_amount = float(existing_shares)

                logger.info(f"   Current position: {filled_amount:.4f} shares")
                logger.info(f"   Existing position (from API): {existing_amount:.4f} shares")

                # Check if we have MORE shares than expected (dust from previous trades)
                if existing_amount > filled_amount:
                    dust_amount = existing_amount - filled_amount
                    logger.info(f"   ✅ DUST DETECTED: {dust_amount:.4f} shares")
                    logger.info(f"   Adding dust to SELL order...")

                    # Update filled_amount to include dust
                    old_amount = filled_amount
                    filled_amount = existing_amount
                    position['filled_amount'] = filled_amount
                    self.state_manager.save_state(self.bot.state)

                    logger.info(f"   📝 Updated SELL amount: {old_amount:.4f} → {filled_amount:.4f} shares")
                elif existing_amount < filled_amount:
                    # API shows LESS than expected - possible manual sale
                    logger.warning(f"   ⚠️ API shows LESS shares than expected!")
                    logger.warning(f"   Using API value (more accurate)")

                    filled_amount = existing_amount
                    position['filled_amount'] = filled_amount
                    self.state_manager.save_state(self.bot.state)

                    # Re-check if still above dust threshold
                    if filled_amount < 5.0:
                        logger.warning("   ⚠️ After adjustment, position is now dust!")
                        logger.info("   Abandoning and resetting to SCANNING")
                        self.state_manager.reset_position(self.bot.state)
                        self.bot.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.bot.state)
                        return True
                else:
                    logger.info(f"   ✅ No dust - amounts match")

            except Exception as e:
                logger.warning(f"   ⚠️ Could not check for dust: {e}")
                logger.info(f"   Proceeding with state.json value: {filled_amount:.4f}")

            # Place SELL order
            logger.info("📝 Placing SELL order...")

            result = self.order_manager.place_sell(
                market_id=market_id,
                token_id=token_id,
                price=sell_price,
                amount_tokens=filled_amount,
                outcome_side=outcome_side
            )

            if not result:
                logger.error("Failed to place SELL order")
                return False

            sell_order_id = result.get('order_id', result.get('orderId', 'unknown'))

            logger.info(f"✅ SELL order placed: {sell_order_id}")

            # Update state
            position['sell_order_id'] = sell_order_id
            position['sell_price'] = sell_price
            position['sell_placed_at'] = get_timestamp()

            # Save original sell price for repricing logic
            # This is the initial target sell price that we wanted when placing the order
            if 'original_sell_price' not in position:
                position['original_sell_price'] = sell_price
                logger.debug(f"   Saved original_sell_price: {format_price(sell_price)}")

            # =================================================================
            # POSITION LADDERING: Place counter-BUY order if enabled
            # =================================================================
            if self.config.get('ENABLE_POSITION_LADDERING', False):
                logger.info("")
                logger.info("=" * 70)
                logger.info("🎯 POSITION LADDERING ENABLED")
                logger.info("=" * 70)
                logger.info("")

                try:
                    from monitoring.position_laddering import PositionLaddering

                    # Initialize laddering strategy
                    laddering = PositionLaddering(self.config, self.client, self.bot.state)

                    # Get entry price and amount
                    entry_price = position.get('avg_fill_price', 0)
                    filled_amount = position.get('filled_amount', 0)

                    if entry_price <= 0 or filled_amount <= 0:
                        logger.warning("⚠️  Cannot place ladder BUY: invalid entry_price or filled_amount")
                        logger.warning("   Continuing without laddering (traditional stop-loss will apply)")
                    else:
                        # Calculate ladder price
                        ladder_offset_pct = self.config.get('LADDER_BUY_OFFSET_PCT', -15.0)
                        ladder_price = laddering.calculate_ladder_price(entry_price, ladder_offset_pct)

                        logger.info(f"📊 LADDER CALCULATION:")
                        logger.info(f"   Entry price: {format_price(entry_price)}")
                        logger.info(f"   Ladder offset: {ladder_offset_pct}%")
                        logger.info(f"   Ladder price: {format_price(float(ladder_price))}")
                        logger.info(f"   Position size: {filled_amount:.4f} tokens")
                        logger.info("")

                        # Place counter-BUY order
                        logger.info(f"📤 Placing counter-BUY order (safety net)...")

                        ladder_result = laddering.place_ladder_buy(
                            market_id=market_id,
                            token_id=token_id,
                            price=float(ladder_price),
                            amount=filled_amount
                        )

                        if ladder_result.get('success'):
                            # Counter-BUY placed successfully
                            ladder_order_id = ladder_result.get('order_id')

                            logger.info("")
                            logger.info("✅ LADDERING STRATEGY ACTIVATED")
                            logger.info("")
                            logger.info("   📍 Current state:")
                            logger.info(f"      SELL order @ {format_price(sell_price)} [PENDING]")
                            logger.info(f"      Safety BUY @ {format_price(float(ladder_price))} [PENDING]")
                            logger.info("")
                            logger.info("   📈 Possible outcomes:")
                            logger.info(f"      ✅ SELL fills first → Normal exit (+profit)")
                            logger.info(f"      🎯 BUY fills first → Average down, wait for recovery")
                            logger.info("")
                            logger.info("=" * 70)
                            logger.info("")

                            # Update state with laddering info
                            position['laddering_active'] = True
                            position['ladder_buy_order_id'] = ladder_order_id
                            position['ladder_buy_price'] = float(ladder_price)
                            position['original_cost_basis'] = entry_price
                            position['original_shares'] = filled_amount
                            position['averaging_rounds'] = 0
                            position['total_cost_usd'] = filled_amount * entry_price

                            # Save state immediately with ladder info
                            self.state_manager.save_state(self.bot.state)

                            logger.debug(f"💾 State updated with ladder BUY order info")

                        else:
                            # Counter-BUY failed (likely insufficient capital)
                            reason = ladder_result.get('reason', 'Unknown error')
                            logger.warning("")
                            logger.warning("⚠️  LADDERING ACTIVATION FAILED")
                            logger.warning(f"   Reason: {reason}")
                            logger.warning("")
                            logger.warning("   Continuing with traditional stop-loss only")
                            logger.warning("   Position will use standard stop-loss protection")
                            logger.warning("")
                            logger.warning("=" * 70)
                            logger.warning("")

                            # Mark laddering as inactive
                            position['laddering_active'] = False

                except Exception as e:
                    logger.exception(f"❌ Error setting up position laddering: {e}")
                    logger.warning("   Continuing without laddering (traditional stop-loss will apply)")

                    # Mark laddering as inactive
                    position['laddering_active'] = False

            self.bot.state['stage'] = 'SELL_PLACED'
            self.state_manager.save_state(self.bot.state)

            # Send Telegram notification
            self.telegram.send_state_change(
                new_stage='SELL_PLACED',
                market_id=position.get('market_id'),
                market_title=position.get('market_title'),
                price=sell_price,
                amount=position.get('filled_amount', 0) * sell_price
            )

            return True

        except Exception as e:
            logger.exception(f"Error placing SELL: {e}")
            return False
