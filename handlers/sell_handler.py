"""
SELL Handler
============

Handles all SELL-related stages:
- SELL_PLACED: Transition to monitoring
- SELL_MONITORING: Monitor order until filled

Extracted from AutonomousBot to improve code organization.
"""

from datetime import datetime, timedelta
from typing import Dict, Any

from logger_config import setup_logger
from utils import get_timestamp
from monitoring.sell_monitor import SellMonitor

logger = setup_logger(__name__)


class SellHandler:
    """
    Handles SELL-related trading stages.

    Manages order monitoring and position tracking for SELL orders.
    """

    def __init__(self, bot):
        """
        Initialize SELL handler.

        Args:
            bot: AutonomousBot instance (for access to client, config, etc.)
        """
        self.bot = bot
        self.client = bot.client
        self.config = bot.config
        self.state = bot.state
        self.state_manager = bot.state_manager
        self.validator = bot.validator
        self.tracker = bot.tracker
        self.telegram = bot.telegram

    def handle_sell_placed(self) -> bool:
        """
        SELL_PLACED stage: SELL order placed, ready to monitor.

        Transitions to: SELL_MONITORING
        """
        logger.info("📋 SELL_PLACED - Transitioning to monitoring")

        # Simply transition to monitoring
        self.state['stage'] = 'SELL_MONITORING'
        self.state_manager.save_state(self.state)

        return True

    def handle_sell_monitoring(self) -> bool:
        """
        SELL_MONITORING stage: Monitor SELL order until filled.

        Transitions to: COMPLETED (if filled)
        Transitions to: BUY_FILLED (if cancelled/expired - retry)
        Transitions to: SCANNING (if stop-loss/deteriorated)
        """
        logger.info("⏳ SELL_MONITORING - Waiting for fill...")

        position = self.state['current_position']
        sell_order_id = position['sell_order_id']
        market_id = position['market_id']

        # SELF-HEALING: Verify order is still active before starting monitor
        logger.info("🔍 Verifying SELL order status before monitoring...")
        try:
            # Get full order details
            order_details = self.client.get_order(sell_order_id)

            # Initialize variables
            order_is_terminal = False
            is_cancelled = False
            is_fully_filled = False

            if not order_details:
                logger.warning("⚠️ SELL order not found in API")
                order_is_terminal = True
            else:
                order_status = order_details.get('status_str', 'UNKNOWN')
                order_filled_amount = float(order_details.get('filled_amount', 0) or 0)
                order_amount = float(order_details.get('order_amount', 0) or 0)

                logger.info(f"   Order status: {order_status}")
                logger.info(f"   Filled: ${order_filled_amount:.2f} / ${order_amount:.2f}")

                # Calculate fill percentage
                fill_percentage = (order_filled_amount / order_amount * 100) if order_amount > 0 else 0

                # Check if order is TRULY terminal
                is_fully_filled = (fill_percentage >= 99.0)
                is_cancelled = (order_status == 'CANCELLED')

                if is_cancelled:
                    logger.warning(f"⚠️ SELL order was CANCELLED")
                    order_is_terminal = True
                elif is_fully_filled:
                    logger.info(f"✅ SELL order is fully FILLED ({fill_percentage:.1f}% = ${order_filled_amount:.2f})")
                    order_is_terminal = True
                else:
                    logger.info(f"✅ Order is active ({fill_percentage:.1f}% filled) - starting monitor")
                    order_is_terminal = False

            # If order is terminal, check position and decide what to do
            if order_is_terminal:
                logger.info("🔄 Checking if position still exists...")

                # Check for manual sale using validator
                outcome_side = position.get('outcome_side', 'YES')
                expected_tokens = position.get('filled_amount', 0)

                has_position, tokens, error_msg = self.validator.verify_actual_position(
                    market_id, outcome_side, expected_tokens=expected_tokens
                )

                if not has_position:
                    logger.warning(f"⚠️ Manual sale detected: {error_msg}")
                    logger.info("💡 Action: Resetting to SCANNING")

                    # Reset and find new market
                    self.state_manager.reset_position(self.state)
                    self.state['stage'] = 'SCANNING'
                    self.state_manager.save_state(self.state)
                    return True

                if tokens >= 1.0:  # Still have significant tokens
                    logger.info(f"✅ Still have {tokens:.4f} tokens")
                    logger.info(f"   Order is terminal but tokens remain - going back to BUY_FILLED to place new SELL")

                    # Update filled_amount in case it changed
                    position['filled_amount'] = tokens

                    # Remove old SELL order data
                    if 'sell_order_id' in position:
                        del position['sell_order_id']
                    if 'sell_price' in position:
                        del position['sell_price']

                    self.state['stage'] = 'BUY_FILLED'
                    self.state_manager.save_state(self.state)
                    return True

                else:
                    logger.warning(f"⚠️ No significant tokens found (only {tokens:.4f})")

                    if order_details and is_fully_filled:
                        logger.info(f"   SELL order completed successfully")
                        logger.info("   Marking as COMPLETED")
                        self.state['stage'] = 'COMPLETED'
                        self.state_manager.save_state(self.state)
                        return True
                    else:
                        logger.info(f"   Order terminal without completion - resetting to SCANNING")

                        self.state_manager.reset_position(self.state)
                        self.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.state)
                        return True

            # If we reach here, order is NOT terminal - proceed with monitoring

        except Exception as e:
            logger.warning(f"⚠️ Could not verify SELL order status: {e}")
            logger.info("   Proceeding with normal monitoring (may fail if order doesn't exist)")

        # Calculate timeout based on when SELL order was originally placed
        timeout_hours = self.config['SELL_ORDER_TIMEOUT_HOURS']

        sell_placed_at_str = position.get('sell_placed_at')
        if sell_placed_at_str:
            try:
                sell_placed_at = datetime.fromisoformat(sell_placed_at_str.replace('Z', '+00:00'))
                timeout_at = sell_placed_at + timedelta(hours=timeout_hours)
                logger.debug(f"Using sell_placed_at from state: {sell_placed_at_str}")
                logger.debug(f"Timeout at: {timeout_at.strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception as e:
                logger.warning(f"Could not parse sell_placed_at '{sell_placed_at_str}': {e}")
                logger.info("Falling back to current time for timeout calculation")
                timeout_at = datetime.now() + timedelta(hours=timeout_hours)
        else:
            logger.debug("No sell_placed_at in state, using current time for timeout")
            timeout_at = datetime.now() + timedelta(hours=timeout_hours)

        # Create monitor and start monitoring
        monitor = SellMonitor(self.config, self.client, self.state, heartbeat_callback=self.bot._check_and_send_heartbeat)

        result = monitor.monitor_until_filled(sell_order_id, timeout_at)

        status = result['status']

        # Handle different outcomes
        if status == 'filled':
            logger.info("✅ SELL order filled!")

            # Update state with fill data
            position['sell_filled_amount'] = result['filled_amount']
            position['avg_sell_price'] = result['avg_fill_price']
            position['sell_proceeds'] = result['filled_usdt']
            position['sell_fill_timestamp'] = result['fill_timestamp']

            # Calculate P&L
            pnl = self.tracker.calculate_pnl(
                buy_cost_usdt=position['filled_usdt'],
                buy_tokens=position['filled_amount'],
                buy_price=position['avg_fill_price'],
                sell_tokens=result['filled_amount'],
                sell_price=result['avg_fill_price']
            )

            # Display P&L
            self.tracker.display_pnl(pnl)

            # Add to history
            self.tracker.add_to_history(pnl, position['market_id'])

            # Update statistics
            self.bot._update_statistics(pnl)

            self.state['stage'] = 'COMPLETED'
            self.state_manager.save_state(self.state)

            return True

        elif status in ['cancelled', 'canceled', 'expired']:
            logger.warning(f"SELL order {status}: {result.get('reason')}")
            logger.info("Retrying SELL order...")

            # Go back to BUY_FILLED to place new SELL
            self.state['stage'] = 'BUY_FILLED'

            # Clear old SELL data
            if 'sell_order_id' in position:
                del position['sell_order_id']
            if 'sell_price' in position:
                del position['sell_price']

            self.state_manager.save_state(self.state)

            return True

        elif status == 'stop_loss_triggered':
            logger.warning(f"🛑 Stop-loss triggered: {result.get('reason')}")
            logger.info("Position closed at loss - finding new market...")

            # Send Telegram notification
            current_price = result.get('current_price', 0)
            buy_price = position.get('avg_fill_price', 0)
            pnl_percent = result.get('pnl_percent', 0)

            self.telegram.send_stop_loss(
                market_id=position.get('market_id', 0),
                market_title=position.get('market_title', 'Unknown market'),
                current_price=current_price,
                buy_price=buy_price,
                pnl_percent=pnl_percent,
                action='triggered'
            )

            # Update statistics (record as loss)
            stats = self.state['statistics']
            stats['losses'] += 1
            stats['consecutive_losses'] += 1

            # Reset position
            self.state_manager.reset_position(self.state)
            self.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.state)

            return True

        elif status in ['timeout', 'deteriorated']:
            logger.warning(f"SELL order {status}: {result.get('reason')}")
            logger.info("Cancelling and finding new market...")

            # Cancel order if still active
            try:
                self.client.cancel_order(sell_order_id)
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
