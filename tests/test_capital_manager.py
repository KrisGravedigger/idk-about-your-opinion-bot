#!/usr/bin/env python3
"""
Test Capital Manager Module
============================

Comprehensive tests for CapitalManager with mock API client.

Run with: python test_capital_manager.py
"""

import sys
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock API client for testing
class MockClient:
    """Mock OpinionClient for testing without real API."""
    
    def __init__(self, balance: float):
        """
        Initialize mock client with fixed balance.
        
        Args:
            balance: USDT balance to return
        """
        self.balance = balance
    
    def get_usdt_balance(self) -> float:
        """Return the mocked balance."""
        return self.balance


# Import after path setup
from core.capital_manager import (
    CapitalManager, 
    InsufficientCapitalError, 
    PositionTooSmallError
)


def test_1_fixed_mode_sufficient():
    """
    Test 1: Fixed mode with sufficient balance.
    
    Scenario:
        - Balance: 12 USDT
        - Mode: fixed
        - Amount: 10 USDT
        
    Expected: Should return 10 USDT (fixed amount)
    """
    print("Test 1: Fixed mode with sufficient balance")
    
    config = {
        'CAPITAL_MODE': 'fixed',
        'CAPITAL_AMOUNT_USDT': 10.0,
        'CAPITAL_PERCENTAGE': 100.0,
        'MIN_BALANCE_TO_CONTINUE_USDT': 8.0,
        'MIN_POSITION_SIZE_USDT': 5.0,
        'MIN_POSITION_FOR_POINTS_USDT': 10.0,
        'WARN_IF_BELOW_POINTS_THRESHOLD': True
    }
    
    client = MockClient(balance=12.0)
    manager = CapitalManager(config, client)
    
    position_size = manager.get_position_size()
    
    assert position_size == 10.0, f"Expected 10.0, got {position_size}"
    print(f"   ✓ Position size: ${position_size:.2f}")
    print()


def test_2_percentage_mode_100():
    """
    Test 2: Percentage mode 100% with sufficient balance.
    
    Scenario:
        - Balance: 15 USDT
        - Mode: percentage
        - Percentage: 100%
        
    Expected: Should return 15 USDT (100% of balance)
    """
    print("Test 2: Percentage mode 100% of balance")
    
    config = {
        'CAPITAL_MODE': 'percentage',
        'CAPITAL_AMOUNT_USDT': 10.0,
        'CAPITAL_PERCENTAGE': 100.0,
        'MIN_BALANCE_TO_CONTINUE_USDT': 8.0,
        'MIN_POSITION_SIZE_USDT': 5.0,
        'MIN_POSITION_FOR_POINTS_USDT': 10.0,
        'WARN_IF_BELOW_POINTS_THRESHOLD': True
    }
    
    client = MockClient(balance=15.0)
    manager = CapitalManager(config, client)
    
    position_size = manager.get_position_size()
    
    assert position_size == 15.0, f"Expected 15.0, got {position_size}"
    print(f"   ✓ Position size: ${position_size:.2f}")
    print()


def test_3_percentage_mode_50():
    """
    Test 3: Percentage mode 50% of balance.
    
    Scenario:
        - Balance: 20 USDT
        - Mode: percentage
        - Percentage: 50%
        
    Expected: Should return 10 USDT (50% of 20)
    """
    print("Test 3: Percentage mode 50% of balance")
    
    config = {
        'CAPITAL_MODE': 'percentage',
        'CAPITAL_AMOUNT_USDT': 10.0,
        'CAPITAL_PERCENTAGE': 50.0,
        'MIN_BALANCE_TO_CONTINUE_USDT': 8.0,
        'MIN_POSITION_SIZE_USDT': 5.0,
        'MIN_POSITION_FOR_POINTS_USDT': 10.0,
        'WARN_IF_BELOW_POINTS_THRESHOLD': True
    }
    
    client = MockClient(balance=20.0)
    manager = CapitalManager(config, client)
    
    position_size = manager.get_position_size()
    
    assert position_size == 10.0, f"Expected 10.0, got {position_size}"
    print(f"   ✓ Position size: ${position_size:.2f}")
    print()


def test_4_insufficient_balance():
    """
    Test 4: Insufficient balance (should raise error).
    
    Scenario:
        - Balance: 7 USDT
        - Min required: 8 USDT
        
    Expected: Should raise InsufficientCapitalError
    """
    print("Test 4: Insufficient balance (should raise error)")
    
    config = {
        'CAPITAL_MODE': 'percentage',
        'CAPITAL_AMOUNT_USDT': 10.0,
        'CAPITAL_PERCENTAGE': 100.0,
        'MIN_BALANCE_TO_CONTINUE_USDT': 8.0,
        'MIN_POSITION_SIZE_USDT': 5.0,
        'MIN_POSITION_FOR_POINTS_USDT': 10.0,
        'WARN_IF_BELOW_POINTS_THRESHOLD': True
    }
    
    client = MockClient(balance=7.0)
    manager = CapitalManager(config, client)
    
    try:
        position_size = manager.get_position_size()
        assert False, "Should have raised InsufficientCapitalError"
    except InsufficientCapitalError as e:
        print(f"   ✓ Correctly raised InsufficientCapitalError: {e}")
        print()


def test_5_position_too_small():
    """
    Test 5: Position size below platform minimum (should raise error).
    
    Scenario:
        - Balance: 9 USDT
        - Mode: percentage 50% = 4.5 USDT
        - Min position: 5 USDT
        
    Expected: Should raise PositionTooSmallError (4.5 < 5.0)
    """
    print("Test 5: Position too small for platform minimum")
    
    config = {
        'CAPITAL_MODE': 'percentage',
        'CAPITAL_AMOUNT_USDT': 10.0,
        'CAPITAL_PERCENTAGE': 50.0,
        'MIN_BALANCE_TO_CONTINUE_USDT': 8.0,
        'MIN_POSITION_SIZE_USDT': 5.0,
        'MIN_POSITION_FOR_POINTS_USDT': 10.0,
        'WARN_IF_BELOW_POINTS_THRESHOLD': True
    }
    
    client = MockClient(balance=9.0)
    manager = CapitalManager(config, client)
    
    try:
        position_size = manager.get_position_size()
        assert False, "Should have raised PositionTooSmallError"
    except PositionTooSmallError as e:
        print(f"   ✓ Correctly raised PositionTooSmallError: {e}")
        print()


def test_6_warning_threshold():
    """
    Test 6: Position below airdrop points threshold (should log warning).

    Scenario:
        - Balance: 7 USDT
        - Mode: percentage 100% = 7 USDT
        - Min for points: 10 USDT

    Expected:
        - Should succeed (7 > 5 platform min)
        - Should log warning (7 < 10 points threshold)
    """
    print("Test 6: Position below airdrop points threshold (warning)")

    config = {
        'CAPITAL_MODE': 'percentage',
        'CAPITAL_AMOUNT_USDT': 10.0,
        'CAPITAL_PERCENTAGE': 100.0,
        'MIN_BALANCE_TO_CONTINUE_USDT': 5.0,  # Lower min to allow test
        'MIN_POSITION_SIZE_USDT': 5.0,
        'MIN_POSITION_FOR_POINTS_USDT': 10.0,
        'WARN_IF_BELOW_POINTS_THRESHOLD': True
    }

    client = MockClient(balance=7.0)
    manager = CapitalManager(config, client)

    position_size = manager.get_position_size()

    assert position_size == 7.0, f"Expected 7.0, got {position_size}"
    print(f"   ✓ Position size: ${position_size:.2f} (warning logged above)")
    print()


def test_7_laddering_percentage_mode():
    """
    Test 7: Laddering enabled with percentage mode.

    Scenario:
        - Balance: 174.83 USDT
        - Mode: percentage 90%
        - Laddering: enabled (2x multiplier)

    Expected:
        - Base calculation: 174.83 × 0.90 = 157.35
        - Adjusted for laddering: 157.35 / 2.0 = 78.67 (rounded to 78.68)
        - This reserves 45% for position + 45% for counter-buy
    """
    print("Test 7: Laddering enabled with percentage mode")

    # Import config to check and modify laddering flag
    import config
    original_laddering = config.ENABLE_POSITION_LADDERING

    try:
        # Enable laddering for this test
        config.ENABLE_POSITION_LADDERING = True

        test_config = {
            'CAPITAL_MODE': 'percentage',
            'CAPITAL_AMOUNT_USDT': 20.0,
            'CAPITAL_PERCENTAGE': 90.0,
            'MIN_BALANCE_TO_CONTINUE_USDT': 50.0,
            'MIN_POSITION_SIZE_USDT': 50.0,
            'MIN_POSITION_FOR_POINTS_USDT': 10.0,
            'WARN_IF_BELOW_POINTS_THRESHOLD': False
        }

        client = MockClient(balance=174.83)
        manager = CapitalManager(test_config, client)

        position_size = manager.get_position_size()

        # Expected: 174.83 × 0.90 / 2.0 = 78.6735 ≈ 78.67
        expected = 174.83 * 0.90 / 2.0

        # Allow small floating point difference
        assert abs(position_size - expected) < 0.01, f"Expected {expected:.2f}, got {position_size:.2f}"
        print(f"   ✓ Position size: ${position_size:.2f} (45% of balance)")
        print(f"   ✓ Counter-buy reserve: ${position_size:.2f} (45% of balance)")
        print()

    finally:
        # Restore original config
        config.ENABLE_POSITION_LADDERING = original_laddering


def test_8_laddering_fixed_mode():
    """
    Test 8: Laddering enabled with fixed mode.

    Scenario:
        - Balance: 200 USDT
        - Mode: fixed 100 USDT
        - Laddering: enabled (2x multiplier)

    Expected:
        - Base: 100 USDT (fixed)
        - Adjusted for laddering: 100 / 2.0 = 50 USDT
        - This reserves 50 USDT for position + 50 USDT for counter-buy
    """
    print("Test 8: Laddering enabled with fixed mode")

    # Import config to check and modify laddering flag
    import config
    original_laddering = config.ENABLE_POSITION_LADDERING

    try:
        # Enable laddering for this test
        config.ENABLE_POSITION_LADDERING = True

        test_config = {
            'CAPITAL_MODE': 'fixed',
            'CAPITAL_AMOUNT_USDT': 100.0,
            'CAPITAL_PERCENTAGE': 90.0,
            'MIN_BALANCE_TO_CONTINUE_USDT': 50.0,
            'MIN_POSITION_SIZE_USDT': 40.0,
            'MIN_POSITION_FOR_POINTS_USDT': 10.0,
            'WARN_IF_BELOW_POINTS_THRESHOLD': False
        }

        client = MockClient(balance=200.0)
        manager = CapitalManager(test_config, client)

        position_size = manager.get_position_size()

        # Expected: 100 / 2.0 = 50.0
        expected = 50.0

        assert position_size == expected, f"Expected {expected:.2f}, got {position_size:.2f}"
        print(f"   ✓ Position size: ${position_size:.2f}")
        print(f"   ✓ Counter-buy reserve: ${position_size:.2f}")
        print()

    finally:
        # Restore original config
        config.ENABLE_POSITION_LADDERING = original_laddering


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("CAPITAL MANAGER TESTS")
    print("=" * 60)
    print()
    
    try:
        test_1_fixed_mode_sufficient()
        test_2_percentage_mode_100()
        test_3_percentage_mode_50()
        test_4_insufficient_balance()
        test_5_position_too_small()
        test_6_warning_threshold()
        test_7_laddering_percentage_mode()
        test_8_laddering_fixed_mode()

        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        sys.exit(1)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ UNEXPECTED ERROR: {e}")
        print("=" * 60)
        sys.exit(1)