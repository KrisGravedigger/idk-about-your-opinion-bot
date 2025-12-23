#!/usr/bin/env python3
"""
SCORING SYSTEM TEST SUITE
==========================

Test all metrics to ensure they work correctly before integration.

USAGE:
    python test_scoring.py
"""

from scoring import (
    score_price_balance,
    score_hourglass_advanced,
    score_hourglass_simple,
    score_spread_large,
    score_spread_small,
    score_volume_24h,
    score_liquidity_depth,
    calculate_market_score,
)


def test_price_balance():
    """Test price balance scoring"""
    print("=" * 60)
    print("TEST 1: Price Balance")
    print("=" * 60)
    
    tests = [
        (0.49, 0.51, "Perfect 50/50"),
        (0.48, 0.52, "Close to 50/50"),
        (0.30, 0.32, "Biased to NO (30%)"),
        (0.70, 0.72, "Biased to YES (70%)"),
        (0.10, 0.12, "Extreme bias"),
    ]
    
    for best_bid, best_ask, description in tests:
        score = score_price_balance(best_bid, best_ask)
        mid = (best_bid + best_ask) / 2
        print(f"  {description:20s} (mid={mid:.2f}): {score:.3f}")
    
    print()


def test_spread_scoring():
    """Test spread scoring (both directions)"""
    print("=" * 60)
    print("TEST 2: Spread Scoring")
    print("=" * 60)
    
    spreads = [0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 20.0]
    
    print("  Spread%  | Large (farm) | Small (test)")
    print("  " + "-" * 40)
    for spread_pct in spreads:
        large = score_spread_large(spread_pct)
        small = score_spread_small(spread_pct)
        print(f"  {spread_pct:5.1f}%   |    {large:.3f}      |    {small:.3f}")
    
    print()


def test_volume_scoring():
    """Test volume scoring"""
    print("=" * 60)
    print("TEST 3: Volume Scoring")
    print("=" * 60)
    
    volumes = [10, 100, 1000, 10000, 50000, 100000]
    
    print("  Volume    | Linear | Logarithmic")
    print("  " + "-" * 35)
    for volume in volumes:
        linear = score_volume_24h(volume, log_scale=False)
        log = score_volume_24h(volume, log_scale=True)
        print(f"  ${volume:7,d} | {linear:.3f}  |   {log:.3f}")
    
    print()


def test_hourglass_simple():
    """Test simple hourglass scoring"""
    print("=" * 60)
    print("TEST 4: Hourglass (Simple)")
    print("=" * 60)
    
    # Mock orderbook 1: Good hourglass (more volume far away)
    good_orderbook = {
        'bids': [
            {'price': '0.48', 'size': '1000'},   # Near (top 3)
            {'price': '0.47', 'size': '1200'},
            {'price': '0.46', 'size': '1100'},
            {'price': '0.45', 'size': '5000'},   # Far (4-10)
            {'price': '0.44', 'size': '6000'},
            {'price': '0.43', 'size': '7000'},
        ],
        'asks': [
            {'price': '0.52', 'size': '1000'},   # Near
            {'price': '0.53', 'size': '1200'},
            {'price': '0.54', 'size': '1100'},
            {'price': '0.55', 'size': '5000'},   # Far
            {'price': '0.56', 'size': '6000'},
            {'price': '0.57', 'size': '7000'},
        ]
    }
    
    # Mock orderbook 2: Bad hourglass (more volume near)
    bad_orderbook = {
        'bids': [
            {'price': '0.48', 'size': '5000'},   # Near (lots)
            {'price': '0.47', 'size': '6000'},
            {'price': '0.46', 'size': '7000'},
            {'price': '0.45', 'size': '1000'},   # Far (little)
            {'price': '0.44', 'size': '1200'},
            {'price': '0.43', 'size': '1100'},
        ],
        'asks': [
            {'price': '0.52', 'size': '5000'},
            {'price': '0.53', 'size': '6000'},
            {'price': '0.54', 'size': '7000'},
            {'price': '0.55', 'size': '1000'},
            {'price': '0.56', 'size': '1200'},
            {'price': '0.57', 'size': '1100'},
        ]
    }
    
    good_score = score_hourglass_simple(good_orderbook)
    bad_score = score_hourglass_simple(bad_orderbook)
    
    print(f"  Good hourglass (far > near): {good_score:.3f}")
    print(f"  Bad hourglass (near > far):  {bad_score:.3f}")
    print()


def test_hourglass_advanced():
    """Test advanced hourglass scoring"""
    print("=" * 60)
    print("TEST 5: Hourglass (Advanced)")
    print("=" * 60)
    
    # Same orderbooks as simple test
    good_orderbook = {
        'bids': [
            {'price': '0.48', 'size': '1000'},
            {'price': '0.47', 'size': '1200'},
            {'price': '0.46', 'size': '1100'},
            {'price': '0.45', 'size': '5000'},
            {'price': '0.44', 'size': '6000'},
            {'price': '0.43', 'size': '7000'},
        ],
        'asks': [
            {'price': '0.52', 'size': '1000'},
            {'price': '0.53', 'size': '1200'},
            {'price': '0.54', 'size': '1100'},
            {'price': '0.55', 'size': '5000'},
            {'price': '0.56', 'size': '6000'},
            {'price': '0.57', 'size': '7000'},
        ]
    }
    
    bad_orderbook = {
        'bids': [
            {'price': '0.48', 'size': '5000'},
            {'price': '0.47', 'size': '6000'},
            {'price': '0.46', 'size': '7000'},
            {'price': '0.45', 'size': '1000'},
            {'price': '0.44', 'size': '1200'},
            {'price': '0.43', 'size': '1100'},
        ],
        'asks': [
            {'price': '0.52', 'size': '5000'},
            {'price': '0.53', 'size': '6000'},
            {'price': '0.54', 'size': '7000'},
            {'price': '0.55', 'size': '1000'},
            {'price': '0.56', 'size': '1200'},
            {'price': '0.57', 'size': '1100'},
        ]
    }
    
    good_score = score_hourglass_advanced(good_orderbook, 0.48, 0.52)
    bad_score = score_hourglass_advanced(bad_orderbook, 0.48, 0.52)
    
    print(f"  Good hourglass (zone-based): {good_score:.3f}")
    print(f"  Bad hourglass (zone-based):  {bad_score:.3f}")
    print()


def test_composite_scoring():
    """Test composite scoring with different profiles"""
    print("=" * 60)
    print("TEST 6: Composite Scoring")
    print("=" * 60)
    
    # Mock market object
    class MockMarket:
        def __init__(self):
            self.best_bid = 0.48
            self.best_ask = 0.52
            self.spread_pct = 8.0
            self.volume_24h = 10000
            self.is_bonus = False
    
    # Mock orderbook
    orderbook = {
        'bids': [
            {'price': '0.48', 'size': '1000'},
            {'price': '0.47', 'size': '1200'},
            {'price': '0.46', 'size': '5000'},
        ],
        'asks': [
            {'price': '0.52', 'size': '1000'},
            {'price': '0.53', 'size': '1200'},
            {'price': '0.54', 'size': '5000'},
        ]
    }
    
    market = MockMarket()
    
    # Test different weight combinations
    profiles = [
        {
            'name': 'Production Farming',
            'weights': {
                'price_balance': 0.45,
                'hourglass_simple': 0.25,
                'spread': 0.20,
                'volume_24h': 0.10,
            },
            'bonus_multiplier': 1.5,
        },
        {
            'name': 'Test Quick Fill',
            'weights': {
                'spread': 1.0,
            },
            'bonus_multiplier': 1.0,
            'invert_spread': True,
        },
        {
            'name': 'Balanced',
            'weights': {
                'price_balance': 0.25,
                'spread': 0.25,
                'volume_24h': 0.25,
                'hourglass_simple': 0.25,
            },
            'bonus_multiplier': 1.2,
        },
    ]
    
    for profile in profiles:
        score = calculate_market_score(
            market=market,
            orderbook=orderbook,
            weights=profile['weights'],
            bonus_multiplier=profile.get('bonus_multiplier', 1.0),
            invert_spread=profile.get('invert_spread', False)
        )
        print(f"  {profile['name']:20s}: {score:.3f}")
    
    print()


def test_edge_cases():
    """Test edge cases and error handling"""
    print("=" * 60)
    print("TEST 7: Edge Cases")
    print("=" * 60)
    
    # Empty orderbook
    try:
        score = score_hourglass_simple({})
        print(f"  Empty orderbook: {score:.3f} (should be 0.0)")
    except Exception as e:
        print(f"  Empty orderbook: ERROR - {e}")
    
    # Invalid data
    try:
        bad_orderbook = {
            'bids': [{'price': 'invalid', 'size': 'bad'}],
            'asks': [{'price': '0.50', 'size': '1000'}]
        }
        score = score_hourglass_simple(bad_orderbook)
        print(f"  Invalid data: {score:.3f} (should handle gracefully)")
    except Exception as e:
        print(f"  Invalid data: ERROR - {e}")
    
    # Extreme values
    score = score_price_balance(0.01, 0.03)
    print(f"  Extreme price (1%): {score:.3f}")
    
    score = score_price_balance(0.97, 0.99)
    print(f"  Extreme price (98%): {score:.3f}")
    
    print()


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("SCORING SYSTEM TEST SUITE")
    print("=" * 60)
    print()
    
    test_price_balance()
    test_spread_scoring()
    test_volume_scoring()
    test_hourglass_simple()
    test_hourglass_advanced()
    test_composite_scoring()
    test_edge_cases()
    
    print("=" * 60)
    print("✅ ALL TESTS COMPLETED")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Review test results")
    print("2. Integrate scoring.py into project")
    print("3. Update config.py with profiles")
    print("4. Modify market_scanner.py")
    print("5. Update scripts (stage2, place_test_order)")
    print()


if __name__ == "__main__":
    main()
