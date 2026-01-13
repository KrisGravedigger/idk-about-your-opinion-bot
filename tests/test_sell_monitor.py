#!/usr/bin/env python3
"""
Test SELL Monitor Module
=========================

Comprehensive tests for SellMonitor with mock client and stop-loss scenarios.

Run with: python test_sell_monitor.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))


# Mock API client for testing
class MockClient:
    """Mock OpinionClient for testing without real API."""
    
    def __init__(self, order_responses: list, orderbook: dict = None, cancel_success: bool = True):
        """
        Initialize mock client with pre-defined responses.
        
        Args:
            order_responses: List of order dicts to return sequentially
            orderbook: Optional orderbook dict for liquidity/stop-loss checks
            cancel_success: Whether order cancellation should succeed
        """
        self.order_responses = order_responses
        self.response_index = 0
        self.orderbook = orderbook or {
            'bids': [{'price': 0.066, 'size': 100}],
            'asks': [{'price': 0.072, 'size': 100}]
        }
        self.cancel_success = cancel_success
        self.cancelled_orders = []
        self.placed_orders = []
    
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
    
    def cancel_order(self, order_id: str) -> bool:
        """Mock order cancellation."""
        self.cancelled_orders.append(order_id)
        return self.cancel_success
    
    def place_sell_order(self, market_id: int, token_id: int, amount_tokens: float, price: float) -> str:
        """Mock placing sell order."""
        order_id = f"ord_stop_loss_{len(self.placed_orders) + 1}"
        self.placed_orders.append({
            'order_id': order_id,
            'market_id': market_id,
            'token_id': token_id,
            'amount_tokens': amount_tokens,
            'price': price
        })
        return order_id


# Import after path setup
from monitoring.sell_monitor import SellMonitor


def test_1_order_fills_immediately():
    """
    Test 1: SELL order fills on first check.
    
    Scenario:
        - Order is already filled when monitoring starts
        
    Expected: Should return filled status with fill data
    """
    print("Test 1: SELL order fills immediately")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 1,
        'SELL_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'avg_fill_price': 0.066,  # Buy price
        'filled_amount': 150.0,
        'sell_price': 0.072
    }
    
    # Order is filled immediately
    order_responses = [
        {
            'status': 2,  # Finished
            'status_enum': 'Finished',
            'filled_shares': 150.0,
            'price': 0.072,
            'filled_amount': 10.80
        }
    ]
    
    client = MockClient(order_responses)
    monitor = SellMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_456', timeout_at)
    
    assert result['status'] == 'filled', f"Expected 'filled', got '{result['status']}'"
    assert result['filled_amount'] == 150.0, "Should have filled_amount"
    assert result['avg_fill_price'] == 0.072, "Should have avg_fill_price"
    assert result['filled_usdt'] == 10.80, "Should have filled_usdt"
    assert result['fill_timestamp'] is not None, "Should have timestamp"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Sold: {result['filled_amount']} tokens")
    print(f"   ✓ Price: ${result['avg_fill_price']:.4f}")
    print(f"   ✓ Proceeds: ${result['filled_usdt']:.2f}")
    print()


def test_2_order_fills_after_pending():
    """
    Test 2: SELL order fills after being pending.
    
    Scenario:
        - Check 1: Pending
        - Check 2: Pending
        - Check 3: Filled
        
    Expected: Should return filled status after 3 checks
    """
    print("Test 2: SELL order fills after being pending")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 0.1,
        'SELL_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'avg_fill_price': 0.066,
        'filled_amount': 100.0,
        'sell_price': 0.070
    }
    
    # Order pending, then pending, then filled
    order_responses = [
        {'status': 0, 'status_enum': 'Pending'},
        {'status': 0, 'status_enum': 'Pending'},
        {
            'status': 2,
            'status_enum': 'Finished',
            'filled_shares': 100.0,
            'price': 0.070,
            'filled_amount': 7.00
        }
    ]
    
    client = MockClient(order_responses)
    monitor = SellMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_456', timeout_at)
    
    assert result['status'] == 'filled', "Should eventually fill"
    assert result['filled_amount'] == 100.0, "Should have correct amount"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Filled after pending checks")
    print()


def test_3_order_cancelled():
    """
    Test 3: SELL order gets cancelled.
    
    Scenario:
        - Order status returns Cancelled
        
    Expected: Should return cancelled status
    """
    print("Test 3: SELL order cancelled")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 1,
        'SELL_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'avg_fill_price': 0.066,
        'filled_amount': 100.0,
        'sell_price': 0.070
    }
    
    order_responses = [
        {'status': 3, 'status_enum': 'Cancelled'}
    ]
    
    client = MockClient(order_responses)
    monitor = SellMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_456', timeout_at)
    
    assert result['status'] == 'cancelled', f"Expected 'cancelled', got '{result['status']}'"
    assert result['filled_amount'] is None, "Should have no fill data"
    assert result['reason'] == 'Order cancelled', "Should have reason"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Reason: {result['reason']}")
    print()


def test_4_order_expired():
    """
    Test 4: SELL order expires.
    
    Scenario:
        - Order status returns Expired
        
    Expected: Should return expired status
    """
    print("Test 4: SELL order expired")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 1,
        'SELL_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'avg_fill_price': 0.066,
        'filled_amount': 100.0,
        'sell_price': 0.070
    }
    
    order_responses = [
        {'status': 4, 'status_enum': 'Expired'}
    ]
    
    client = MockClient(order_responses)
    monitor = SellMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_456', timeout_at)
    
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
        'SELL_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'avg_fill_price': 0.066,
        'filled_amount': 100.0,
        'sell_price': 0.070
    }
    
    # Order always pending
    order_responses = [
        {'status': 0, 'status_enum': 'Pending'}
    ]
    
    client = MockClient(order_responses)
    monitor = SellMonitor(config, client, state)
    
    # Set timeout to immediate past
    timeout_at = datetime.now() - timedelta(seconds=1)
    result = monitor.monitor_until_filled('ord_456', timeout_at)
    
    assert result['status'] == 'timeout', f"Expected 'timeout', got '{result['status']}'"
    assert result['filled_amount'] is None, "Should have no fill data"
    assert 'hours without fill' in result['reason'], "Should mention timeout"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Reason: {result['reason']}")
    print()


def test_6_stop_loss_triggered():
    """
    Test 6: Stop-loss triggers due to unrealized loss.
    
    Scenario:
        - Buy price: $0.100
        - Current bid: $0.070 (30% loss)
        - Stop-loss threshold: -10%
        
    Expected: 
        - Should detect stop-loss condition
        - Should cancel order
        - Should place aggressive limit
        - Should return stop_loss_triggered status
    """
    print("Test 6: Stop-loss triggered (30% loss)")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 0.1,
        'SELL_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,  # Trigger at -10%
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'avg_fill_price': 0.100,  # Buy price
        'filled_amount': 100.0,
        'sell_price': 0.110
    }
    
    # Order stays pending (will be cancelled by stop-loss)
    order_responses = [
        {'status': 0, 'status_enum': 'Pending'}
    ]
    
    # Orderbook shows 15% loss (triggers stop-loss but not liquidity deterioration)
    orderbook = {
        'bids': [
            {'price': 0.085, 'size': 100},  # Current bid = $0.085 (15% loss from $0.100)
            {'price': 0.084, 'size': 150}   # 15% loss triggers stop-loss (-10%)
        ],                                   # but NOT liquidity deterioration (25%)
        'asks': [
            {'price': 0.095, 'size': 100},
            {'price': 0.096, 'size': 150}
        ]
    }
    
    client = MockClient(order_responses, orderbook=orderbook)
    monitor = SellMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_456', timeout_at)
    
    assert result['status'] == 'stop_loss_triggered', f"Expected 'stop_loss_triggered', got '{result['status']}'"
    assert result['filled_amount'] is None, "Should have no fill data"
    assert '-30' in result['reason'] or 'loss' in result['reason'].lower(), "Should mention loss"
    
    # Verify stop-loss actions
    assert len(client.cancelled_orders) == 1, "Should have cancelled original order"
    assert client.cancelled_orders[0] == 'ord_456', "Should cancel correct order"
    assert len(client.placed_orders) == 1, "Should have placed aggressive limit"
    
    aggressive_order = client.placed_orders[0]
    assert aggressive_order['price'] == 0.086, f"Aggressive price should be 0.086, got {aggressive_order['price']}"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Unrealized loss: 15% (triggered at -10% threshold)")
    print(f"   ✓ Original order cancelled: {client.cancelled_orders[0]}")
    print(f"   ✓ Aggressive limit placed: {aggressive_order['order_id']} @ ${aggressive_order['price']:.4f}")
    print()


def test_7_stop_loss_not_triggered():
    """
    Test 7: Stop-loss NOT triggered (loss within threshold).
    
    Scenario:
        - Buy price: $0.100
        - Current bid: $0.095 (5% loss)
        - Stop-loss threshold: -10%
        
    Expected: 
        - Should NOT trigger stop-loss
        - Order should eventually fill normally
    """
    print("Test 7: Stop-loss NOT triggered (5% loss within threshold)")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 0.1,
        'SELL_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,  # Trigger at -10%
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'avg_fill_price': 0.100,  # Buy price
        'filled_amount': 100.0,
        'sell_price': 0.105
    }
    
    # Order pending, then fills
    order_responses = [
        {'status': 0, 'status_enum': 'Pending'},
        {'status': 0, 'status_enum': 'Pending'},
        {
            'status': 2,
            'status_enum': 'Finished',
            'filled_shares': 100.0,
            'price': 0.105,
            'filled_amount': 10.50
        }
    ]
    
    # Orderbook shows only 5% loss (within threshold)
    orderbook = {
        'bids': [
            {'price': 0.095, 'size': 100},  # Current bid = $0.095 (5% loss)
            {'price': 0.094, 'size': 150}
        ],
        'asks': [
            {'price': 0.105, 'size': 100},
            {'price': 0.106, 'size': 150}
        ]
    }
    
    client = MockClient(order_responses, orderbook=orderbook)
    monitor = SellMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_456', timeout_at)
    
    assert result['status'] == 'filled', f"Expected 'filled', got '{result['status']}'"
    assert result['filled_amount'] == 100.0, "Should have filled normally"
    
    # Verify NO stop-loss actions
    assert len(client.cancelled_orders) == 0, "Should NOT cancel order"
    assert len(client.placed_orders) == 0, "Should NOT place aggressive limit"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Loss within threshold - no stop-loss triggered")
    print(f"   ✓ Order filled normally at ${result['avg_fill_price']:.4f}")
    print()


def test_8_stop_loss_disabled():
    """
    Test 8: Stop-loss disabled (should not trigger even with big loss).
    
    Scenario:
        - ENABLE_STOP_LOSS = False
        - Buy price: $0.100
        - Current bid: $0.070 (30% loss)
        
    Expected: 
        - Should NOT trigger stop-loss (disabled)
        - Should continue monitoring normally
    """
    print("Test 8: Stop-loss disabled (should not trigger)")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 0.1,
        'SELL_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': False,  # DISABLED
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'avg_fill_price': 0.100,  # Buy price
        'filled_amount': 100.0,
        'sell_price': 0.110
    }
    
    # Order pending, then fills
    order_responses = [
        {'status': 0, 'status_enum': 'Pending'},
        {'status': 0, 'status_enum': 'Pending'},
        {
            'status': 2,
            'status_enum': 'Finished',
            'filled_shares': 100.0,
            'price': 0.075,  # Filled at loss
            'filled_amount': 7.50
        }
    ]
    
    # Orderbook shows 30% loss (but stop-loss disabled)
    orderbook = {
        'bids': [
            {'price': 0.070, 'size': 100},
            {'price': 0.069, 'size': 150}
        ],
        'asks': [
            {'price': 0.080, 'size': 100},
            {'price': 0.081, 'size': 150}
        ]
    }
    
    client = MockClient(order_responses, orderbook=orderbook)
    monitor = SellMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_456', timeout_at)
    
    assert result['status'] == 'filled', f"Expected 'filled', got '{result['status']}'"
    assert result['avg_fill_price'] == 0.075, "Should fill at loss price"
    
    # Verify NO stop-loss actions
    assert len(client.cancelled_orders) == 0, "Should NOT cancel order (disabled)"
    assert len(client.placed_orders) == 0, "Should NOT place aggressive limit"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Stop-loss disabled - no protection triggered")
    print(f"   ✓ Order filled at ${result['avg_fill_price']:.4f} (loss)")
    print()


def test_9_extract_from_trades():
    """
    Test 9: Extract fill data from trades[] when primary fields missing.
    
    Scenario:
        - Order filled but filled_shares = 0
        - trades[] array has data in wei format
        
    Expected: Should extract from trades and convert from wei
    """
    print("Test 9: Extract fill data from trades array")
    
    config = {
        'FILL_CHECK_INTERVAL_SECONDS': 1,
        'SELL_ORDER_TIMEOUT_HOURS': 1,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001
    }
    
    state = {
        'market_id': 813,
        'token_id': 1626,
        'avg_fill_price': 0.066,
        'filled_amount': 100.0,
        'sell_price': 0.072
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
                    'amount': 7.2 * (10 ** 18)   # 7.2 USDT in wei
                }
            ]
        }
    ]
    
    client = MockClient(order_responses)
    monitor = SellMonitor(config, client, state)
    
    timeout_at = datetime.now() + timedelta(hours=1)
    result = monitor.monitor_until_filled('ord_456', timeout_at)
    
    assert result['status'] == 'filled', "Should be filled"
    assert result['filled_amount'] == 100.0, f"Should extract 100 tokens, got {result['filled_amount']}"
    assert result['filled_usdt'] == 7.2, f"Should extract 7.2 USDT, got {result['filled_usdt']}"
    assert abs(result['avg_fill_price'] - 0.072) < 0.001, "Should calculate price from trades"
    
    print(f"   ✓ Status: {result['status']}")
    print(f"   ✓ Extracted from trades array")
    print(f"   ✓ Sold: {result['filled_amount']} tokens")
    print(f"   ✓ Price: ${result['avg_fill_price']:.4f}")
    print()


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("SELL MONITOR TESTS")
    print("=" * 60)
    print()
    
    try:
        test_1_order_fills_immediately()
        test_2_order_fills_after_pending()
        test_3_order_cancelled()
        test_4_order_expired()
        test_5_monitor_timeout()
        test_6_stop_loss_triggered()
        test_7_stop_loss_not_triggered()
        test_8_stop_loss_disabled()
        test_9_extract_from_trades()
        
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