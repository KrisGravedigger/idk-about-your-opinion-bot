#!/usr/bin/env python3
"""
Test Autonomous Bot Orchestrator
=================================

Basic integration tests for AutonomousBot with mocked components.

Note: These are simplified tests. Full integration testing will be in Phase 9.

Run with: python test_autonomous_bot.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))


# Mock classes for testing
class MockClient:
    """Mock OpinionClient for testing."""
    
    def __init__(self):
        self.balance = 100.0
        self.orders_placed = []
        self.orders_cancelled = []
    
    def get_usdt_balance(self) -> float:
        return self.balance
    
    def get_order(self, order_id: str) -> dict:
        # Simulate filled order
        return {
            'status': 2,
            'status_enum': 'Finished',
            'filled_shares': 100.0,
            'price': 0.070,
            'filled_amount': 7.0,
            'trades': []
        }
    
    def get_market_orderbook(self, token_id: int) -> dict:
        return {
            'bids': [{'price': 0.066, 'size': 100}],
            'asks': [{'price': 0.072, 'size': 100}]
        }
    
    def cancel_order(self, order_id: str) -> bool:
        self.orders_cancelled.append(order_id)
        return True


class MockScanner:
    """Mock MarketScanner for testing."""
    
    def __init__(self, client):
        self.client = client
        self.markets = []
    
    def load_bonus_markets(self, filename: str):
        pass
    
    def scan_and_rank(self, limit: int = 10):
        from dataclasses import dataclass
        
        @dataclass
        class MockMarket:
            market_id: int = 813
            yes_token_id: int = 1626
            title: str = "Test Market"
            score: float = 75.0
            is_bonus: bool = False
        
        return [MockMarket()]
    
    def get_fresh_orderbook(self, market_id: int, token_id: int):
        return {
            'best_bid': 0.066,
            'best_ask': 0.072,
            'spread_abs': 0.006,
            'spread_pct': 9.09
        }


class MockOrderManager:
    """Mock OrderManager for testing."""
    
    def __init__(self, client):
        self.client = client
        self.orders = []
    
    def place_buy(self, market_id: int, token_id: str, price: float, amount_usdt: float):
        order = {
            'order_id': f'buy_ord_{len(self.orders) + 1}',
            'market_id': market_id,
            'token_id': token_id,
            'price': price,
            'amount_usdt': amount_usdt
        }
        self.orders.append(order)
        return order
    
    def place_sell(self, market_id: int, token_id: str, price: float, amount_tokens: float):
        order = {
            'order_id': f'sell_ord_{len(self.orders) + 1}',
            'market_id': market_id,
            'token_id': token_id,
            'price': price,
            'amount_tokens': amount_tokens
        }
        self.orders.append(order)
        return order


# Import after path setup
from core.autonomous_bot import AutonomousBot


def test_1_initialization():
    """
    Test 1: Bot initializes with all modules.
    
    Expected: All modules loaded successfully
    """
    print("Test 1: Bot initialization")
    
    config = {
        'CAPITAL_MODE': 'fixed',
        'CAPITAL_AMOUNT_USDT': 10.0,
        'CAPITAL_PERCENTAGE': 100.0,
        'MIN_BALANCE_TO_CONTINUE_USDT': 8.0,
        'MIN_POSITION_SIZE_USDT': 5.0,
        'MIN_POSITION_FOR_POINTS_USDT': 10.0,
        'WARN_IF_BELOW_POINTS_THRESHOLD': True,
        'BUY_MULTIPLIER': 1.10,
        'SELL_MULTIPLIER': 0.90,
        'SAFETY_MARGIN_CENTS': 0.001,
        'FILL_CHECK_INTERVAL_SECONDS': 1,
        'BUY_ORDER_TIMEOUT_HOURS': 24,
        'SELL_ORDER_TIMEOUT_HOURS': 24,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001,
        'CYCLE_DELAY_SECONDS': 1,
        'MAX_CYCLES': None
    }
    
    client = MockClient()
    bot = AutonomousBot(config, client)
    
    # Verify modules initialized
    assert bot.capital_manager is not None, "CapitalManager should be initialized"
    assert bot.state_manager is not None, "StateManager should be initialized"
    assert bot.scanner is not None, "MarketScanner should be initialized"
    assert bot.pricing is not None, "PricingStrategy should be initialized"
    assert bot.order_manager is not None, "OrderManager should be initialized"
    assert bot.tracker is not None, "PositionTracker should be initialized"
    
    print(f"   ✓ All modules initialized")
    print(f"   ✓ Modules: {bot._list_modules()}")
    print()


def test_2_idle_to_scanning():
    """
    Test 2: IDLE stage transitions to SCANNING.
    
    Expected: Stage changes from IDLE to SCANNING
    """
    print("Test 2: IDLE → SCANNING transition")
    
    config = {
        'CAPITAL_MODE': 'fixed',
        'CAPITAL_AMOUNT_USDT': 10.0,
        'CAPITAL_PERCENTAGE': 100.0,
        'MIN_BALANCE_TO_CONTINUE_USDT': 8.0,
        'MIN_POSITION_SIZE_USDT': 5.0,
        'MIN_POSITION_FOR_POINTS_USDT': 10.0,
        'WARN_IF_BELOW_POINTS_THRESHOLD': True,
        'BUY_MULTIPLIER': 1.10,
        'SELL_MULTIPLIER': 0.90,
        'SAFETY_MARGIN_CENTS': 0.001,
        'FILL_CHECK_INTERVAL_SECONDS': 1,
        'BUY_ORDER_TIMEOUT_HOURS': 24,
        'SELL_ORDER_TIMEOUT_HOURS': 24,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001,
        'CYCLE_DELAY_SECONDS': 1,
        'MAX_CYCLES': None
    }
    
    client = MockClient()
    bot = AutonomousBot(config, client)
    
    # Initialize state
    bot.state = bot.state_manager.initialize_state()
    bot.state['stage'] = 'IDLE'
    
    # Execute IDLE handler
    success = bot._handle_idle()
    
    assert success == True, "IDLE handler should succeed"
    assert bot.state['stage'] == 'SCANNING', f"Expected SCANNING, got {bot.state['stage']}"
    assert bot.state['cycle_number'] == 1, "Cycle number should increment"
    
    print(f"   ✓ Transitioned from IDLE to SCANNING")
    print(f"   ✓ Cycle number: {bot.state['cycle_number']}")
    print()


def test_3_stage_execution():
    """
    Test 3: Stage execution dispatcher works.
    
    Expected: Correct handler called for each stage
    """
    print("Test 3: Stage execution dispatcher")
    
    config = {
        'CAPITAL_MODE': 'fixed',
        'CAPITAL_AMOUNT_USDT': 10.0,
        'CAPITAL_PERCENTAGE': 100.0,
        'MIN_BALANCE_TO_CONTINUE_USDT': 8.0,
        'MIN_POSITION_SIZE_USDT': 5.0,
        'MIN_POSITION_FOR_POINTS_USDT': 10.0,
        'WARN_IF_BELOW_POINTS_THRESHOLD': True,
        'BUY_MULTIPLIER': 1.10,
        'SELL_MULTIPLIER': 0.90,
        'SAFETY_MARGIN_CENTS': 0.001,
        'FILL_CHECK_INTERVAL_SECONDS': 1,
        'BUY_ORDER_TIMEOUT_HOURS': 24,
        'SELL_ORDER_TIMEOUT_HOURS': 24,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001,
        'CYCLE_DELAY_SECONDS': 1,
        'MAX_CYCLES': None
    }
    
    client = MockClient()
    bot = AutonomousBot(config, client)
    bot.state = bot.state_manager.initialize_state()
    
    # Test each stage can be executed
    stages_to_test = ['IDLE', 'BUY_PLACED', 'SELL_PLACED', 'COMPLETED']
    
    for stage in stages_to_test:
        bot.state['stage'] = stage
        success = bot._execute_stage(stage)
        assert success == True, f"{stage} handler should succeed"
        print(f"   ✓ {stage} handler executed successfully")
    
    print()


def test_4_unknown_stage_handling():
    """
    Test 4: Unknown stage resets to IDLE.
    
    Expected: Bot resets to IDLE on unknown stage
    """
    print("Test 4: Unknown stage handling")
    
    config = {
        'CAPITAL_MODE': 'fixed',
        'CAPITAL_AMOUNT_USDT': 10.0,
        'CAPITAL_PERCENTAGE': 100.0,
        'MIN_BALANCE_TO_CONTINUE_USDT': 8.0,
        'MIN_POSITION_SIZE_USDT': 5.0,
        'MIN_POSITION_FOR_POINTS_USDT': 10.0,
        'WARN_IF_BELOW_POINTS_THRESHOLD': True,
        'BUY_MULTIPLIER': 1.10,
        'SELL_MULTIPLIER': 0.90,
        'SAFETY_MARGIN_CENTS': 0.001,
        'FILL_CHECK_INTERVAL_SECONDS': 1,
        'BUY_ORDER_TIMEOUT_HOURS': 24,
        'SELL_ORDER_TIMEOUT_HOURS': 24,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001,
        'CYCLE_DELAY_SECONDS': 1,
        'MAX_CYCLES': None
    }
    
    client = MockClient()
    bot = AutonomousBot(config, client)
    bot.state = bot.state_manager.initialize_state()
    
    # Set unknown stage
    bot.state['stage'] = 'UNKNOWN_STAGE'
    
    # Execute
    success = bot._execute_stage('UNKNOWN_STAGE')
    
    assert success == False, "Unknown stage should return False"
    assert bot.state['stage'] == 'IDLE', f"Should reset to IDLE, got {bot.state['stage']}"
    
    print(f"   ✓ Unknown stage detected")
    print(f"   ✓ Reset to IDLE")
    print()


def test_5_statistics_update():
    """
    Test 5: Statistics update after trade completion.
    
    Expected: Statistics correctly updated with P&L
    """
    print("Test 5: Statistics update")
    
    config = {
        'CAPITAL_MODE': 'fixed',
        'CAPITAL_AMOUNT_USDT': 10.0,
        'CAPITAL_PERCENTAGE': 100.0,
        'MIN_BALANCE_TO_CONTINUE_USDT': 8.0,
        'MIN_POSITION_SIZE_USDT': 5.0,
        'MIN_POSITION_FOR_POINTS_USDT': 10.0,
        'WARN_IF_BELOW_POINTS_THRESHOLD': True,
        'BUY_MULTIPLIER': 1.10,
        'SELL_MULTIPLIER': 0.90,
        'SAFETY_MARGIN_CENTS': 0.001,
        'FILL_CHECK_INTERVAL_SECONDS': 1,
        'BUY_ORDER_TIMEOUT_HOURS': 24,
        'SELL_ORDER_TIMEOUT_HOURS': 24,
        'LIQUIDITY_AUTO_CANCEL': True,
        'LIQUIDITY_BID_DROP_THRESHOLD': 25.0,
        'LIQUIDITY_SPREAD_THRESHOLD': 15.0,
        'ENABLE_STOP_LOSS': True,
        'STOP_LOSS_TRIGGER_PERCENT': -10.0,
        'STOP_LOSS_AGGRESSIVE_OFFSET': 0.001,
        'CYCLE_DELAY_SECONDS': 1,
        'MAX_CYCLES': None
    }
    
    client = MockClient()
    bot = AutonomousBot(config, client)
    bot.state = bot.state_manager.initialize_state()
    
    # Create mock PnL (winning trade)
    from position_tracker import PositionTracker
    from decimal import Decimal
    
    tracker = PositionTracker()
    pnl = tracker.calculate_pnl(
        buy_cost_usdt=10.0,
        buy_tokens=100.0,
        buy_price=0.10,
        sell_tokens=100.0,
        sell_price=0.11
    )
    
    # Update statistics
    initial_trades = bot.state['statistics']['total_trades']
    initial_wins = bot.state['statistics']['wins']
    
    bot._update_statistics(pnl)
    
    assert bot.state['statistics']['total_trades'] == initial_trades + 1, "Total trades should increment"
    assert bot.state['statistics']['wins'] == initial_wins + 1, "Wins should increment"
    assert bot.state['statistics']['total_pnl_usdt'] == float(pnl.pnl), "Total P&L should update"
    
    print(f"   ✓ Statistics updated")
    print(f"   ✓ Total trades: {bot.state['statistics']['total_trades']}")
    print(f"   ✓ Wins: {bot.state['statistics']['wins']}")
    print(f"   ✓ Total P&L: ${bot.state['statistics']['total_pnl_usdt']:.2f}")
    print()


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("AUTONOMOUS BOT TESTS")
    print("=" * 60)
    print()
    print("Note: These are basic unit tests with mocks.")
    print("Full integration testing will be in Phase 9.")
    print()
    
    try:
        test_1_initialization()
        test_2_idle_to_scanning()
        test_3_stage_execution()
        test_4_unknown_stage_handling()
        test_5_statistics_update()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print()
        print("Next: Create entry point (autonomous_bot_main.py)")
        
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