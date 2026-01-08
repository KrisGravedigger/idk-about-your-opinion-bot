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
from utils import format_price, format_usdt, get_timestamp
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
        self.state = bot.state
        self.state_manager = bot.state_manager
        self.validator = bot.validator
        self.recovery = bot.recovery
        self.scanner = bot.scanner
        self.pricing = bot.pricing
        self.order_manager = bot.order_manager
        self.telegram = bot.telegram

    def handle_buy_placed(self) -> bool:
        """
        BUY_PLACED stage: BUY order placed, ready to monitor.

        Transitions to: BUY_MONITORING
        """
        logger.info("📋 BUY_PLACED - Transitioning to monitoring")

        # Simply transition to monitoring
        self.state['stage'] = 'BUY_MONITORING'
        self.state_manager.save_state(self.state)

        return True

    def handle_buy_monitoring(self) -> bool:
        """
        BUY_MONITORING stage: Monitor BUY order until filled.

        Transitions to: BUY_FILLED (if filled)
        Transitions to: SCANNING (if cancelled/deteriorated)
        """
        logger.info("⏳ BUY_MONITORING - Waiting for fill...")

        position = self.state['current_position']
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

                # Also recover token_id to prevent liquidity check crashes
                outcome_side = position.get('outcome_side', 'YES')
                token_result = self.recovery.recover_token_id_from_market(market_id, outcome_side)

                if token_result.success:
                    position['token_id'] = token_result.token_id
                    logger.info(f"   ✅ Also recovered token_id")

                self.state_manager.save_state(self.state)
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
                    position['avg_fill_price'] = position.get('price', 0.01)
                    position['filled_usdt'] = tokens * position['avg_fill_price']
                    position['fill_timestamp'] = get_timestamp()

                    self.state['stage'] = 'BUY_FILLED'
                    self.state_manager.save_state(self.state)
                    return True
                else:
                    logger.warning(f"⚠️ No pending order AND no filled position")
                    logger.warning(f"   Order may have been cancelled or doesn't exist")
                    logger.info("   Resetting to SCANNING to find new market")

                self.state_manager.reset_position(self.state)
                self.state['stage'] = 'SCANNING'
                self.state_manager.save_state(self.state)
                return True

        # SELF-HEALING: Verify order is still active before starting monitor
        logger.info("🔍 Verifying order status before monitoring...")
        try:
            order_status = self.client.get_order_status(order_id)

            # If order doesn't exist or is in terminal state (can't be monitored)
            terminal_statuses = ['CANCELLED', 'FILLED']

            if order_status is None or order_status in terminal_statuses:
                if order_status == 'CANCELLED':
                    logger.warning(f"⚠️ BUY order is CANCELLED")
                elif order_status == 'FILLED':
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
                        market_id=market_id,
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

                    if order_status in ['FILLED', 'PARTIALLY_FILLED']:
                        logger.info(f"   Order was {order_status} - switching to BUY_FILLED")
                    else:
                        logger.info(f"   Order was {order_status or 'not found'} but position exists")
                        logger.info(f"   This may be partial fill - switching to SELL")

                    # Update state as if BUY was filled
                    position['filled_amount'] = tokens
                    position['avg_fill_price'] = position.get('price', 0.01)
                    position['filled_usdt'] = tokens * position['avg_fill_price']
                    position['fill_timestamp'] = get_timestamp()

                    self.state['stage'] = 'BUY_FILLED'
                    self.state_manager.save_state(self.state)
                    return True

                else:
                    logger.warning(f"⚠️ No significant position found (only {tokens:.4f} tokens)")

                    # CRITICAL: This may be API timing delay!
                    if order_status == 'FILLED':
                        logger.info(f"   Order status='FILLED' but position not visible yet")
                        logger.info(f"   This is likely API timing delay (position update lag)")
                        logger.info(f"   🔄 RETRYING: Will check again in next monitoring cycle")
                        logger.info(f"   Bot will proceed to normal monitoring which includes retry logic")
                        logger.info(f"✅ Order is active (timing issue) - proceeding to monitor")
                        # Fall through to normal monitoring code below

                    elif order_status == 'CANCELLED':
                        logger.info(f"   Order was CANCELLED without fill - reset to find new market")

                        self.state_manager.reset_position(self.state)
                        self.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.state)
                        return True

                    else:
                        logger.warning(f"   Order not found in API and no position exists")
                        logger.info(f"   Resetting to SCANNING for new market")

                        self.state_manager.reset_position(self.state)
                        self.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.state)
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
        monitor = BuyMonitor(self.config, self.client, self.state, heartbeat_callback=self.bot._check_and_send_heartbeat)

        result = monitor.monitor_until_filled(order_id, timeout_at)

        status = result['status']

        # Handle different outcomes
        if status == 'filled':
            logger.info("✅ BUY order filled!")

            # Record transaction in history for audit trail
            order_id = position.get('order_id', 'unknown')
            market_id = position.get('market_id', 0)
            market_title = position.get('market_title', 'Unknown market')
            token_id = position.get('token_id', '')
            outcome = position.get('outcome_side', 'YES')

            # Update state with fill data
            filled_from_monitor = result.get('filled_amount', 0)

            # Double-check with actual position shares
            try:
                market_id = position['market_id']
                outcome_side = position.get('outcome_side', 'YES')
                verified_shares = self.client.get_position_shares(
                    market_id=market_id,
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

            self.state['stage'] = 'BUY_FILLED'
            self.state_manager.save_state(self.state)

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
            self.state_manager.reset_position(self.state)
            self.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.state)

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

        position = self.state['current_position']
        market_id = position['market_id']
        token_id = position.get('token_id')
        filled_amount = position['filled_amount']

        # Validate token_id
        outcome_side = position.get('outcome_side', 'YES')
        is_valid, recovered_token_id = self.validator.validate_token_id(token_id, market_id, outcome_side)

        if not is_valid:
            logger.error(f"❌ Could not validate or recover token_id")
            logger.error(f"   Cannot place SELL without valid token_id")
            logger.info(f"   Resetting to SCANNING")

            self.state_manager.reset_position(self.state)
            self.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.state)
            return False

        # Update token_id if it was recovered
        if recovered_token_id and recovered_token_id != token_id:
            token_id = recovered_token_id
            position['token_id'] = token_id
            self.state_manager.save_state(self.state)
            logger.info(f"   💾 State updated with valid token_id")

        logger.info(f"✅ token_id validated: {token_id[:20]}...")

        # Check for manual sale
        has_position, actual_tokens, error_msg = self.validator.verify_actual_position(
            market_id, outcome_side, expected_tokens=filled_amount
        )

        if not has_position:
            logger.warning(f"⚠️ Position verification failed: {error_msg}")
            logger.info("   Resetting to SCANNING to find new market")

            self.state_manager.reset_position(self.state)
            self.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.state)
            return True

        # Update filled_amount if actual differs from expected
        if abs(actual_tokens - filled_amount) > 0.01:
            logger.info(f"   Updating filled_amount: {filled_amount:.4f} → {actual_tokens:.4f}")
            filled_amount = actual_tokens
            position['filled_amount'] = actual_tokens
            self.state_manager.save_state(self.state)

        # Check if position is dust
        dust_result = self.validator.check_dust_position_by_shares(filled_amount)

        if not dust_result.is_valid:
            # Reset and find new market
            self.state_manager.reset_position(self.state)
            self.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.state)
            return True

        # Get fresh orderbook for SELL pricing
        try:
            fresh_orderbook = self.scanner.get_fresh_orderbook(market_id, token_id)

            if not fresh_orderbook:
                logger.error("Failed to get orderbook for SELL")
                return False

            best_bid = fresh_orderbook['best_bid']
            best_ask = fresh_orderbook['best_ask']

            # Check if order value meets minimum
            value_result = self.validator.check_dust_position_by_value(filled_amount, best_ask)

            if not value_result.is_valid:
                # Reset and find new market
                self.state_manager.reset_position(self.state)
                self.state['stage'] = 'SCANNING'
                self.state_manager.save_state(self.state)
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

            # Calculate SELL price
            sell_price = self.pricing.calculate_sell_price(best_bid, best_ask)

            logger.info(f"   SELL price: {format_price(sell_price)}")

            # Check for dust accumulation
            logger.info("🔍 Checking for existing dust position on this market...")

            try:
                existing_shares = self.client.get_position_shares(
                    market_id=market_id,
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
                    self.state_manager.save_state(self.state)

                    logger.info(f"   📝 Updated SELL amount: {old_amount:.4f} → {filled_amount:.4f} shares")
                elif existing_amount < filled_amount:
                    # API shows LESS than expected - possible manual sale
                    logger.warning(f"   ⚠️ API shows LESS shares than expected!")
                    logger.warning(f"   Using API value (more accurate)")

                    filled_amount = existing_amount
                    position['filled_amount'] = filled_amount
                    self.state_manager.save_state(self.state)

                    # Re-check if still above dust threshold
                    if filled_amount < 5.0:
                        logger.warning("   ⚠️ After adjustment, position is now dust!")
                        logger.info("   Abandoning and resetting to SCANNING")
                        self.state_manager.reset_position(self.state)
                        self.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.state)
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

            self.state['stage'] = 'SELL_PLACED'
            self.state_manager.save_state(self.state)

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
