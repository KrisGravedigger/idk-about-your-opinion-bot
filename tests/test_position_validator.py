"""
Unit tests for PositionValidator

Tests validation logic for dust positions, token IDs, and manual sales.
"""

import unittest
from unittest.mock import Mock, MagicMock
from core.position_validator import PositionValidator, ValidationResult


class TestPositionValidator(unittest.TestCase):
    """Test suite for PositionValidator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock()
        self.config = {
            'MIN_ORDER_VALUE_USDT': 1.30,
            'MIN_SELLABLE_SHARES': 5.0,
            'DUST_THRESHOLD': 5.0,
            'MANUAL_SALE_THRESHOLD_PERCENT': 95.0
        }
        self.validator = PositionValidator(self.mock_client, self.config)

    def test_check_dust_position_by_shares_valid(self):
        """Test dust check with valid position (>= 5.0 shares)."""
        result = self.validator.check_dust_position_by_shares(10.0)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.action, 'continue')

    def test_check_dust_position_by_shares_dust(self):
        """Test dust check with dust position (< 5.0 shares)."""
        result = self.validator.check_dust_position_by_shares(3.0)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.action, 'reset_to_scanning')
        self.assertIn('dust', result.reason.lower())

    def test_check_dust_position_by_value_valid(self):
        """Test dust check by value with valid position."""
        # 10 shares @ $0.50 = $5.00 > $1.30 minimum
        result = self.validator.check_dust_position_by_value(10.0, 0.50)

        self.assertTrue(result.is_valid)

    def test_check_dust_position_by_value_dust(self):
        """Test dust check by value with dust position."""
        # 3 shares @ $0.40 = $1.20 < $1.30 minimum (after floor rounding)
        result = self.validator.check_dust_position_by_value(3.0, 0.40)

        self.assertFalse(result.is_valid)
        self.assertIn('value', result.reason.lower())

    def test_validate_token_id_valid_string(self):
        """Test token ID validation with valid string."""
        valid_token = "0x1234567890abcdef"

        is_valid, recovered = self.validator.validate_token_id(
            valid_token, 123, "YES"
        )

        self.assertTrue(is_valid)
        self.assertEqual(recovered, valid_token)

    def test_validate_token_id_invalid_int(self):
        """Test token ID validation with invalid int type."""
        self.mock_client.get_market.return_value = Mock(
            yes_token_id="0xrecovered123"
        )

        is_valid, recovered = self.validator.validate_token_id(
            12345,  # Invalid: int instead of string
            123,
            "YES"
        )

        # Should attempt recovery
        self.mock_client.get_market.assert_called_once_with(123)
        self.assertEqual(recovered, "0xrecovered123")

    def test_validate_token_id_recovery_failure(self):
        """Test token ID validation when recovery fails."""
        self.mock_client.get_market.return_value = None

        is_valid, recovered = self.validator.validate_token_id(
            None,  # Invalid
            123,
            "YES"
        )

        self.assertFalse(is_valid)
        self.assertIsNone(recovered)

    def test_detect_manual_sale_no_sale(self):
        """Test manual sale detection when position is intact."""
        self.mock_client.get_position_shares.return_value = "100.0"

        result = self.validator.detect_manual_sale(
            expected_tokens=100.0,
            actual_tokens=100.0
        )

        self.assertTrue(result.is_valid)

    def test_detect_manual_sale_detected(self):
        """Test manual sale detection when >95% missing."""
        result = self.validator.detect_manual_sale(
            expected_tokens=100.0,
            actual_tokens=2.0  # 98% missing
        )

        self.assertFalse(result.is_valid)
        self.assertIn('manual', result.reason.lower())
        self.assertEqual(result.action, 'reset_to_scanning')

    def test_verify_actual_position_success(self):
        """Test position verification with matching position."""
        self.mock_client.get_position_shares.return_value = "50.0"

        has_position, actual_tokens, error_msg = self.validator.verify_actual_position(
            market_id=123,
            outcome_side="YES",
            expected_tokens=50.0
        )

        self.assertTrue(has_position)
        self.assertEqual(actual_tokens, 50.0)
        self.assertIsNone(error_msg)

    def test_verify_actual_position_manual_sale(self):
        """Test position verification detecting manual sale."""
        self.mock_client.get_position_shares.return_value = "1.0"  # 98% missing

        has_position, actual_tokens, error_msg = self.validator.verify_actual_position(
            market_id=123,
            outcome_side="YES",
            expected_tokens=100.0
        )

        self.assertFalse(has_position)
        self.assertIsNotNone(error_msg)
        self.assertIn('manual', error_msg.lower())


class TestValidationResult(unittest.TestCase):
    """Test suite for ValidationResult class."""

    def test_validation_result_creation(self):
        """Test ValidationResult object creation."""
        result = ValidationResult(
            is_valid=False,
            reason="Test reason",
            action="reset_to_scanning"
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.reason, "Test reason")
        self.assertEqual(result.action, "reset_to_scanning")

    def test_validation_result_defaults(self):
        """Test ValidationResult default values."""
        result = ValidationResult(is_valid=True)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.reason, "")
        self.assertEqual(result.action, "continue")


if __name__ == '__main__':
    unittest.main()
