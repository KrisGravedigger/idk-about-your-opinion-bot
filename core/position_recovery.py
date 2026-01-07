"""
Position Recovery Module
========================

Extracted from autonomous_bot.py to eliminate code duplication.

Handles self-healing and position recovery:
- Recover order_id from API when state.json has 'unknown'
- Recover token_id from market details
- Find orphaned positions after bot restart
- Detect filled orders that aren't in state

This consolidates recovery logic that was repeated 5+ times across autonomous_bot.py.
"""

from typing import Dict, Any, Optional, Tuple, List
from decimal import Decimal

from logger_config import setup_logger
from utils import get_timestamp

logger = setup_logger(__name__)


class RecoveryResult:
    """Result of position recovery attempt."""

    def __init__(
        self,
        success: bool,
        order_id: Optional[str] = None,
        token_id: Optional[str] = None,
        filled_amount: Optional[float] = None,
        reason: str = ""
    ):
        """
        Initialize recovery result.

        Args:
            success: Whether recovery was successful
            order_id: Recovered order ID (if any)
            token_id: Recovered token ID (if any)
            filled_amount: Recovered fill amount (if any)
            reason: Reason for failure or success details
        """
        self.success = success
        self.order_id = order_id
        self.token_id = token_id
        self.filled_amount = filled_amount
        self.reason = reason

    def __bool__(self):
        """Allow using result in boolean context."""
        return self.success


class PositionRecovery:
    """
    Handles position recovery and self-healing after bot restarts or errors.

    This class consolidates recovery logic that was duplicated across autonomous_bot.py.
    """

    def __init__(self, client, config: Dict[str, Any]):
        """
        Initialize position recovery.

        Args:
            client: OpinionClient instance for API calls
            config: Bot configuration dictionary
        """
        self.client = client
        self.config = config

    def recover_order_id_from_api(
        self,
        market_id: int,
        expected_side: str = "BUY"
    ) -> RecoveryResult:
        """
        Recover order_id from API when state has 'unknown'.

        This happens when bot recovered from orphaned PENDING order.

        Args:
            market_id: Market ID to search for orders
            expected_side: Expected order side ("BUY" or "SELL")

        Returns:
            RecoveryResult with recovered order_id or failure reason

        Example:
            >>> result = recovery.recover_order_id_from_api(123, "BUY")
            >>> if result:
            ...     print(f"Recovered order: {result.order_id}")
        """
        logger.warning("⚠️ order_id is 'unknown' - attempting to recover from API...")
        logger.info("   This happens when bot recovered from orphaned PENDING order")
        logger.info("")

        try:
            # Use FILLED status (paradoxically includes pending orders with $0 filled)
            # Same logic as in autonomous_bot_main.py recovery
            orders = self.client.get_my_orders(
                market_id=market_id,
                status='FILLED',  # Status "1" includes orders with any fill amount (even $0!)
                limit=20
            )

            # 🔍 DEBUG: Log ALL order details
            logger.info(f"🔍 DEBUG: API returned {len(orders)} orders:")
            for i, order in enumerate(orders):
                logger.info(f"   Order #{i+1}:")
                logger.info(f"      order_id: {order.get('order_id', 'N/A')}")
                logger.info(f"      status: {order.get('status', 'N/A')} ({order.get('status_str', 'N/A')})")
                logger.info(f"      side: {order.get('side', 'N/A')}")
                logger.info(f"      price: {order.get('price', 'N/A')}")

                # Check if order is truly pending (filled_amount near 0)
                order_amount = float(order.get('order_amount', 0) or 0)
                filled_amount = float(order.get('filled_amount', 0) or 0)

                logger.info(f"      order_amount: ${order_amount:.2f}")
                logger.info(f"      filled_amount: ${filled_amount:.2f}")

                # Skip if already significantly filled
                if filled_amount > 0.10:
                    logger.info(f"      ⏭️  Skipping - already filled ${filled_amount:.2f}")
                    continue

                # Skip if no meaningful order_amount
                if order_amount < 0.10:
                    logger.info(f"      ⏭️  Skipping - dust order (amount < $0.10)")
                    continue

                # Check side matches
                order_side_num = order.get('side', 0)
                order_side = 'BUY' if order_side_num == 1 else 'SELL'
                if order_side != expected_side:
                    logger.info(f"      ⏭️  Skipping - wrong side ({order_side} != {expected_side})")
                    continue

                # This is our pending order!
                recovered_order_id = order.get('order_id')
                logger.info(f"   ✅ Selected order: {recovered_order_id}")

                logger.info(f"✅ Found pending {expected_side} order on market #{market_id}")
                logger.info(f"   Order ID: {recovered_order_id}")
                logger.info(f"   Price: ${float(order.get('price', 0)):.4f}")
                logger.info(f"   Amount: ${order_amount:.2f}")
                logger.info("")

                return RecoveryResult(
                    success=True,
                    order_id=recovered_order_id,
                    reason=f"Recovered {expected_side} order from API"
                )

            # No pending orders found
            logger.warning("⚠️ No pending orders found on this market")
            logger.info("")

            return RecoveryResult(
                success=False,
                reason="No pending orders found in API"
            )

        except Exception as e:
            logger.error(f"❌ Could not recover order_id: {e}")
            logger.info("")
            return RecoveryResult(
                success=False,
                reason=f"API error: {e}"
            )

    def recover_token_id_from_market(
        self,
        market_id: int,
        outcome_side: str = "YES"
    ) -> RecoveryResult:
        """
        Recover token_id from market details.

        This is needed when state has invalid token_id (int, None, 'unknown').

        Args:
            market_id: Market ID
            outcome_side: Outcome side ("YES" or "NO")

        Returns:
            RecoveryResult with recovered token_id or failure reason

        Example:
            >>> result = recovery.recover_token_id_from_market(123, "YES")
            >>> if result:
            ...     print(f"Recovered token_id: {result.token_id}")
        """
        logger.info("🔍 Recovering token_id from market details...")

        try:
            # Fetch market using get_market() method
            market_details = self.client.get_market(market_id)

            if not market_details:
                logger.warning(f"   ⚠️ Could not fetch market #{market_id} details")
                return RecoveryResult(
                    success=False,
                    reason=f"Market #{market_id} not found"
                )

            # Extract correct token_id based on outcome side
            if outcome_side.upper() == 'YES':
                token_id = market_details.get('yes_token_id', '')
            else:
                token_id = market_details.get('no_token_id', '')

            if token_id:
                logger.info(f"   ✅ Recovered token_id: {token_id[:20] if len(token_id) > 20 else token_id}...")
                return RecoveryResult(
                    success=True,
                    token_id=token_id,
                    reason="Recovered from market details"
                )
            else:
                logger.warning(f"   ⚠️ No token_id found in market details")
                return RecoveryResult(
                    success=False,
                    reason="Market details missing token_id field"
                )

        except Exception as e:
            logger.warning(f"   ⚠️ Failed to recover token_id: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return RecoveryResult(
                success=False,
                reason=f"Exception: {e}"
            )

    def check_if_already_filled(
        self,
        market_id: int,
        outcome_side: str = "YES"
    ) -> Tuple[bool, float]:
        """
        Check if order already filled by verifying position.

        This handles case where order filled but state wasn't updated.

        Args:
            market_id: Market ID
            outcome_side: Outcome side ("YES" or "NO")

        Returns:
            Tuple of (is_filled, tokens_amount)

        Example:
            >>> is_filled, tokens = recovery.check_if_already_filled(123, "YES")
            >>> if is_filled:
            ...     print(f"Order filled: {tokens} tokens")
        """
        logger.info("   Checking if order already filled...")

        try:
            verified_shares = self.client.get_position_shares(
                market_id=market_id,
                outcome_side=outcome_side
            )
            tokens = float(verified_shares)

            if tokens >= 1.0:
                logger.info(f"✅ Order already filled! Found {tokens:.4f} tokens")
                return (True, tokens)
            else:
                logger.debug(f"   No significant position found ({tokens:.4f} tokens)")
                return (False, tokens)

        except Exception as e:
            logger.warning(f"⚠️ Could not check position: {e}")
            return (False, 0.0)

    def find_orphaned_positions(
        self,
        min_shares: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        Find orphaned positions (bot restarted with existing positions).

        This searches for significant positions that aren't tracked in state.json.

        Args:
            min_shares: Minimum shares to consider (filter dust)

        Returns:
            List of orphaned position dictionaries

        Example:
            >>> positions = recovery.find_orphaned_positions(min_shares=5.0)
            >>> for pos in positions:
            ...     print(f"Orphaned: {pos['market_id']} - {pos['shares']:.2f} shares")
        """
        logger.info(f"🔍 Searching for orphaned positions (min {min_shares} shares)...")

        try:
            positions = self.client.get_significant_positions(min_shares=min_shares)

            if not positions:
                logger.debug("   No orphaned positions found")
                return []

            logger.info(f"✅ Found {len(positions)} orphaned positions:")
            for i, pos in enumerate(positions, 1):
                market_id = pos.get('market_id', 'unknown')
                shares = pos.get('shares_owned', 0)
                outcome = pos.get('outcome_side', 'UNKNOWN')
                logger.info(f"   {i}. Market #{market_id}: {shares:.2f} {outcome} shares")

            return positions

        except Exception as e:
            logger.warning(f"⚠️ Could not search for orphaned positions: {e}")
            return []

    def recover_fill_data_from_position(
        self,
        market_id: int,
        outcome_side: str,
        order_price: float
    ) -> RecoveryResult:
        """
        Recover fill data from actual position when order data is missing.

        Args:
            market_id: Market ID
            outcome_side: Outcome side ("YES" or "NO")
            order_price: Original order price (fallback for avg_fill_price)

        Returns:
            RecoveryResult with fill data

        Example:
            >>> result = recovery.recover_fill_data_from_position(123, "YES", 0.50)
            >>> if result:
            ...     print(f"Recovered {result.filled_amount} tokens")
        """
        logger.info("🔄 Recovering fill data from actual position...")

        try:
            verified_shares = self.client.get_position_shares(
                market_id=market_id,
                outcome_side=outcome_side
            )
            filled_amount = float(verified_shares)

            if filled_amount > 0:
                logger.info(f"✅ Recovered filled_amount: {filled_amount:.10f} tokens")

                # Use order price as avg_fill_price (best we can do)
                avg_fill_price = order_price if order_price > 0 else 0.01

                return RecoveryResult(
                    success=True,
                    filled_amount=filled_amount,
                    reason=f"Recovered from position API"
                )
            else:
                logger.warning("⚠️ No position found")
                return RecoveryResult(
                    success=False,
                    reason="Position not found or zero tokens"
                )

        except Exception as e:
            logger.error(f"❌ Failed to recover fill data: {e}")
            return RecoveryResult(
                success=False,
                reason=f"Exception: {e}"
            )
