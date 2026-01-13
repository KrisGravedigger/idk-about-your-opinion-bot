#!/usr/bin/env python3
"""
Test Liquidity Checker Module
==============================

Comprehensive tests for LiquidityChecker with mock orderbook data.

Run with: python test_liquidity_checker.py
"""

import sys
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))


# Mock API client for testing
class MockClient:
    """Mock OpinionClient for testing without real API."""
    
    def __init__(self, orderbook: dict):
        """
        Initialize mock client with fixed orderbook.
        
        Args:
            orderbook: Orderbook dict with 'bids' and 'asks'
        """
        self.orderbook = orderbook
    
    def get_market_orderbook(self, token_id: int) -> dict:
        """Return the mocked orderbook."""
        return self.orderbook


# Import after path setup
from monitoring.liquidity_checker import LiquidityChecker


def test_1_good_liquidity():
    """
    Test 1: Good liquidity (no deterioration).
    
    Scenario:
        - Initial bid: 0.066
        - Current bid: 0.065 (only 1.5% drop, within threshold)
        - Current spread: 10% (within threshold)
        
    Expected: Should return ok=True
    """
    print("Test 1: Good liquidity (no deterioration)")
    
    config = {
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0
    }
    
    # Mock orderbook with good liquidity
    orderbook = {
        'bids': [
            {'price': 0.065, 'size': 100},
            {'price': 0.064, 'size': 150}
        ],
        'asks': [
            {'price': 0.072, 'size': 100},
            {'price': 0.073, 'size': 150}
        ]
    }
    
    client = MockClient(orderbook)
    checker = LiquidityChecker(config, client)
    
    result = checker.check_liquidity(
        market_id=813,
        token_id=1626,
        initial_best_bid=0.066
    )
    
    assert result['ok'] == True, "Liquidity should be OK"
    assert result['current_best_bid'] == 0.065, "Should have correct current bid"
    assert result['current_best_ask'] == 0.072, "Should have correct current ask"
    assert result['deterioration_reason'] is None, "Should have no deterioration reason"
    
    print(f"   ✓ Liquidity OK")
    print(f"   ✓ Current bid: ${result['current_best_bid']:.4f}")
    print(f"   ✓ Current spread: {result['current_spread_pct']:.2f}%")
    print(f"   ✓ Bid drop: {result['bid_drop_pct']:.2f}%")
    print()


def test_2_bid_drop_deterioration():
    """
    Test 2: Bid dropped significantly (deterioration).
    
    Scenario:
        - Initial bid: 0.100
        - Current bid: 0.070 (30% drop, exceeds 25% threshold)
        
    Expected: Should return ok=False with deterioration_reason
    """
    print("Test 2: Bid drop deterioration")
    
    config = {
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0
    }
    
    # Mock orderbook with bid collapse
    orderbook = {
        'bids': [
            {'price': 0.070, 'size': 50},  # 30% drop from 0.100
            {'price': 0.069, 'size': 75}
        ],
        'asks': [
            {'price': 0.080, 'size': 100},
            {'price': 0.081, 'size': 150}
        ]
    }
    
    client = MockClient(orderbook)
    checker = LiquidityChecker(config, client)
    
    result = checker.check_liquidity(
        market_id=813,
        token_id=1626,
        initial_best_bid=0.100
    )
    
    assert result['ok'] == False, "Liquidity should be deteriorated"
    assert result['current_best_bid'] == 0.070, "Should have correct current bid"
    assert result['bid_drop_pct'] < -25.0, "Bid drop should exceed threshold"
    assert result['deterioration_reason'] is not None, "Should have deterioration reason"
    assert 'Bid dropped' in result['deterioration_reason'], "Reason should mention bid drop"
    
    print(f"   ✓ Deterioration detected")
    print(f"   ✓ Bid drop: {result['bid_drop_pct']:.2f}% (threshold: -25%)")
    print(f"   ✓ Reason: {result['deterioration_reason']}")
    print()


def test_3_spread_deterioration():
    """
    Test 3: Spread widened significantly (deterioration).
    
    Scenario:
        - Initial bid: 0.050
        - Current bid: 0.050 (no drop)
        - Current spread: 20% (exceeds 15% threshold)
        
    Expected: Should return ok=False with deterioration_reason
    """
    print("Test 3: Spread widening deterioration")
    
    config = {
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0
    }
    
    # Mock orderbook with wide spread
    orderbook = {
        'bids': [
            {'price': 0.050, 'size': 100},
            {'price': 0.049, 'size': 150}
        ],
        'asks': [
            {'price': 0.060, 'size': 100},  # 20% spread from 0.050
            {'price': 0.061, 'size': 150}
        ]
    }
    
    client = MockClient(orderbook)
    checker = LiquidityChecker(config, client)
    
    result = checker.check_liquidity(
        market_id=813,
        token_id=1626,
        initial_best_bid=0.050
    )
    
    assert result['ok'] == False, "Liquidity should be deteriorated"
    assert result['current_spread_pct'] > 15.0, "Spread should exceed threshold"
    assert result['deterioration_reason'] is not None, "Should have deterioration reason"
    assert 'Spread' in result['deterioration_reason'], "Reason should mention spread"
    
    print(f"   ✓ Deterioration detected")
    print(f"   ✓ Spread: {result['current_spread_pct']:.2f}% (threshold: 15%)")
    print(f"   ✓ Reason: {result['deterioration_reason']}")
    print()


def test_4_unsorted_orderbook():
    """
    Test 4: Unsorted orderbook (Opinion.trade doesn't guarantee sorted).
    
    Scenario:
        - Orderbook bids are not sorted
        - Orderbook asks are not sorted
        
    Expected: Should correctly find best bid (max) and best ask (min)
    """
    print("Test 4: Unsorted orderbook handling")
    
    config = {
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0
    }
    
    # Mock UNSORTED orderbook
    orderbook = {
        'bids': [
            {'price': 0.040, 'size': 100},  # Not best
            {'price': 0.055, 'size': 150},  # BEST BID (highest)
            {'price': 0.050, 'size': 200}   # Middle
        ],
        'asks': [
            {'price': 0.070, 'size': 100},  # Middle
            {'price': 0.075, 'size': 150},  # Not best
            {'price': 0.065, 'size': 200}   # BEST ASK (lowest)
        ]
    }
    
    client = MockClient(orderbook)
    checker = LiquidityChecker(config, client)
    
    result = checker.check_liquidity(
        market_id=813,
        token_id=1626,
        initial_best_bid=0.055
    )
    
    assert result['current_best_bid'] == 0.055, "Should find highest bid (max)"
    assert result['current_best_ask'] == 0.065, "Should find lowest ask (min)"
    
    print(f"   ✓ Correctly found best bid: ${result['current_best_bid']:.4f}")
    print(f"   ✓ Correctly found best ask: ${result['current_best_ask']:.4f}")
    print()


def test_5_empty_orderbook():
    """
    Test 5: Empty orderbook (edge case).
    
    Scenario:
        - Orderbook has no bids or asks
        
    Expected: Should return ok=True (neutral, don't cancel on fetch failure)
    """
    print("Test 5: Empty orderbook (edge case)")
    
    config = {
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0
    }
    
    # Mock empty orderbook
    orderbook = {
        'bids': [],
        'asks': []
    }
    
    client = MockClient(orderbook)
    checker = LiquidityChecker(config, client)
    
    result = checker.check_liquidity(
        market_id=813,
        token_id=1626,
        initial_best_bid=0.066
    )
    
    assert result['ok'] == True, "Should return neutral (ok=True) for empty orderbook"
    assert result['deterioration_reason'] is None, "Should have no deterioration reason"
    
    print(f"   ✓ Empty orderbook handled gracefully")
    print(f"   ✓ Result: ok={result['ok']}")
    print()


def test_6_edge_case_zero_initial_bid():
    """
    Test 6: Edge case - zero initial bid (should not crash).
    
    Scenario:
        - Initial bid: 0 (edge case)
        - Current bid: 0.055
        - Current ask: 0.062 (spread ~12.7%, within threshold)
        
    Expected: Should calculate bid_drop_pct as 0% (not divide by zero)
    """
    print("Test 6: Edge case - zero initial bid")
    
    config = {
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0
    }
    
    orderbook = {
        'bids': [{'price': 0.055, 'size': 100}],
        'asks': [{'price': 0.062, 'size': 100}]  # Changed from 0.065 to 0.062
    }
    
    client = MockClient(orderbook)
    checker = LiquidityChecker(config, client)
    
    result = checker.check_liquidity(
        market_id=813,
        token_id=1626,
        initial_best_bid=0.0  # Edge case
    )
    
    assert result['bid_drop_pct'] == 0.0, "Should handle zero initial bid gracefully"
    assert result['ok'] == True, "Should not detect deterioration"
    
    print(f"   ✓ Zero initial bid handled (no crash)")
    print(f"   ✓ Bid drop: {result['bid_drop_pct']:.2f}%")
    print()


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("LIQUIDITY CHECKER TESTS")
    print("=" * 60)
    print()
    
    try:
        test_1_good_liquidity()
        test_2_bid_drop_deterioration()
        test_3_spread_deterioration()
        test_4_unsorted_orderbook()
        test_5_empty_orderbook()
        test_6_edge_case_zero_initial_bid()
        
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
        import traceback
        traceback.print_exc()
        sys.exit(1)