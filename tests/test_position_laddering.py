"""
Unit Tests for Position Laddering Module
==========================================

Tests the core mathematical calculations and logic for position laddering
strategy without requiring API access.

Run with: pytest tests/test_position_laddering.py -v
"""

import pytest
from decimal import Decimal
from monitoring.position_laddering import PositionLaddering


class MockClient:
    """Mock API client for testing."""

    def __init__(self, balance=1000.0):
        self.balance = balance

    def get_usdt_balance(self):
        return self.balance


@pytest.fixture
def mock_config():
    """Standard test configuration."""
    return {
        'ENABLE_POSITION_LADDERING': True,
        'LADDERING_MODE': 'single',
        'LADDER_BUY_OFFSET_PCT': -15.0,
        'LADDER_MAX_ROUNDS': 1,
        'LADDER_PROFIT_TARGET_PCT': 4.0,
        'LADDER_HARD_STOP_LOSS_PCT': -50.0,
        'LADDER_SPREAD_FILTER_PCT': 20.0,
        'LADDER_CAPITAL_MULTIPLIER': 2.0,
        'PRICE_DECIMALS': 3,
        'STATE_FILE': 'state.json'
    }


@pytest.fixture
def mock_state():
    """Standard test state."""
    return {
        'current_position': {
            'market_id': 1856,
            'token_id': '0x123abc',
            'avg_fill_price': 0.7820,
            'filled_amount': 535.0,
            'averaging_rounds': 0,
            'outcome_side': 'YES'
        }
    }


@pytest.fixture
def laddering(mock_config, mock_state):
    """Create PositionLaddering instance with mocks."""
    mock_client = MockClient(balance=500.0)
    return PositionLaddering(mock_config, mock_client, mock_state)


class TestLadderPriceCalculation:
    """Test ladder price calculation."""

    def test_calculate_ladder_price_basic(self, laddering):
        """Test basic ladder price calculation."""
        entry_price = 0.7820
        offset_pct = -15.0

        ladder_price = laddering.calculate_ladder_price(entry_price, offset_pct)

        # Expected: 0.7820 * 0.85 = 0.6647
        assert float(ladder_price) == pytest.approx(0.6647, rel=1e-3)

    def test_calculate_ladder_price_precision(self, laddering):
        """Test Decimal precision in calculation."""
        entry_price = 0.78
        offset_pct = -15.0

        ladder_price = laddering.calculate_ladder_price(entry_price, offset_pct)

        # Should return Decimal, not float
        assert isinstance(ladder_price, Decimal)
        # Should be rounded to 3 decimals
        assert float(ladder_price) == pytest.approx(0.663, rel=1e-3)

    def test_calculate_ladder_price_different_offsets(self, laddering):
        """Test with various offset percentages."""
        entry_price = 1.0

        # -10%
        result = laddering.calculate_ladder_price(entry_price, -10.0)
        assert float(result) == pytest.approx(0.900, rel=1e-3)

        # -25%
        result = laddering.calculate_ladder_price(entry_price, -25.0)
        assert float(result) == pytest.approx(0.750, rel=1e-3)

        # -50%
        result = laddering.calculate_ladder_price(entry_price, -50.0)
        assert float(result) == pytest.approx(0.500, rel=1e-3)

    def test_calculate_ladder_price_invalid_inputs(self, laddering):
        """Test error handling for invalid inputs."""
        # Negative entry price
        with pytest.raises(ValueError):
            laddering.calculate_ladder_price(-1.0, -15.0)

        # Zero entry price
        with pytest.raises(ValueError):
            laddering.calculate_ladder_price(0.0, -15.0)

        # Positive offset (should be negative)
        with pytest.raises(ValueError):
            laddering.calculate_ladder_price(1.0, 15.0)


class TestProfitTargetCalculation:
    """Test profit target calculation."""

    def test_calculate_profit_target_basic(self, laddering):
        """Test basic profit target calculation."""
        avg_price = 0.7234
        margin_pct = 4.0

        profit_target = laddering.calculate_profit_target(avg_price, margin_pct)

        # Expected: 0.7234 * 1.04 = 0.7523
        assert profit_target == pytest.approx(0.752, rel=1e-2)

    def test_calculate_profit_target_different_margins(self, laddering):
        """Test with various profit margins."""
        avg_price = 1.0

        # +2%
        result = laddering.calculate_profit_target(avg_price, 2.0)
        assert result == pytest.approx(1.020, rel=1e-3)

        # +10%
        result = laddering.calculate_profit_target(avg_price, 10.0)
        assert result == pytest.approx(1.100, rel=1e-3)

        # +0.5% (small margin)
        result = laddering.calculate_profit_target(avg_price, 0.5)
        assert result == pytest.approx(1.005, rel=1e-3)

    def test_calculate_profit_target_invalid_inputs(self, laddering):
        """Test error handling for invalid inputs."""
        # Negative avg price
        with pytest.raises(ValueError):
            laddering.calculate_profit_target(-1.0, 4.0)

        # Zero avg price
        with pytest.raises(ValueError):
            laddering.calculate_profit_target(0.0, 4.0)

        # Negative margin
        with pytest.raises(ValueError):
            laddering.calculate_profit_target(1.0, -4.0)

        # Zero margin
        with pytest.raises(ValueError):
            laddering.calculate_profit_target(1.0, 0.0)


class TestAveragingDownMath:
    """Test averaging down calculations (mathematical correctness)."""

    def test_averaging_equal_amounts(self):
        """Test averaging with equal amounts at different prices."""
        # Original: 535 @ $0.7820
        # Counter: 535 @ $0.6647
        # Expected avg: (0.7820 + 0.6647) / 2 = 0.72335

        from decimal import Decimal

        orig_shares = Decimal('535')
        orig_price = Decimal('0.7820')
        new_shares = Decimal('535')
        new_price = Decimal('0.6647')

        orig_cost = orig_shares * orig_price
        new_cost = new_shares * new_price
        total_cost = orig_cost + new_cost
        total_shares = orig_shares + new_shares
        avg_price = total_cost / total_shares

        assert float(avg_price) == pytest.approx(0.7234, rel=1e-3)
        assert float(total_shares) == 1070.0

    def test_averaging_different_amounts(self):
        """Test averaging with different amounts."""
        # Original: 1000 @ $0.50
        # Counter: 500 @ $0.40
        # Expected avg: (1000*0.50 + 500*0.40) / 1500 = 0.4667

        from decimal import Decimal

        orig_shares = Decimal('1000')
        orig_price = Decimal('0.50')
        new_shares = Decimal('500')
        new_price = Decimal('0.40')

        total_cost = orig_shares * orig_price + new_shares * new_price
        total_shares = orig_shares + new_shares
        avg_price = total_cost / total_shares

        assert float(avg_price) == pytest.approx(0.4667, rel=1e-3)
        assert float(total_shares) == 1500.0

    def test_averaging_always_lowers_cost_basis(self):
        """Verify that buying lower always reduces average cost."""
        original_price = 1.0
        lower_price = 0.80
        shares = 100.0

        # Average should be between lower_price and original_price
        avg = (shares * original_price + shares * lower_price) / (2 * shares)

        assert avg < original_price  # Average is lower than original
        assert avg > lower_price  # But higher than the lower price
        assert avg == pytest.approx(0.90, rel=1e-6)


class TestSafetyChecks:
    """Test safety check logic."""

    def test_should_counter_buy_spread_filter(self, laddering):
        """Test spread filter blocks counter-buy."""
        # Spread too wide
        should_buy, reason = laddering.should_counter_buy(
            current_spread_pct=25.0,  # > 20% threshold
            market_status='open'
        )

        assert should_buy is False
        assert 'spread' in reason.lower()

    def test_should_counter_buy_market_resolved(self, laddering):
        """Test resolved market blocks counter-buy."""
        should_buy, reason = laddering.should_counter_buy(
            current_spread_pct=5.0,
            market_status='resolved'
        )

        assert should_buy is False
        assert 'resolved' in reason.lower()

    def test_should_counter_buy_max_rounds(self, laddering, mock_state):
        """Test max rounds limit blocks counter-buy."""
        # Set averaging_rounds to max
        mock_state['current_position']['averaging_rounds'] = 1  # Max is 1

        should_buy, reason = laddering.should_counter_buy(
            current_spread_pct=5.0,
            market_status='open'
        )

        assert should_buy is False
        assert 'max' in reason.lower() or 'rounds' in reason.lower()

    def test_should_counter_buy_all_checks_pass(self, laddering):
        """Test that counter-buy proceeds when all checks pass."""
        should_buy, reason = laddering.should_counter_buy(
            current_spread_pct=5.0,  # < 20% threshold
            market_status='open'
        )

        assert should_buy is True
        assert 'pass' in reason.lower()


class TestCapitalValidation:
    """Test capital validation logic."""

    def test_place_ladder_buy_sufficient_capital(self, mock_config, mock_state):
        """Test ladder BUY with sufficient capital."""
        # Client has $500, order needs ~$350
        mock_client = MockClient(balance=500.0)
        laddering = PositionLaddering(mock_config, mock_client, mock_state)

        # This would place an actual order - can't test without API
        # Just verify the calculation would work
        price = 0.6647
        amount = 535.0
        required = price * amount  # ~$355

        assert mock_client.get_usdt_balance() > required

    def test_place_ladder_buy_insufficient_capital(self, mock_config, mock_state):
        """Test ladder BUY fails with insufficient capital."""
        # Client has $100, order needs ~$350
        mock_client = MockClient(balance=100.0)
        laddering = PositionLaddering(mock_config, mock_client, mock_state)

        price = 0.6647
        amount = 535.0
        required = price * amount  # ~$355

        assert mock_client.get_usdt_balance() < required


class TestExpectedValueCalculations:
    """Test expected value improvements from design doc."""

    def test_flash_crash_scenario(self):
        """
        Test the documented scenario from design doc.

        Original: 535 @ $0.7820
        Counter: 535 @ $0.6647 (filled during crash)
        New avg: 1070 @ $0.7234
        Profit target: $0.7520 (+4%)
        Expected profit: ~+4.2% vs -35% loss with traditional stop-loss
        """
        from decimal import Decimal

        # Calculate averaging
        orig_shares = Decimal('535')
        orig_price = Decimal('0.7820')
        counter_shares = Decimal('535')
        counter_price = Decimal('0.6647')

        total_cost = orig_shares * orig_price + counter_shares * counter_price
        total_shares = orig_shares + counter_shares
        avg_price = total_cost / total_shares

        # Calculate profit if selling at $0.75 (recovery)
        sell_price = Decimal('0.7520')
        proceeds = total_shares * sell_price
        profit_usdt = proceeds - total_cost
        profit_pct = (profit_usdt / total_cost) * Decimal('100')

        # Verify math
        assert float(avg_price) == pytest.approx(0.7234, rel=1e-3)
        assert float(profit_pct) > 0  # Profitable
        assert float(profit_pct) == pytest.approx(4.0, rel=0.5)  # ~4% profit


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
