#!/usr/bin/env python3
"""
Test BUY Monitor Module
=======================

Comprehensive tests for BuyMonitor with mock client.

Run with: python test_buy_monitor.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))


# Mock API client for testing
class MockClient:
    """Mock OpinionClient for testing without real API."""
    
    def __init__(self, order_responses: list, orderbook: dict = None):
        """
        Initialize mock client with pre-defined order status responses.
        
        Args:
            order_responses: List of order dicts to return sequentially
            orderbook: Optional orderbook dict for liquidity checks
        """
        self.order_responses = order_responses
        self.response_index = 0
        self.orderbook = orderbook or {
            'bids': [{'price': 0.066, 'size': 100}],
            'asks': [{'price': 0.072, 'size': 100}]
        }
    
    def get_order(self, order_id: str) -> dict:
        """Return next order response from sequence."""
        if self.response_index < len(self.order_responses):
            response = self.order_responses[self.response_index]
            self.response_index += 1
            return response
        # Return last response if ran out
        return self.order_responses[-1]
    
    def get_market_orderbook(self, token_id: int) -> dict:
        """Return the mocked orderbook."""
        return self.orderbook


# Import after path setup
from monitoring.buy_monitor import BuyMonitor


def test_1_order_fills_immediately():
    """
    Test 1: Order fills on first check.
    
    Scenario:
        - Order is already filled when monitoring starts
        
    Expected: Should return filled status with fill data
    """
    print("Test 1: Order fills immediately")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 1,  # Fast for testing
        'BUY_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'current_price': 0.066
    }
    
    # Order is filled immediately
    order_responses = [
        {
            'status': 2,  # Finished
            'status_enum': 'Finished',
            'filled_shares': 150.0,
            'price': 0.066,
            'filled_amount': 9.90
        }
    ]
    
    client = MockClient(order_responses)
    monitor = BuyMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_123', timeout_at)
    
    assert result['status'] == 'filled', f"Expected 'filled', got '{result['status']}'"
    assert result['filled_amount'] == 150.0, "Should have filled_amount"
    assert result['avg_fill_price'] == 0.066, "Should have avg_fill_price"
    assert result['filled_usdt'] == 9.90, "Should have filled_usdt"
    assert result['fill_timestamp'] is not None, "Should have timestamp"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Filled: {result['filled_amount']} tokens")
    print(f"   ✓ Price: ${result['avg_fill_price']:.4f}")
    print(f"   ✓ Cost: ${result['filled_usdt']:.2f}")
    print()


def test_2_order_fills_after_pending():
    """
    Test 2: Order fills after being pending for a while.
    
    Scenario:
        - Check 1: Pending
        - Check 2: Pending
        - Check 3: Filled
        
    Expected: Should return filled status after 3 checks
    """
    print("Test 2: Order fills after being pending")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 0.1,  # Very fast for testing
        'BUY_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'current_price': 0.066
    }
    
    # Order pending, then pending, then filled
    order_responses = [
        {'status': 0, 'status_enum': 'Pending'},
        {'status': 0, 'status_enum': 'Pending'},
        {
            'status': 2,
            'status_enum': 'Finished',
            'filled_shares': 100.0,
            'price': 0.065,
            'filled_amount': 6.50
        }
    ]
    
    client = MockClient(order_responses)
    monitor = BuyMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_123', timeout_at)
    
    assert result['status'] == 'filled', "Should eventually fill"
    assert result['filled_amount'] == 100.0, "Should have correct amount"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Filled after pending checks")
    print()


def test_3_order_cancelled():
    """
    Test 3: Order gets cancelled.
    
    Scenario:
        - Order status returns Cancelled
        
    Expected: Should return cancelled status
    """
    print("Test 3: Order cancelled")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 1,
        'BUY_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'current_price': 0.066
    }
    
    order_responses = [
        {'status': 3, 'status_enum': 'Cancelled'}
    ]
    
    client = MockClient(order_responses)
    monitor = BuyMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_123', timeout_at)
    
    assert result['status'] == 'cancelled', f"Expected 'cancelled', got '{result['status']}'"
    assert result['filled_amount'] is None, "Should have no fill data"
    assert result['reason'] == 'Order cancelled', "Should have reason"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Reason: {result['reason']}")
    print()


def test_4_order_expired():
    """
    Test 4: Order expires.
    
    Scenario:
        - Order status returns Expired
        
    Expected: Should return expired status
    """
    print("Test 4: Order expired")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 1,
        'BUY_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'current_price': 0.066
    }
    
    order_responses = [
        {'status': 4, 'status_enum': 'Expired'}
    ]
    
    client = MockClient(order_responses)
    monitor = BuyMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_123', timeout_at)
    
    assert result['status'] == 'expired', f"Expected 'expired', got '{result['status']}'"
    assert result['filled_amount'] is None, "Should have no fill data"
    
    print(f"   ✓ Status: {result['status']}")
    print()


def test_5_monitor_timeout():
    """
    Test 5: Monitoring times out.
    
    Scenario:
        - Order stays pending
        - Timeout is reached
        
    Expected: Should return timeout status
    """
    print("Test 5: Monitor timeout")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 0.1,
        'BUY_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'current_price': 0.066
    }
    
    # Order always pending
    order_responses = [
        {'status': 0, 'status_enum': 'Pending'}
    ]
    
    client = MockClient(order_responses)
    monitor = BuyMonitor(config, client, state)
    
    # Set timeout to immediate past
    timeout_at = datetime.now() - timedelta(seconds=1)
    result = monitor.monitor_until_filled('ord_123', timeout_at)
    
    assert result['status'] == 'timeout', f"Expected 'timeout', got '{result['status']}'"
    assert result['filled_amount'] is None, "Should have no fill data"
    assert 'hours without fill' in result['reason'], "Should mention timeout"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Reason: {result['reason']}")
    print()


def test_6_extract_from_trades():
    """
    Test 6: Extract fill data from trades[] when primary fields missing.
    
    Scenario:
        - Order filled but filled_shares = 0
        - trades[] array has data in wei format
        
    Expected: Should extract from trades and convert from wei
    """
    print("Test 6: Extract fill data from trades array")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 1,
        'BUY_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'current_price': 0.066
    }
    
    # Order filled but primary fields are 0, with trades data
    order_responses = [
        {
            'status': 2,
            'status_enum': 'Finished',
            'filled_shares': 0,  # Missing
            'price': 0,  # Missing
            'filled_amount': 0,  # Missing
            'trades': [
                {
                    'shares': 100 * (10 ** 18),  # 100 tokens in wei
                    'amount': 6.6 * (10 ** 18)   # 6.6 USDT in wei
                }
            ]
        }
    ]
    
    client = MockClient(order_responses)
    monitor = BuyMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_123', timeout_at)
    
    assert result['status'] == 'filled', "Should be filled"
    assert result['filled_amount'] == 100.0, f"Should extract 100 tokens, got {result['filled_amount']}"
    assert result['filled_usdt'] == 6.6, f"Should extract 6.6 USDT, got {result['filled_usdt']}"
    assert abs(result['avg_fill_price'] - 0.066) < 0.001, "Should calculate price from trades"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Extracted from trades array")
    print(f"   ✓ Filled: {result['filled_amount']} tokens")
    print(f"   ✓ Price: ${result['avg_fill_price']:.4f}")
    print()


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("BUY MONITOR TESTS")
    print("=" * 60)
    print()
    
    try:
        test_1_order_fills_immediately()
        test_2_order_fills_after_pending()
        test_3_order_cancelled()
        test_4_order_expired()
        test_5_monitor_timeout()
        test_6_extract_from_trades()
        
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