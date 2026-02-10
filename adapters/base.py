"""
Prediction Market Client - Abstract Base Class
===============================================

Platform-agnostic interface for prediction market trading operations.

This ABC defines the contract that all platform adapters must implement.
It allows the bot to support multiple prediction market platforms (Opinion.trade,
Hyperliquid, etc.) by simply swapping the adapter implementation.

Design Philosophy:
------------------
- All methods use (market_id, outcome_side) as universal identifiers
- Platform-specific IDs (like token_id) are handled internally by adapters
- Return types are standardized dicts for cross-platform compatibility
- Financial values use Decimal for precision (never float)

Usage:
------
    # Create platform-specific adapter
    from adapters.opinion_adapter import OpinionAdapter
    client = OpinionAdapter(api_key="...", private_key="...")

    # Use universal interface
    markets = client.get_active_markets()
    orderbook = client.get_orderbook(market_id="1234", outcome_side="YES")
    balance = client.get_balance()

    # Place orders
    result = client.place_buy_order(
        market_id="1234",
        outcome_side="YES",
        price=Decimal("0.65"),
        amount=Decimal("100.00")
    )
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional


class PredictionMarketClient(ABC):
    """
    Abstract base class for prediction market platform clients.

    All platform adapters (Opinion, Hyperliquid, etc.) must implement this interface.
    This ensures the bot can switch between platforms with minimal code changes.

    Key Concepts:
    -------------
    - **market_id**: Universal identifier for a prediction market (platform-specific format)
    - **outcome_side**: "YES" or "NO" (standardized across platforms)
    - **price**: Decimal between 0.01 and 0.99 (probability as price)
    - **amount**: Decimal in base stablecoin units (USDT, USDH, etc.)

    All methods raise NotImplementedError if called on base class.
    Concrete adapters must override all abstract methods.
    """

    # =========================================================================
    # MARKET DISCOVERY
    # =========================================================================

    @abstractmethod
    def get_active_markets(self) -> list[dict]:
        """
        Fetch all active (tradeable) markets from the platform.

        Returns:
            List of market dictionaries, each containing:
                - market_id (str): Platform-specific market identifier
                - title (str): Human-readable market question
                - yes_id (str): Internal identifier for YES outcome (adapter use)
                - no_id (str): Internal identifier for NO outcome (adapter use)
                - close_time (int): Unix timestamp when market closes
                - status (str): Market status (e.g., "ACTIVATED", "OPEN")

        Example:
            >>> client = OpinionAdapter(...)
            >>> markets = client.get_active_markets()
            >>> markets[0]
            {
                'market_id': '1234',
                'title': 'Will Bitcoin hit $100k in 2026?',
                'yes_id': '0xabc...',
                'no_id': '0xdef...',
                'close_time': 1735689600,
                'status': 'ACTIVATED'
            }

        Note:
            - Pagination is handled internally by the adapter
            - Returns only markets that are currently tradeable
            - Market status terminology may vary by platform but should map to common states
        """
        raise NotImplementedError("get_active_markets must be implemented by adapter")

    @abstractmethod
    def get_market(self, market_id: str) -> dict:
        """
        Fetch detailed information for a specific market.

        Args:
            market_id: Platform-specific market identifier

        Returns:
            Market dictionary with same fields as get_active_markets(),
            plus additional details like description, resolution criteria, etc.
            Returns empty dict {} if market not found.

        Example:
            >>> client = OpinionAdapter(...)
            >>> market = client.get_market(market_id="1234")
            >>> market['title']
            'Will Bitcoin hit $100k in 2026?'

        Note:
            - Should include current market status for resolution detection
            - May include extra platform-specific metadata
        """
        raise NotImplementedError("get_market must be implemented by adapter")

    @abstractmethod
    def get_orderbook(self, market_id: str, outcome_side: str) -> dict:
        """
        Fetch current orderbook for a specific market outcome.

        Args:
            market_id: Platform-specific market identifier
            outcome_side: "YES" or "NO"

        Returns:
            Orderbook dictionary containing:
                - bids (list[dict]): Buy orders, DESCENDING by price
                    - Each order: {'price': Decimal, 'size': Decimal}
                - asks (list[dict]): Sell orders, ASCENDING by price
                    - Each order: {'price': Decimal, 'size': Decimal}

        Example:
            >>> client = OpinionAdapter(...)
            >>> book = client.get_orderbook(market_id="1234", outcome_side="YES")
            >>> book
            {
                'bids': [
                    {'price': Decimal('0.65'), 'size': Decimal('100.0')},  # Best bid
                    {'price': Decimal('0.64'), 'size': Decimal('50.0')},
                ],
                'asks': [
                    {'price': Decimal('0.67'), 'size': Decimal('75.0')},   # Best ask
                    {'price': Decimal('0.68'), 'size': Decimal('120.0')},
                ]
            }

        Critical Requirements:
            - bids[0] MUST be highest bid (descending order)
            - asks[0] MUST be lowest ask (ascending order)
            - price MUST be Decimal (not float)
            - size MUST be Decimal in quote token units (USDT)

        Note:
            - Adapter must translate platform-specific orderbook to this format
            - Empty orderbook returns {'bids': [], 'asks': []}
        """
        raise NotImplementedError("get_orderbook must be implemented by adapter")

    # =========================================================================
    # ACCOUNT OPERATIONS
    # =========================================================================

    @abstractmethod
    def get_balance(self) -> Decimal:
        """
        Get available balance in base stablecoin (USDT/USDH/etc).

        Returns:
            Decimal: Available balance for trading (excludes frozen/locked funds)

        Example:
            >>> client = OpinionAdapter(...)
            >>> balance = client.get_balance()
            >>> balance
            Decimal('1234.56')

        Note:
            - Returns ONLY available balance (not total)
            - Frozen balance (in open orders) should be excluded
            - Returns Decimal('0') if no balance or error
        """
        raise NotImplementedError("get_balance must be implemented by adapter")

    # =========================================================================
    # ORDER OPERATIONS
    # =========================================================================

    @abstractmethod
    def place_buy_order(
        self,
        market_id: str,
        outcome_side: str,
        price: Decimal,
        amount: Decimal
    ) -> dict:
        """
        Place a limit BUY order (open/increase position).

        Args:
            market_id: Platform-specific market identifier
            outcome_side: "YES" or "NO"
            price: Limit price per share (Decimal between 0.01 and 0.99)
            amount: Order size in quote token (USDT), not shares

        Returns:
            Order result dictionary:
                - order_id (str): Platform-specific order identifier
                - status (str): Order status ('pending', 'filled', 'failed', etc.)
            Returns empty dict {} on failure.

        Example:
            >>> client = OpinionAdapter(...)
            >>> result = client.place_buy_order(
            ...     market_id="1234",
            ...     outcome_side="YES",
            ...     price=Decimal("0.65"),
            ...     amount=Decimal("100.00")
            ... )
            >>> result
            {'order_id': 'abc123', 'status': 'pending'}

        Note:
            - This is a LIMIT order (not market order)
            - amount is in USDT (quote token), not number of shares
            - Adapter must convert (market_id, outcome_side) to platform token_id
            - Should handle insufficient balance gracefully (return {})
        """
        raise NotImplementedError("place_buy_order must be implemented by adapter")

    @abstractmethod
    def place_sell_order(
        self,
        market_id: str,
        outcome_side: str,
        price: Decimal,
        amount: Decimal
    ) -> dict:
        """
        Place a limit SELL order (close/reduce position).

        Args:
            market_id: Platform-specific market identifier
            outcome_side: "YES" or "NO"
            price: Limit price per share (Decimal between 0.01 and 0.99)
            amount: Number of shares to sell (NOT quote token value)

        Returns:
            Order result dictionary:
                - order_id (str): Platform-specific order identifier
                - status (str): Order status ('pending', 'filled', 'failed', etc.)
            Returns empty dict {} on failure.

        Example:
            >>> client = OpinionAdapter(...)
            >>> result = client.place_sell_order(
            ...     market_id="1234",
            ...     outcome_side="YES",
            ...     price=Decimal("0.70"),
            ...     amount=Decimal("153.8")  # Number of shares
            ... )
            >>> result
            {'order_id': 'def456', 'status': 'pending'}

        Critical Difference:
            - BUY orders: amount = USDT to spend
            - SELL orders: amount = shares to sell

        Note:
            - Adapter must convert (market_id, outcome_side) to platform token_id
            - Should handle insufficient shares gracefully (return {})
        """
        raise NotImplementedError("place_sell_order must be implemented by adapter")

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Platform-specific order identifier (from place_*_order)

        Returns:
            bool: True if cancelled successfully, False otherwise

        Example:
            >>> client = OpinionAdapter(...)
            >>> success = client.cancel_order(order_id="abc123")
            >>> success
            True

        Note:
            - Returns False if order already filled/cancelled
            - Returns False if order not found
            - Should handle network errors gracefully
        """
        raise NotImplementedError("cancel_order must be implemented by adapter")

    @abstractmethod
    def get_order(self, order_id: str) -> dict:
        """
        Get detailed status of an order.

        Args:
            order_id: Platform-specific order identifier

        Returns:
            Order status dictionary:
                - order_id (str): Order identifier (same as input)
                - status (str): Current status
                    - 'pending': Order open, waiting for fill
                    - 'filled': Order completely filled
                    - 'cancelled': Order cancelled by user
                    - 'expired': Order expired (timeout)
                    - 'failed': Order failed (insufficient balance, etc.)
                - filled_amount (Decimal): Amount filled so far (shares for SELL, USDT for BUY)
                - avg_fill_price (Decimal): Average price of fills (0 if no fills)
                - filled_usdt (Decimal): Total USDT value of fills
                - trades (list[dict]): List of individual fills
                    - Each trade: {'price': Decimal, 'amount': Decimal, 'timestamp': int}
            Returns empty dict {} if order not found.

        Example:
            >>> client = OpinionAdapter(...)
            >>> order = client.get_order(order_id="abc123")
            >>> order
            {
                'order_id': 'abc123',
                'status': 'filled',
                'filled_amount': Decimal('153.8'),
                'avg_fill_price': Decimal('0.6502'),
                'filled_usdt': Decimal('100.02'),
                'trades': [
                    {'price': Decimal('0.65'), 'amount': Decimal('100.0'), 'timestamp': 1735689600},
                    {'price': Decimal('0.651'), 'amount': Decimal('53.8'), 'timestamp': 1735689605}
                ]
            }

        Note:
            - Status strings must match the standardized set above
            - trades list may be empty if platform doesn't provide fill history
            - avg_fill_price should be weighted average (not simple average)
        """
        raise NotImplementedError("get_order must be implemented by adapter")

    # =========================================================================
    # POSITION OPERATIONS
    # =========================================================================

    @abstractmethod
    def get_position_size(self, market_id: str, outcome_side: str) -> Decimal:
        """
        Get current position size (shares owned) for a specific market outcome.

        Args:
            market_id: Platform-specific market identifier
            outcome_side: "YES" or "NO"

        Returns:
            Decimal: Number of shares currently held in this position
            Returns Decimal('0') if no position.

        Example:
            >>> client = OpinionAdapter(...)
            >>> shares = client.get_position_size(market_id="1234", outcome_side="YES")
            >>> shares
            Decimal('153.8')

        Note:
            - Returns shares owned, not USDT value
            - Should reflect fills that happened while bot was offline
            - Used for self-healing position recovery
        """
        raise NotImplementedError("get_position_size must be implemented by adapter")

    @abstractmethod
    def is_market_resolved(self, market_id: str) -> bool:
        """
        Check if a market has been resolved (settled).

        Args:
            market_id: Platform-specific market identifier

        Returns:
            bool: True if market has been resolved, False otherwise

        Example:
            >>> client = OpinionAdapter(...)
            >>> resolved = client.is_market_resolved(market_id="1234")
            >>> resolved
            True

        Note:
            - Used to detect if we need to exit positions before resolution
            - May check market status field (e.g., "RESOLVED", "SETTLED")
            - Returns False if market not found or API error
        """
        raise NotImplementedError("is_market_resolved must be implemented by adapter")

    # =========================================================================
    # CLEANUP OPERATIONS
    # =========================================================================

    def cleanup_resolved_positions(self, market_id: str) -> None:
        """
        Redeem/settle positions from a resolved market.

        Args:
            market_id: Platform-specific market identifier

        Returns:
            None

        Example:
            >>> client = OpinionAdapter(...)
            >>> client.cleanup_resolved_positions(market_id="1234")
            # Redeems any positions from market 1234

        Note:
            - Default implementation is no-op (for platforms with auto-settlement)
            - Platforms requiring manual redemption (like Opinion.trade) should override
            - Should be idempotent (safe to call multiple times)
            - Should log errors but not raise exceptions
        """
        # Default: no-op for platforms with automatic settlement
        pass
