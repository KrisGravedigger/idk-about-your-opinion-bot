#!/usr/bin/env python3
"""
Test Pricing Strategy Module
=============================

Comprehensive tests for PricingStrategy with various spread scenarios.

Run with: python test_pricing.py
"""

import sys
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import after path setup
from strategies.pricing import PricingStrategy


def test_1_buy_price_normal_spread():
    """
    Test 1: BUY price calculation with normal spread.
    
    Scenario:
        - Best bid: $0.066
        - Best ask: $0.080
        - Spread: 21.21%
        - Multiplier: 1.10
        
    Expected: price = 0.066 × 1.10 = 0.0726 (within spread)
    """
    print("Test 1: BUY price with normal spread")
    
    config = {
        'BUY_MULTIPLIER': 1.10,
        'SELL_MULTIPLIER': 0.90,
        'SAFETY_MARGIN_CENTS': 0.001
    }
    
    strategy = PricingStrategy(config)
    
    best_bid = 0.066
    best_ask = 0.080  # Wider spread so 1.10x multiplier doesn't trigger safety
    
    price = strategy.calculate_buy_price(best_bid, best_ask)
    
    expected = 0.073  # 0.066 × 1.10 = 0.0726 → rounded to 0.073
    assert price == expected, f"Expected {expected}, got {price}"
    assert price < best_ask, "Price should not cross ask"
    
    print(f"   ✓ Best bid: ${best_bid:.4f}")
    print(f"   ✓ Best ask: ${best_ask:.4f}")
    print(f"   ✓ Spread: {((best_ask - best_bid) / best_bid * 100):.1f}%")
    print(f"   ✓ Calculated: ${price:.4f}")
    print(f"   ✓ Within spread: True")
    print()


def test_2_buy_price_tight_spread():
    """
    Test 2: BUY price with tight spread (safety check triggers).
    
    Scenario:
        - Best bid: $0.070
        - Best ask: $0.071 (tight 1.4% spread)
        - Multiplier: 1.10 would give 0.077 (crosses ask!)
        
    Expected: Safety check adjusts to 0.070 (ask - margin)
    """
    print("Test 2: BUY price with tight spread (safety check)")
    
    config = {
        'BUY_MULTIPLIER': 1.10,
        'SELL_MULTIPLIER': 0.90,
        'SAFETY_MARGIN_CENTS': 0.001
    }
    
    strategy = PricingStrategy(config)
    
    best_bid = 0.070
    best_ask = 0.071  # Very tight spread
    
    price = strategy.calculate_buy_price(best_bid, best_ask)
    
    # Should be adjusted to ask - margin
    expected = 0.070  # 0.071 - 0.001 = 0.070 (rounded)
    assert price == expected, f"Expected {expected}, got {price}"
    assert price < best_ask, "Price must not cross ask"
    
    print(f"   ✓ Best bid: ${best_bid:.4f}")
    print(f"   ✓ Best ask: ${best_ask:.4f}")
    print(f"   ✓ Calculated: ${price:.4f}")
    print(f"   ✓ Safety adjusted: True")
    print()


def test_3_sell_price_normal_spread():
    """
    Test 3: SELL price calculation with normal spread.
    
    Scenario:
        - Best bid: $0.066
        - Best ask: $0.090
        - Spread: 36.36%
        - Multiplier: 0.90
        
    Expected: price = 0.090 × 0.90 = 0.081 (within spread)
    """
    print("Test 3: SELL price with normal spread")
    
    config = {
        'BUY_MULTIPLIER': 1.10,
        'SELL_MULTIPLIER': 0.90,
        'SAFETY_MARGIN_CENTS': 0.001
    }
    
    strategy = PricingStrategy(config)
    
    best_bid = 0.066
    best_ask = 0.090
    
    price = strategy.calculate_sell_price(best_bid, best_ask)
    
    expected = 0.081  # 0.090 × 0.90 = 0.081
    assert price == expected, f"Expected {expected}, got {price}"
    assert price > best_bid, "Price should not cross bid"
    
    print(f"   ✓ Best bid: ${best_bid:.4f}")
    print(f"   ✓ Best ask: ${best_ask:.4f}")
    print(f"   ✓ Calculated: ${price:.4f}")
    print(f"   ✓ Within spread: True")
    print()


def test_4_sell_price_tight_spread():
    """
    Test 4: SELL price with tight spread (safety check triggers).
    
    Scenario:
        - Best bid: $0.070
        - Best ask: $0.071 (tight 1.4% spread)
        - Multiplier: 0.90 would give 0.064 (crosses bid!)
        
    Expected: Safety check adjusts to 0.071 (bid + margin)
    """
    print("Test 4: SELL price with tight spread (safety check)")
    
    config = {
        'BUY_MULTIPLIER': 1.10,
        'SELL_MULTIPLIER': 0.90,
        'SAFETY_MARGIN_CENTS': 0.001
    }
    
    strategy = PricingStrategy(config)
    
    best_bid = 0.070
    best_ask = 0.071  # Very tight spread
    
    price = strategy.calculate_sell_price(best_bid, best_ask)
    
    # Should be adjusted to bid + margin
    expected = 0.071  # 0.070 + 0.001 = 0.071
    assert price == expected, f"Expected {expected}, got {price}"
    assert price > best_bid, "Price must not cross bid"
    
    print(f"   ✓ Best bid: ${best_bid:.4f}")
    print(f"   ✓ Best ask: ${best_ask:.4f}")
    print(f"   ✓ Calculated: ${price:.4f}")
    print(f"   ✓ Safety adjusted: True")
    print()


def test_5_crossed_book_error():
    """
    Test 5: Error handling for crossed orderbook.
    
    Scenario:
        - Best bid: $0.072 (higher than ask - invalid!)
        - Best ask: $0.070
        
    Expected: Should raise ValueError
    """
    print("Test 5: Crossed orderbook error handling")
    
    config = {
        'BUY_MULTIPLIER': 1.10,
        'SELL_MULTIPLIER': 0.90,
        'SAFETY_MARGIN_CENTS': 0.001
    }
    
    strategy = PricingStrategy(config)
    
    best_bid = 0.072  # Higher than ask (invalid!)
    best_ask = 0.070
    
    try:
        price = strategy.calculate_buy_price(best_bid, best_ask)
        assert False, "Should have raised ValueError for crossed book"
    except ValueError as e:
        assert "Crossed orderbook" in str(e), "Error message should mention crossed book"
        print(f"   ✓ Correctly raised ValueError: {e}")
    
    try:
        price = strategy.calculate_sell_price(best_bid, best_ask)
        assert False, "Should have raised ValueError for crossed book"
    except ValueError as e:
        assert "Crossed orderbook" in str(e), "Error message should mention crossed book"
        print(f"   ✓ Correctly raised ValueError for SELL too")
    
    print()


def test_6_invalid_config():
    """
    Test 6: Validation of config parameters.
    
    Scenarios:
        - BUY_MULTIPLIER <= 1.0 (invalid)
        - SELL_MULTIPLIER >= 1.0 (invalid)
        - SAFETY_MARGIN <= 0 (invalid)
        
    Expected: Should raise ValueError on initialization
    """
    print("Test 6: Config validation")
    
    # Test 6a: Invalid BUY_MULTIPLIER
    try:
        config = {
            'BUY_MULTIPLIER': 0.95,  # Invalid (< 1.0)
            'SELL_MULTIPLIER': 0.90,
            'SAFETY_MARGIN_CENTS': 0.001
        }
        strategy = PricingStrategy(config)
        assert False, "Should have raised ValueError for BUY_MULTIPLIER"
    except ValueError as e:
        assert "BUY_MULTIPLIER must be > 1.0" in str(e)
        print(f"   ✓ Rejected invalid BUY_MULTIPLIER: {e}")
    
    # Test 6b: Invalid SELL_MULTIPLIER
    try:
        config = {
            'BUY_MULTIPLIER': 1.10,
            'SELL_MULTIPLIER': 1.05,  # Invalid (> 1.0)
            'SAFETY_MARGIN_CENTS': 0.001
        }
        strategy = PricingStrategy(config)
        assert False, "Should have raised ValueError for SELL_MULTIPLIER"
    except ValueError as e:
        assert "SELL_MULTIPLIER must be < 1.0" in str(e)
        print(f"   ✓ Rejected invalid SELL_MULTIPLIER: {e}")
    
    # Test 6c: Invalid SAFETY_MARGIN
    try:
        config = {
            'BUY_MULTIPLIER': 1.10,
            'SELL_MULTIPLIER': 0.90,
            'SAFETY_MARGIN_CENTS': 0  # Invalid (<= 0)
        }
        strategy = PricingStrategy(config)
        assert False, "Should have raised ValueError for SAFETY_MARGIN"
    except ValueError as e:
        assert "SAFETY_MARGIN_CENTS must be > 0" in str(e)
        print(f"   ✓ Rejected invalid SAFETY_MARGIN: {e}")
    
    print()


def test_7_edge_case_minimum_spread():
    """
    Test 7: Edge case - minimum possible spread.
    
    Scenario:
        - Best bid: $0.100
        - Best ask: $0.101 (1¢ or 1% spread)
        - Safety margin: $0.001
        
    Expected: Both BUY and SELL should work with tight adjustments
    """
    print("Test 7: Minimum spread edge case")
    
    config = {
        'BUY_MULTIPLIER': 1.10,
        'SELL_MULTIPLIER': 0.90,
        'SAFETY_MARGIN_CENTS': 0.001
    }
    
    strategy = PricingStrategy(config)
    
    best_bid = 0.100
    best_ask = 0.101  # 1% spread
    
    buy_price = strategy.calculate_buy_price(best_bid, best_ask)
    sell_price = strategy.calculate_sell_price(best_bid, best_ask)
    
    # Both should be adjusted to stay within tiny spread
    assert buy_price < best_ask, "BUY must not cross ask"
    assert sell_price > best_bid, "SELL must not cross bid"
    assert buy_price <= sell_price, "BUY must be <= SELL (no crossed orders)"
    
    print(f"   ✓ Best bid: ${best_bid:.4f}")
    print(f"   ✓ Best ask: ${best_ask:.4f}")
    print(f"   ✓ BUY price: ${buy_price:.4f}")
    print(f"   ✓ SELL price: ${sell_price:.4f}")
    print(f"   ✓ No crossed orders: True")
    print()


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("PRICING STRATEGY TESTS")
    print("=" * 60)
    print()
    
    try:
        test_1_buy_price_normal_spread()
        test_2_buy_price_tight_spread()
        test_3_sell_price_normal_spread()
        test_4_sell_price_tight_spread()
        test_5_crossed_book_error()
        test_6_invalid_config()
        test_7_edge_case_minimum_spread()
        
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