"""
Mock Prediction Market Client for Testing
==========================================

Provides a mock implementation of PredictionMarketClient that returns
configurable test data without making real API calls.

Usage:
------
    from tests.mock_client import MockPredictionMarketClient

    # Create mock client
    mock = MockPredictionMarketClient()

    # Configure test data
    mock.set_markets([
        {
            'market_id': '1234',
            'title': 'Will Bitcoin hit $100k?',
            'yes_id': '0xabc',
            'no_id': '0xdef',
            'close_time': 1735689600,
            'status': 'ACTIVATED'
        }
    ])

    mock.set_orderbook('1234', 'YES',
        bids=[{'price': Decimal('0.65'), 'size': Decimal('100.0')}],
        asks=[{'price': Decimal('0.67'), 'size': Decimal('75.0')}]
    )

    # Use like real client
    markets = mock.get_active_markets()
    orderbook = mock.get_orderbook('1234', 'YES')
"""

from decimal import Decimal
from typing import Optional
from adapters.base import PredictionMarketClient


class MockPredictionMarketClient(PredictionMarketClient):
    """
    Mock implementation of PredictionMarketClient for testing.

    Implements all abstract methods from PredictionMarketClient without
    making real API calls. Allows tests to inject configurable test data.
    """

    def __init__(self):
        """Initialize mock client with empty test data."""
        # Configurable test data
        self.markets = []
        self.orderbooks = {}  # {(market_id, outcome_side): {bids: [...], asks: [...]}}
        self.orders = {}  # {order_id: order_dict}
        self.positions = {}  # {(market_id, outcome_side): size}
        self.balance = Decimal('1000.0')
        self.resolved_markets = set()

        # Order ID counter for generating unique IDs
        self._next_order_id = 1

    # =========================================================================
    # TEST DATA CONFIGURATION HELPERS
    # =========================================================================

    def set_markets(self, markets: list[dict]):
        """
        Set test markets data.

        Args:
            markets: List of market dicts (same format as get_active_markets)
        """
        self.markets = markets

    def set_orderbook(self, market_id: str, outcome_side: str, bids: list, asks: list):
        """
        Set test orderbook data for a specific market/outcome.

        Args:
            market_id: Market identifier
            outcome_side: "YES" or "NO"
            bids: List of bid orders [{'price': Decimal, 'size': Decimal}, ...]
            asks: List of ask orders [{'price': Decimal, 'size': Decimal}, ...]
        """
        self.orderbooks[(market_id, outcome_side)] = {
            'bids': bids,
            'asks': asks
        }

    def set_position(self, market_id: str, outcome_side: str, size: Decimal):
        """
        Set test position size.

        Args:
            market_id: Market identifier
            outcome_side: "YES" or "NO"
            size: Number of shares held (Decimal)
        """
        self.positions[(market_id, outcome_side)] = size

    def set_balance(self, balance: Decimal):
        """
        Set test balance.

        Args:
            balance: Available balance in USDT (Decimal)
        """
        self.balance = balance

    def set_market_resolved(self, market_id: str, resolved: bool = True):
        """
        Mark a market as resolved or unresolved.

        Args:
            market_id: Market identifier
            resolved: True to mark resolved, False to mark unresolved
        """
        if resolved:
            self.resolved_markets.add(market_id)
        else:
            self.resolved_markets.discard(market_id)

    def simulate_order_fill(self, order_id: str, filled_amount: Decimal, avg_price: Decimal):
        """
        Simulate an order being filled.

        Args:
            order_id: Order identifier to fill
            filled_amount: Amount filled (shares for SELL, USDT for BUY)
            avg_price: Average fill price
        """
        if order_id in self.orders:
            self.orders[order_id]['status'] = 'filled'
            self.orders[order_id]['filled_amount'] = filled_amount
            self.orders[order_id]['avg_fill_price'] = avg_price
            self.orders[order_id]['filled_usdt'] = filled_amount * avg_price

    def simulate_order_partial_fill(
        self,
        order_id: str,
        filled_amount: Decimal,
        avg_price: Decimal,
        trade_price: Decimal,
        trade_amount: Decimal,
        timestamp: int
    ):
        """
        Simulate a partial fill on an order.

        Args:
            order_id: Order identifier
            filled_amount: Total amount filled so far
            avg_price: Average fill price across all fills
            trade_price: Price of this specific trade
            trade_amount: Amount of this specific trade
            timestamp: Unix timestamp of trade
        """
        if order_id in self.orders:
            self.orders[order_id]['filled_amount'] = filled_amount
            self.orders[order_id]['avg_fill_price'] = avg_price
            self.orders[order_id]['filled_usdt'] = filled_amount * avg_price
            self.orders[order_id]['trades'].append({
                'price': trade_price,
                'amount': trade_amount,
                'timestamp': timestamp
            })

    # =========================================================================
    # MARKET DISCOVERY
    # =========================================================================

    def get_active_markets(self) -> list[dict]:
        """
        Return configured test markets.

        Returns:
            List of market dictionaries
        """
        return self.markets

    def get_market(self, market_id: str) -> dict:
        """
        Get specific market by ID.

        Args:
            market_id: Market identifier

        Returns:
            Market dict if found, empty dict {} otherwise
        """
        for market in self.markets:
            if market['market_id'] == market_id:
                return market
        return {}

    def get_orderbook(self, market_id: str, outcome_side: str) -> dict:
        """
        Get configured orderbook for market/outcome.

        Args:
            market_id: Market identifier
            outcome_side: "YES" or "NO"

        Returns:
            Orderbook dict with bids/asks, or empty orderbook if not configured
        """
        key = (market_id, outcome_side)
        return self.orderbooks.get(key, {'bids': [], 'asks': []})

    # =========================================================================
    # ACCOUNT OPERATIONS
    # =========================================================================

    def get_balance(self) -> Decimal:
        """
        Return configured test balance.

        Returns:
            Available balance (Decimal)
        """
        return self.balance

    # =========================================================================
    # ORDER OPERATIONS
    # =========================================================================

    def place_buy_order(
        self,
        market_id: str,
        outcome_side: str,
        price: Decimal,
        amount: Decimal
    ) -> dict:
        """
        Simulate placing a BUY order.

        Generates a mock order_id and stores order in pending state.

        Args:
            market_id: Market identifier
            outcome_side: "YES" or "NO"
            price: Limit price
            amount: USDT amount to spend

        Returns:
            {'order_id': str, 'status': 'pending'}
        """
        order_id = f"mock_buy_{self._next_order_id}"
        self._next_order_id += 1

        self.orders[order_id] = {
            'order_id': order_id,
            'market_id': market_id,
            'outcome_side': outcome_side,
            'order_type': 'BUY',
            'price': price,
            'amount': amount,
            'status': 'pending',
            'filled_amount': Decimal('0'),
            'avg_fill_price': Decimal('0'),
            'filled_usdt': Decimal('0'),
            'trades': []
        }

        return {'order_id': order_id, 'status': 'pending'}

    def place_sell_order(
        self,
        market_id: str,
        outcome_side: str,
        price: Decimal,
        amount: Decimal
    ) -> dict:
        """
        Simulate placing a SELL order.

        Generates a mock order_id and stores order in pending state.

        Args:
            market_id: Market identifier
            outcome_side: "YES" or "NO"
            price: Limit price
            amount: Number of shares to sell

        Returns:
            {'order_id': str, 'status': 'pending'}
        """
        order_id = f"mock_sell_{self._next_order_id}"
        self._next_order_id += 1

        self.orders[order_id] = {
            'order_id': order_id,
            'market_id': market_id,
            'outcome_side': outcome_side,
            'order_type': 'SELL',
            'price': price,
            'amount': amount,
            'status': 'pending',
            'filled_amount': Decimal('0'),
            'avg_fill_price': Decimal('0'),
            'filled_usdt': Decimal('0'),
            'trades': []
        }

        return {'order_id': order_id, 'status': 'pending'}

    def cancel_order(self, order_id: str) -> bool:
        """
        Simulate cancelling an order.

        Args:
            order_id: Order identifier

        Returns:
            True if order exists and was pending, False otherwise
        """
        if order_id not in self.orders:
            return False

        order = self.orders[order_id]
        if order['status'] != 'pending':
            return False

        order['status'] = 'cancelled'
        return True

    def get_order(self, order_id: str) -> dict:
        """
        Get order details.

        Args:
            order_id: Order identifier

        Returns:
            Order dict with status/fills, or empty dict {} if not found
        """
        if order_id not in self.orders:
            return {}

        order = self.orders[order_id]
        return {
            'order_id': order['order_id'],
            'status': order['status'],
            'filled_amount': order['filled_amount'],
            'avg_fill_price': order['avg_fill_price'],
            'filled_usdt': order['filled_usdt'],
            'trades': order['trades']
        }

    # =========================================================================
    # POSITION OPERATIONS
    # =========================================================================

    def get_position_size(self, market_id: str, outcome_side: str) -> Decimal:
        """
        Get configured position size.

        Args:
            market_id: Market identifier
            outcome_side: "YES" or "NO"

        Returns:
            Number of shares held (Decimal), or Decimal('0') if no position
        """
        key = (market_id, outcome_side)
        return self.positions.get(key, Decimal('0'))

    def is_market_resolved(self, market_id: str) -> bool:
        """
        Check if market is marked as resolved.

        Args:
            market_id: Market identifier

        Returns:
            True if market in resolved_markets set, False otherwise
        """
        return market_id in self.resolved_markets

    # =========================================================================
    # CLEANUP OPERATIONS
    # =========================================================================

    def cleanup_resolved_positions(self, market_id: str) -> None:
        """
        No-op for mock (base class implementation).

        Args:
            market_id: Market identifier
        """
        pass
