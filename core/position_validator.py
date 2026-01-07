"""
Position Validator Module
=========================

Extracted from autonomous_bot.py to eliminate code duplication.

Handles validation of positions:
- token_id validation and recovery
- Dust position detection
- Manual sale detection
- Order value validation

This consolidates validation logic that was repeated 10+ times across autonomous_bot.py.
"""

from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
import math

from logger_config import setup_logger
from config import (
    MIN_ORDER_VALUE_USDT,
    MIN_SELLABLE_SHARES,
    DUST_THRESHOLD,
    MANUAL_SALE_THRESHOLD_PERCENT
)

logger = setup_logger(__name__)


class ValidationResult:
    """Result of position validation."""

    def __init__(self, is_valid: bool, reason: str = "", action: str = "continue"):
        """
        Initialize validation result.

        Args:
            is_valid: Whether position passed validation
            reason: Reason for validation failure (if any)
            action: Recommended action ('continue', 'reset_to_scanning', 'abandon')
        """
        self.is_valid = is_valid
        self.reason = reason
        self.action = action

    def __bool__(self):
        """Allow using result in boolean context."""
        return self.is_valid


class PositionValidator:
    """
    Validates positions and detects issues like dust, manual sales, invalid token_ids.

    This class consolidates validation logic that was duplicated across autonomous_bot.py.
    """

    def __init__(self, client, config: Dict[str, Any]):
        """
        Initialize position validator.

        Args:
            client: OpinionClient instance for API calls
            config: Bot configuration dictionary
        """
        self.client = client
        self.config = config

        # Extract thresholds from config (with fallback to module-level constants)
        self.min_order_value = config.get('MIN_ORDER_VALUE_USDT', MIN_ORDER_VALUE_USDT)
        self.min_sellable_shares = config.get('MIN_SELLABLE_SHARES', MIN_SELLABLE_SHARES)
        self.dust_threshold = config.get('DUST_THRESHOLD', DUST_THRESHOLD)
        self.manual_sale_threshold = config.get('MANUAL_SALE_THRESHOLD_PERCENT', MANUAL_SALE_THRESHOLD_PERCENT)

    def validate_token_id(self, token_id: Any, market_id: int, outcome_side: str = "YES") -> Tuple[bool, Optional[str]]:
        """
        Validate token_id is valid string (not int/None/invalid).

        Args:
            token_id: Token ID to validate
            market_id: Market ID (for recovery)
            outcome_side: Outcome side ("YES" or "NO")

        Returns:
            Tuple of (is_valid, recovered_token_id or None)

        Example:
            >>> valid, token_id = validator.validate_token_id(123, 456, "YES")
            >>> if not valid:
            ...     # Attempt recovery
            ...     pass
        """
        logger.debug(f"🔍 Validating token_id: {token_id} (type: {type(token_id).__name__})")

        # Check if token_id is valid
        if token_id and isinstance(token_id, str) and token_id != 'unknown':
            logger.debug(f"✅ token_id is valid: {token_id[:20]}...")
            return (True, token_id)

        # Invalid token_id - attempt recovery
        logger.warning(f"❌ Invalid token_id: {token_id} (type: {type(token_id).__name__})")
        logger.info(f"🔄 Attempting recovery from market #{market_id} details...")

        try:
            market_details = self.client.get_market(market_id)

            if not market_details:
                logger.error(f"   ❌ Could not fetch market #{market_id}")
                return (False, None)

            # Extract correct token_id based on outcome side
            if outcome_side.upper() == 'YES':
                recovered_token_id = market_details.get('yes_token_id', '')
            else:
                recovered_token_id = market_details.get('no_token_id', '')

            if recovered_token_id:
                logger.info(f"   ✅ Recovered token_id: {recovered_token_id[:20]}...")
                return (True, recovered_token_id)
            else:
                logger.error(f"   ❌ Market details missing token_id field")
                return (False, None)

        except Exception as e:
            logger.error(f"   ❌ Recovery failed: {e}")
            return (False, None)

    def check_dust_position_by_shares(self, filled_amount: float) -> ValidationResult:
        """
        Check if position is too small to sell (dust by share count).

        Args:
            filled_amount: Number of shares in position

        Returns:
            ValidationResult indicating if position is dust

        Example:
            >>> result = validator.check_dust_position_by_shares(3.5)
            >>> if not result:
            ...     print(f"Dust detected: {result.reason}")
        """
        if filled_amount < self.min_sellable_shares:
            logger.warning("=" * 70)
            logger.warning(f"⚠️  DUST POSITION DETECTED!")
            logger.warning(f"   Position: {filled_amount:.4f} shares")
            logger.warning(f"   Minimum: {self.min_sellable_shares:.1f} shares")
            logger.warning(f"   Positions below {self.min_sellable_shares:.1f} shares are too small to sell")
            logger.warning(f"   Dust will be accumulated with future positions on same market")
            logger.warning("=" * 70)
            logger.info("")

            return ValidationResult(
                is_valid=False,
                reason=f"Dust position: {filled_amount:.4f} shares < {self.min_sellable_shares} minimum",
                action="reset_to_scanning"
            )

        logger.debug(f"✅ Position size OK: {filled_amount:.4f} shares (>= {self.min_sellable_shares} minimum)")
        return ValidationResult(is_valid=True)

    def check_dust_position_by_value(
        self,
        filled_amount: float,
        price: float
    ) -> ValidationResult:
        """
        Check if position value (shares × price) meets minimum order value.

        This is critical because API requires minimum $1.30 order value.
        A position with 3.0 tokens @ $0.40 = $1.20 < $1.30 → DUST!

        Args:
            filled_amount: Number of shares
            price: Current price per share

        Returns:
            ValidationResult indicating if order value is sufficient

        Example:
            >>> result = validator.check_dust_position_by_value(3.0, 0.40)
            >>> if not result:
            ...     # Order value too low ($1.20 < $1.30)
            ...     pass
        """
        # Calculate order value after floor rounding (API behavior)
        sellable_amount = math.floor(filled_amount * 10) / 10
        estimated_order_value = sellable_amount * price

        if estimated_order_value < self.min_order_value:
            logger.warning("=" * 70)
            logger.warning(f"⚠️  DUST POSITION DETECTED (order value too low)!")
            logger.warning(f"   Position: {filled_amount:.4f} shares")
            logger.warning(f"   After floor: {sellable_amount:.1f} shares")
            logger.warning(f"   Price: ${price:.4f}")
            logger.warning(f"   Order value: ${estimated_order_value:.2f}")
            logger.warning(f"   API minimum: ${self.min_order_value:.2f}")
            logger.warning(f"   Cannot sell - order value too low!")
            logger.warning("=" * 70)
            logger.info("")

            return ValidationResult(
                is_valid=False,
                reason=f"Order value ${estimated_order_value:.2f} < ${self.min_order_value:.2f} minimum",
                action="reset_to_scanning"
            )

        logger.debug(f"✅ Position value OK: ${estimated_order_value:.2f} (>= ${self.min_order_value:.2f} minimum)")
        return ValidationResult(is_valid=True)

    def detect_manual_sale(
        self,
        expected_tokens: float,
        actual_tokens: float
    ) -> ValidationResult:
        """
        Detect if position was sold manually (via web interface).

        If user manually sold tokens, state.json will have incorrect filled_amount.
        We detect this by comparing expected vs actual position size.

        Args:
            expected_tokens: Expected tokens from state.json
            actual_tokens: Actual tokens from API

        Returns:
            ValidationResult indicating if manual sale detected

        Example:
            >>> result = validator.detect_manual_sale(100.0, 5.0)
            >>> if not result:
            ...     print("Manual sale detected - 95% of tokens missing")
        """
        if expected_tokens <= 0:
            return ValidationResult(is_valid=True)  # No expected tokens = nothing to check

        difference = expected_tokens - actual_tokens
        difference_pct = (difference / expected_tokens) * 100

        logger.debug(f"   Expected: {expected_tokens:.4f} tokens")
        logger.debug(f"   Actual: {actual_tokens:.4f} tokens")
        logger.debug(f"   Difference: {difference:.4f} tokens ({difference_pct:.1f}%)")

        if difference_pct > self.manual_sale_threshold:
            logger.warning("=" * 70)
            logger.warning("⚠️  MANUAL SALE DETECTED!")
            logger.warning(f"   Expected {expected_tokens:.4f} tokens but found only {actual_tokens:.4f}")
            logger.warning(f"   {difference_pct:.1f}% of position is missing (threshold: {self.manual_sale_threshold}%)")
            logger.warning("   Position was likely sold manually via web interface")
            logger.warning("=" * 70)
            logger.info("")

            # Check if remaining tokens are dust
            if actual_tokens < self.dust_threshold:
                logger.info("💡 Action: Remaining position is dust - resetting to SCANNING")
                logger.info(f"   Dust positions ({actual_tokens:.4f} tokens) are too small to sell")
                logger.info(f"   Dust will be accumulated with future positions on this market")
                action = "reset_to_scanning"
            else:
                logger.info("💡 Action: Resetting to SCANNING to find new market")
                logger.info(f"   Manual sale has left {actual_tokens:.4f} tokens")
                action = "reset_to_scanning"

            logger.info("")

            return ValidationResult(
                is_valid=False,
                reason=f"Manual sale detected: {difference_pct:.1f}% of position missing",
                action=action
            )

        # Moderate difference (5-95%) - update filled_amount
        elif difference_pct > 5.0:
            logger.warning(f"⚠️  Position mismatch: {difference_pct:.1f}% difference")
            logger.info(f"   Updating filled_amount to actual: {actual_tokens:.4f}")
            # Caller should update filled_amount
            return ValidationResult(
                is_valid=True,
                reason=f"Position mismatch: {difference_pct:.1f}% difference (updated to actual)"
            )

        return ValidationResult(is_valid=True)

    def verify_actual_position(
        self,
        market_id: int,
        outcome_side: str,
        expected_tokens: Optional[float] = None
    ) -> Tuple[bool, float, Optional[str]]:
        """
        Verify actual position from API and compare to expected.

        This consolidates the common pattern of:
        1. Fetching position from API
        2. Comparing to expected value
        3. Detecting manual sales

        Args:
            market_id: Market ID
            outcome_side: Outcome side ("YES" or "NO")
            expected_tokens: Expected token count (for manual sale detection)

        Returns:
            Tuple of (has_position, actual_tokens, error_message)

        Example:
            >>> has_pos, tokens, err = validator.verify_actual_position(123, "YES", 50.0)
            >>> if not has_pos:
            ...     print(f"Position check failed: {err}")
        """
        logger.info("🔍 Verifying actual position vs state.json...")

        try:
            verified_shares = self.client.get_position_shares(
                market_id=market_id,
                outcome_side=outcome_side
            )
            actual_tokens = float(verified_shares)

            logger.info(f"   Actual position: {actual_tokens:.4f} tokens (from API)")

            # If expected_tokens provided, check for manual sale
            if expected_tokens is not None:
                result = self.detect_manual_sale(expected_tokens, actual_tokens)
                if not result:
                    return (False, actual_tokens, result.reason)

            return (True, actual_tokens, None)

        except Exception as e:
            logger.warning(f"⚠️ Could not verify position (non-critical): {e}")
            return (True, expected_tokens if expected_tokens else 0.0, None)  # Non-blocking error
