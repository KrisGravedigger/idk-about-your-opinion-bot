"""
Opinion.trade Platform Adapter
================================

Concrete implementation of PredictionMarketClient for Opinion.trade platform.

This adapter wraps the Opinion CLOB SDK and translates between:
- Universal interface (market_id, outcome_side) → Opinion SDK (token_id)
- Opinion status enums → Standardized status strings
- Pydantic response models → Standard dictionaries

Key Translation Logic:
----------------------
1. Token ID Lookup:
   - (market_id, "YES") → yes_token_id from market cache
   - (market_id, "NO") → no_token_id from market cache

2. Status Normalization:
   - Opinion status codes (1-5) → Standard strings ('pending', 'filled', etc.)
   - ModelsTopicStatus enum → 'resolved' detection

3. Fill Data Extraction:
   - Multiple fallback chains to handle SDK response variations
   - Robust parsing of fill amounts, avg prices, USDT values

Architecture:
-------------
- Inherits from PredictionMarketClient ABC
- Maintains internal OpinionClient instance (wrapped SDK)
- Caches market metadata for token_id lookups
- Preserves all existing error handling and logging
"""

import time
from typing import Optional
from decimal import Decimal

# Opinion SDK imports
from opinion_clob_sdk import (
    Client,
    TopicStatusFilter,
    TopicStatus,
    BalanceNotEnough,
    NoPositionsToRedeem,
    InsufficientGasBalance
)
from opinion_clob_sdk.chain.py_order_utils.model.order import PlaceOrderDataInput
from opinion_clob_sdk.chain.py_order_utils.model.sides import OrderSide
from opinion_clob_sdk.chain.py_order_utils.model.order_type import LIMIT_ORDER

# Local imports
from adapters.base import PredictionMarketClient
from config_loader import config
from logger_config import setup_logger
from utils import safe_float, safe_int, wei_to_usdt_float

# Initialize logger
logger = setup_logger(__name__)

# Extract credentials from config_loader
API_HOST = config.API_HOST
API_KEY = config.API_KEY
PRIVATE_KEY = config.PRIVATE_KEY
MULTI_SIG_ADDRESS = config.MULTI_SIG_ADDRESS
CHAIN_ID = config.CHAIN_ID
RPC_URL = config.RPC_URL


class OpinionAdapter(PredictionMarketClient):
    """
    Opinion.trade platform adapter.

    Translates universal prediction market interface to Opinion.trade SDK calls.
    Handles token_id mapping, status normalization, and response parsing.

    Usage:
        adapter = OpinionAdapter()
        markets = adapter.get_active_markets()
        orderbook = adapter.get_orderbook(market_id="1234", outcome_side="YES")
    """

    def __init__(self):
        """
        Initialize Opinion.trade adapter with credentials from config.

        Raises:
            ValueError: If required credentials are missing
        """
        # Validate credentials
        if not API_KEY:
            raise ValueError("API_KEY not set. Check your .env file.")
        if not PRIVATE_KEY:
            raise ValueError("PRIVATE_KEY not set. Check your .env file.")

        # Multi-sig is optional - track mode
        self._read_only_mode = not MULTI_SIG_ADDRESS
        if self._read_only_mode:
            logger.warning("⚠️ MULTI_SIG_ADDRESS not set - running in READ-ONLY mode")
            logger.warning("   Market scanning and data queries will work")
            logger.warning("   Order placement will be blocked until address is configured")

        logger.debug("Initializing Opinion adapter...")

        # Create the underlying SDK client
        client_params = {
            'host': API_HOST,
            'apikey': API_KEY,
            'chain_id': CHAIN_ID,
            'private_key': PRIVATE_KEY,
            'rpc_url': RPC_URL
        }

        # Only add multi_sig_addr if using Gnosis Safe
        if MULTI_SIG_ADDRESS:
            logger.debug(f"Using multi-sig address: {MULTI_SIG_ADDRESS}")
            client_params['multi_sig_addr'] = MULTI_SIG_ADDRESS
        else:
            logger.debug("Using standard wallet (address derived from private_key)")

        self._client = Client(**client_params)

        # Cache for market metadata (token_id lookups)
        self._market_cache = {}

        logger.info("Opinion adapter initialized successfully")

    # =========================================================================
    # HELPER METHODS (INTERNAL)
    # =========================================================================

    def _require_trading_mode(self, operation: str):
        """
        Check if trading operations are available.

        Args:
            operation: Name of operation being attempted

        Raises:
            RuntimeError: If MULTI_SIG_ADDRESS not configured
        """
        if self._read_only_mode:
            raise RuntimeError(
                f"Cannot perform '{operation}' - adapter in READ-ONLY mode. "
                f"Set MULTI_SIG_ADDRESS in .env to enable trading operations."
            )

    def _get_token_id(self, market_id: str, outcome_side: str) -> Optional[str]:
        """
        Lookup token_id for a market outcome.

        Args:
            market_id: Market identifier (as string)
            outcome_side: "YES" or "NO"

        Returns:
            Token ID string or None if not found
        """
        # Check cache first
        cache_key = int(market_id)
        if cache_key in self._market_cache:
            market_data = self._market_cache[cache_key]
        else:
            # Fetch market data
            market_data = self.get_market(market_id)
            if not market_data:
                logger.error(f"Market {market_id} not found")
                return None
            self._market_cache[cache_key] = market_data

        # Extract token_id based on outcome_side
        if outcome_side.upper() == "YES":
            return market_data.get('yes_id')
        elif outcome_side.upper() == "NO":
            return market_data.get('no_id')
        else:
            logger.error(f"Invalid outcome_side: {outcome_side}")
            return None

    def _normalize_status(self, status_code: Optional[int]) -> str:
        """
        Normalize Opinion status code to standard string.

        Args:
            status_code: Opinion status (1=PENDING, 2=FINISHED, 3=CANCELLED, 4=EXPIRED, 5=FAILED)

        Returns:
            Standardized status string
        """
        STATUS_MAP = {
            1: 'pending',
            2: 'filled',
            3: 'cancelled',
            4: 'expired',
            5: 'failed'
        }

        if status_code is None:
            return 'unknown'

        return STATUS_MAP.get(status_code, f'unknown({status_code})')

    def _extract_fill_data(self, order_dict: dict) -> dict:
        """
        Extract fill data from order response with fallback chains.

        Args:
            order_dict: Order dictionary from API response

        Returns:
            Dictionary with filled_amount, avg_fill_price, filled_usdt
        """
        # Initialize defaults
        fill_data = {
            'filled_amount': Decimal('0'),
            'avg_fill_price': Decimal('0'),
            'filled_usdt': Decimal('0'),
            'trades': []
        }

        # Try to extract filled amount (shares for SELL, USDT for BUY)
        # Fallback chain: filled_amount → executed_amount → amount_filled
        filled_amount_raw = (
            order_dict.get('filled_amount') or
            order_dict.get('executed_amount') or
            order_dict.get('amount_filled') or
            0
        )

        try:
            fill_data['filled_amount'] = Decimal(str(filled_amount_raw))
        except (ValueError, TypeError):
            fill_data['filled_amount'] = Decimal('0')

        # Try to extract average fill price
        # Fallback chain: avg_price → average_price → price
        avg_price_raw = (
            order_dict.get('avg_price') or
            order_dict.get('average_price') or
            order_dict.get('price') or
            0
        )

        try:
            fill_data['avg_fill_price'] = Decimal(str(avg_price_raw))
        except (ValueError, TypeError):
            fill_data['avg_fill_price'] = Decimal('0')

        # Try to extract filled USDT value
        # Fallback chain: filled_usdt → executed_usdt → (calculate from amount * price)
        filled_usdt_raw = (
            order_dict.get('filled_usdt') or
            order_dict.get('executed_usdt') or
            order_dict.get('total_executed')
        )

        if filled_usdt_raw:
            try:
                fill_data['filled_usdt'] = Decimal(str(filled_usdt_raw))
            except (ValueError, TypeError):
                # Fallback: calculate from filled_amount * avg_price
                fill_data['filled_usdt'] = fill_data['filled_amount'] * fill_data['avg_fill_price']
        else:
            # Calculate from filled_amount * avg_price
            fill_data['filled_usdt'] = fill_data['filled_amount'] * fill_data['avg_fill_price']

        # Try to extract trades/fills list (optional)
        trades_raw = order_dict.get('trades') or order_dict.get('fills') or []

        for trade in trades_raw:
            try:
                fill_data['trades'].append({
                    'price': Decimal(str(trade.get('price', 0))),
                    'amount': Decimal(str(trade.get('amount', 0))),
                    'timestamp': int(trade.get('timestamp', 0))
                })
            except (ValueError, TypeError, AttributeError):
                continue

        return fill_data

    # =========================================================================
    # MARKET DISCOVERY (ABSTRACT METHODS)
    # =========================================================================

    def get_active_markets(self) -> list[dict]:
        """
        Fetch all active (ACTIVATED) markets with pagination.

        Returns:
            List of market dictionaries with standardized fields
        """
        all_markets = []
        page = 1
        page_size = 20  # Maximum allowed by API

        logger.debug("Fetching active markets...")

        while True:
            try:
                response = self._client.get_markets(
                    status=TopicStatusFilter.ACTIVATED,
                    limit=page_size,
                    page=page
                )

                # Check for API errors
                if hasattr(response, 'errno') and response.errno != 0:
                    logger.error(f"API error fetching markets: {response.errmsg}")
                    break

                # Extract markets from response
                markets = []
                if hasattr(response, 'result'):
                    if hasattr(response.result, 'list'):
                        markets = response.result.list
                    elif hasattr(response.result, 'data'):
                        markets = response.result.data
                    else:
                        markets = response.result if isinstance(response.result, list) else []
                elif hasattr(response, 'data'):
                    markets = response.data
                else:
                    markets = response if isinstance(response, list) else []

                # Convert Pydantic models to dicts
                if markets:
                    converted_markets = []
                    for m in markets:
                        if hasattr(m, 'model_dump'):
                            market_dict = m.model_dump()
                        elif hasattr(m, 'dict'):
                            market_dict = m.dict()
                        else:
                            market_dict = m

                        # Normalize field names for universal interface
                        normalized_market = {
                            'market_id': str(market_dict.get('market_id', '')),
                            'title': market_dict.get('title', ''),
                            'yes_id': market_dict.get('yes_token_id', ''),
                            'no_id': market_dict.get('no_token_id', ''),
                            'close_time': market_dict.get('close_time', 0),
                            'status': market_dict.get('status', ''),
                            # Keep original data for backward compatibility
                            **market_dict
                        }

                        converted_markets.append(normalized_market)

                    markets = converted_markets

                if not markets:
                    break

                all_markets.extend(markets)
                logger.debug(f"Fetched page {page}: {len(markets)} markets")

                # Check if there are more pages
                if len(markets) < page_size:
                    break

                page += 1

            except Exception as e:
                logger.error(f"Error fetching markets page {page}: {e}")
                break

        logger.info(f"Fetched {len(all_markets)} active markets total")
        return all_markets

    def get_market(self, market_id: str) -> dict:
        """
        Fetch details for a specific market.

        Args:
            market_id: Market ID as string

        Returns:
            Market dictionary or empty dict if not found
        """
        try:
            response = self._client.get_market(market_id=int(market_id))

            if response.errno != 0:
                logger.error(f"API error fetching market {market_id}: {response.errmsg}")
                return {}

            # Extract market data
            result = response.result.data if response.result else None

            if not result:
                return {}

            # Convert Pydantic model to dict
            if hasattr(result, 'model_dump'):
                market_dict = result.model_dump()
            elif hasattr(result, 'dict'):
                market_dict = result.dict()
            elif isinstance(result, dict):
                market_dict = result
            else:
                return {}

            # Normalize field names
            normalized_market = {
                'market_id': str(market_dict.get('market_id', '')),
                'title': market_dict.get('title', ''),
                'yes_id': market_dict.get('yes_token_id', ''),
                'no_id': market_dict.get('no_token_id', ''),
                'close_time': market_dict.get('close_time', 0),
                'status': market_dict.get('status', ''),
                # Keep original data
                **market_dict
            }

            return normalized_market

        except Exception as e:
            logger.error(f"Error fetching market {market_id}: {e}")
            return {}

    def get_orderbook(self, market_id: str, outcome_side: str) -> dict:
        """
        Fetch orderbook for a specific market outcome.

        Args:
            market_id: Market ID as string
            outcome_side: "YES" or "NO"

        Returns:
            Orderbook dict with bids/asks lists (Decimal prices/sizes)
        """
        # Lookup token_id
        token_id = self._get_token_id(market_id, outcome_side)
        if not token_id:
            logger.error(f"Could not find token_id for market {market_id}, side {outcome_side}")
            return {'bids': [], 'asks': []}

        try:
            response = self._client.get_orderbook(token_id=token_id)

            if response.errno != 0:
                logger.error(f"API error fetching orderbook: {response.errmsg}")
                return {'bids': [], 'asks': []}

            if not response.result:
                return {'bids': [], 'asks': []}

            result = response.result

            # Convert Pydantic models to dicts with Decimal
            bids = []
            if hasattr(result, 'bids') and result.bids:
                for bid in result.bids:
                    if hasattr(bid, 'model_dump'):
                        bid_dict = bid.model_dump()
                    elif hasattr(bid, 'dict'):
                        bid_dict = bid.dict()
                    else:
                        bid_dict = bid

                    bids.append({
                        'price': Decimal(str(bid_dict.get('price', 0))),
                        'size': Decimal(str(bid_dict.get('size', 0)))
                    })

            asks = []
            if hasattr(result, 'asks') and result.asks:
                for ask in result.asks:
                    if hasattr(ask, 'model_dump'):
                        ask_dict = ask.model_dump()
                    elif hasattr(ask, 'dict'):
                        ask_dict = ask.dict()
                    else:
                        ask_dict = ask

                    asks.append({
                        'price': Decimal(str(ask_dict.get('price', 0))),
                        'size': Decimal(str(ask_dict.get('size', 0)))
                    })

            # CRITICAL: Sort orderbook to ensure correct best prices
            # bids: highest to lowest (descending)
            # asks: lowest to highest (ascending)
            if bids:
                bids.sort(key=lambda x: x['price'], reverse=True)
            if asks:
                asks.sort(key=lambda x: x['price'])

            # DEBUG: Log orderbook after sorting
            if bids and asks:
                logger.debug(f"📊 Orderbook sorted for market {market_id}, {outcome_side}")
                logger.debug(f"   Best bid: ${bids[0]['price']:.4f} (from {len(bids)} bids)")
                logger.debug(f"   Best ask: ${asks[0]['price']:.4f} (from {len(asks)} asks)")
                logger.debug(f"   Spread: ${asks[0]['price'] - bids[0]['price']:.4f}")

            return {
                'bids': bids,
                'asks': asks
            }

        except Exception as e:
            logger.error(f"Error fetching orderbook for market {market_id}: {e}")
            return {'bids': [], 'asks': []}

    # =========================================================================
    # ACCOUNT OPERATIONS (ABSTRACT METHODS)
    # =========================================================================

    def get_balance(self) -> Decimal:
        """
        Get available USDT balance.

        Returns:
            Decimal: Available USDT balance
        """
        try:
            response = self._client.get_my_balances()

            if response.errno != 0:
                logger.error(f"API error fetching balances: {response.errmsg}")
                return Decimal('0')

            if not response.result:
                return Decimal('0')

            result = response.result

            # Process balances list
            balances_list = getattr(result, 'balances', [])
            if not balances_list:
                return Decimal('0')

            # USDT token address on BSC
            USDT_ADDRESS = '0x55d398326f99059ff775485246999027b3197955'.lower()

            # Find USDT balance
            for token_balance in balances_list:
                token_address = getattr(token_balance, 'quote_token', None)
                if not token_address:
                    continue

                if token_address.lower() == USDT_ADDRESS:
                    available_str = getattr(token_balance, 'available_balance', '0')
                    decimals = getattr(token_balance, 'token_decimals', 18)

                    try:
                        balance_raw = float(available_str)

                        # SMART DETECTION: Check if value is already in USDT or in wei
                        if balance_raw < 1000:
                            return Decimal(str(balance_raw))
                        else:
                            # Large number - probably in smallest unit (wei)
                            return Decimal(str(balance_raw / (10 ** decimals)))
                    except (ValueError, TypeError):
                        return Decimal('0')

            # USDT not found
            logger.debug("USDT token not found in balances")
            return Decimal('0')

        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return Decimal('0')

    # =========================================================================
    # ORDER OPERATIONS (ABSTRACT METHODS)
    # =========================================================================

    def place_buy_order(
        self,
        market_id: str,
        outcome_side: str,
        price: Decimal,
        amount: Decimal
    ) -> dict:
        """
        Place a limit BUY order.

        Args:
            market_id: Market ID as string
            outcome_side: "YES" or "NO"
            price: Limit price (Decimal between 0.01 and 0.99)
            amount: Order size in USDT (Decimal)

        Returns:
            Order result dict {'order_id': str, 'status': str} or {} on failure
        """
        # Require trading mode
        self._require_trading_mode("place_buy_order")

        # Lookup token_id
        token_id = self._get_token_id(market_id, outcome_side)
        if not token_id:
            logger.error(f"Could not find token_id for market {market_id}, side {outcome_side}")
            return {}

        try:
            # Round price to 6 decimal places (API limit)
            price = round(float(price), 6)
            logger.info(f"Placing BUY order: {amount} USDT @ ${price:.4f}")

            order_input = PlaceOrderDataInput(
                marketId=int(market_id),
                tokenId=token_id,
                side=OrderSide.BUY,
                orderType=LIMIT_ORDER,
                price=str(price),
                makerAmountInQuoteToken=float(amount)
            )

            response = self._client.place_order(order_input, check_approval=False)

            if response.errno != 0:
                logger.error(f"Failed to place BUY order: {response.errmsg}")
                return {}

            if not response.result:
                logger.error("No result in place_order response")
                return {}

            result = response.result

            # Extract order_id from result.order_data
            order_id = None
            if hasattr(result, 'order_data') and result.order_data is not None:
                order_data = result.order_data

                if hasattr(order_data, 'order_id') and order_data.order_id:
                    order_id = str(order_data.order_id)
                elif hasattr(order_data, 'model_dump'):
                    try:
                        data_dict = order_data.model_dump()
                        if 'order_id' in data_dict and data_dict['order_id']:
                            order_id = str(data_dict['order_id'])
                    except Exception:
                        pass

            if order_id:
                logger.info(f"BUY order placed successfully: {order_id}")
                return {
                    'order_id': order_id,
                    'status': 'pending'
                }
            else:
                logger.warning("Order placed but could not extract order_id")
                return {}

        except BalanceNotEnough:
            logger.error("Insufficient USDT balance for order")
            return {}
        except InsufficientGasBalance:
            logger.error("Insufficient BNB for gas fees")
            return {}
        except Exception as e:
            logger.error(f"Error placing BUY order: {e}")
            return {}

    def place_sell_order(
        self,
        market_id: str,
        outcome_side: str,
        price: Decimal,
        amount: Decimal
    ) -> dict:
        """
        Place a limit SELL order.

        Args:
            market_id: Market ID as string
            outcome_side: "YES" or "NO"
            price: Limit price (Decimal between 0.01 and 0.99)
            amount: Number of shares to sell (Decimal)

        Returns:
            Order result dict {'order_id': str, 'status': str} or {} on failure
        """
        # Require trading mode
        self._require_trading_mode("place_sell_order")

        # Lookup token_id
        token_id = self._get_token_id(market_id, outcome_side)
        if not token_id:
            logger.error(f"Could not find token_id for market {market_id}, side {outcome_side}")
            return {}

        try:
            # Validation
            if amount <= 0:
                logger.error(f"❌ Cannot place SELL order with amount={amount}")
                return {}

            # Round price to 6 decimal places (API limit)
            price = round(float(price), 6)
            logger.info(f"Placing SELL order: {amount:.4f} tokens @ ${price:.4f}")

            # Floor to 1 decimal place to avoid API rounding errors
            import math
            adjusted_amount = math.floor(float(amount) * 10) / 10

            if adjusted_amount <= 0:
                logger.error(f"❌ Amount too small after rounding: {adjusted_amount:.4f}")
                return {}

            loss_from_rounding = float(amount) - adjusted_amount
            logger.debug(f"   Floored amount: {adjusted_amount:.1f} (loss: {loss_from_rounding:.4f})")

            order_input = PlaceOrderDataInput(
                marketId=int(market_id),
                tokenId=token_id,
                side=OrderSide.SELL,
                orderType=LIMIT_ORDER,
                price=str(price),
                makerAmountInBaseToken=adjusted_amount
            )

            response = self._client.place_order(order_input, check_approval=True)

            if response.errno != 0:
                logger.error(f"Failed to place SELL order: {response.errmsg}")
                return {}

            # Extract order_data
            result = response.result.order_data if response.result else None

            if result:
                if hasattr(result, 'model_dump'):
                    result_dict = result.model_dump()
                elif hasattr(result, 'dict'):
                    result_dict = result.dict()
                elif hasattr(result, '__dict__'):
                    result_dict = result.__dict__
                else:
                    result_dict = {}

                order_id = result_dict.get('order_id', 'unknown')
                logger.info(f"SELL order placed successfully: {order_id}")

                return {
                    'order_id': str(order_id),
                    'status': 'pending'
                }

            return {}

        except BalanceNotEnough:
            logger.error("Insufficient token balance for order")
            return {}
        except InsufficientGasBalance:
            logger.error("Insufficient BNB for gas fees")
            return {}
        except Exception as e:
            logger.error(f"Error placing SELL order: {e}")
            return {}

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an active order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully, False otherwise
        """
        try:
            logger.info(f"Cancelling order: {order_id}")

            response = self._client.cancel_order(order_id=order_id)

            if response.errno != 0:
                logger.error(f"Failed to cancel order: {response.errmsg}")
                return False

            logger.info(f"Order {order_id} cancelled successfully")
            return True

        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False

    def get_order(self, order_id: str) -> dict:
        """
        Get detailed status of an order.

        Args:
            order_id: Order ID to query

        Returns:
            Order status dict with standardized fields or {} if not found
        """
        try:
            response = self._client.get_order_by_id(order_id=order_id)

            if response.errno != 0:
                logger.error(f"API error fetching order {order_id}: {response.errmsg}")
                return {}

            # Extract order_data
            result = response.result.order_data if response.result else None

            if not result:
                return {}

            # Convert to dict
            if hasattr(result, 'model_dump'):
                order_dict = result.model_dump()
            elif hasattr(result, 'dict'):
                order_dict = result.dict()
            elif hasattr(result, '__dict__'):
                order_dict = result.__dict__
            else:
                order_dict = {}

            # Normalize status
            status_code = order_dict.get('status')
            normalized_status = self._normalize_status(status_code)

            # Extract fill data
            fill_data = self._extract_fill_data(order_dict)

            # Build standardized response
            return {
                'order_id': str(order_dict.get('order_id', order_id)),
                'status': normalized_status,
                'filled_amount': fill_data['filled_amount'],
                'avg_fill_price': fill_data['avg_fill_price'],
                'filled_usdt': fill_data['filled_usdt'],
                'trades': fill_data['trades'],
                # Keep original data for backward compatibility
                **order_dict
            }

        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {e}")
            return {}

    # =========================================================================
    # POSITION OPERATIONS (ABSTRACT METHODS)
    # =========================================================================

    def get_position_size(self, market_id: str, outcome_side: str) -> Decimal:
        """
        Get current position size (shares owned) for a market outcome.

        Args:
            market_id: Market ID as string
            outcome_side: "YES" or "NO"

        Returns:
            Decimal: Number of shares owned
        """
        try:
            response = self._client.get_my_positions(
                market_id=int(market_id),
                page=1,
                limit=50
            )

            if response.errno != 0:
                logger.warning(f"⚠️ get_my_positions failed: {response.errmsg}")
                return Decimal("0")

            positions = response.result.list

            logger.debug(f"🔍 Checking positions for market {market_id}, {outcome_side}")
            logger.debug(f"   Total positions: {len(positions)}")

            if len(positions) == 0:
                return Decimal("0")

            # Find matching position
            for pos in positions:
                pos_side = getattr(pos, 'outcome_side_enum', '').upper()
                if pos.market_id == int(market_id) and pos_side == outcome_side.upper():
                    shares = Decimal(str(pos.shares_owned))
                    logger.info(f"✅ Position found: {shares} {outcome_side} shares")
                    return shares

            logger.debug(f"No {outcome_side} position found in market {market_id}")
            return Decimal("0")

        except Exception as e:
            logger.error(f"❌ Error getting position size: {e}")
            return Decimal("0")

    def is_market_resolved(self, market_id: str) -> bool:
        """
        Check if a market has been resolved.

        Args:
            market_id: Market ID as string

        Returns:
            True if resolved, False otherwise
        """
        market = self.get_market(market_id)
        if not market:
            return False

        status = market.get('status', '')

        # Check for TopicStatus.RESOLVED enum value
        # Handle both string and numeric enum values
        if hasattr(TopicStatus, 'RESOLVED'):
            if status == TopicStatus.RESOLVED.value or status == TopicStatus.RESOLVED:
                return True

        # Fallback: check for string "RESOLVED"
        if isinstance(status, str) and status.upper() == 'RESOLVED':
            return True

        return False

    # =========================================================================
    # CLEANUP OPERATIONS (OVERRIDE BASE DEFAULT)
    # =========================================================================

    def cleanup_resolved_positions(self, market_id: str) -> None:
        """
        Redeem positions for a resolved market.

        Args:
            market_id: Market ID as string
        """
        # Require trading mode
        try:
            self._require_trading_mode("cleanup_resolved_positions")
        except RuntimeError as e:
            logger.warning(f"Cannot redeem positions: {e}")
            return

        try:
            logger.info(f"Redeeming positions for market {market_id}")

            tx_hash = self._client.redeem(market_id=int(market_id))

            logger.info(f"Redeemed successfully: {tx_hash.hex()}")

        except NoPositionsToRedeem:
            logger.info("No positions to redeem")
        except Exception as e:
            logger.error(f"Error redeeming positions: {e}")

    # =========================================================================
    # BACKWARD COMPATIBILITY METHODS (FOR EXISTING BOT CODE)
    # =========================================================================

    def get_all_active_markets(self) -> list[dict]:
        """Backward compatibility wrapper for get_active_markets()"""
        return self.get_active_markets()

    def get_market_orderbook(self, token_id: str) -> Optional[dict]:
        """
        Backward compatibility: Get orderbook by token_id directly.

        This is for legacy code that already has token_id.
        New code should use get_orderbook(market_id, outcome_side).
        """
        try:
            response = self._client.get_orderbook(token_id=token_id)

            if response.errno != 0:
                return None

            if not response.result:
                return None

            result = response.result

            # Convert to standard format (same as get_orderbook)
            bids = []
            if hasattr(result, 'bids') and result.bids:
                for bid in result.bids:
                    if hasattr(bid, 'model_dump'):
                        bid_dict = bid.model_dump()
                    elif hasattr(bid, 'dict'):
                        bid_dict = bid.dict()
                    else:
                        bid_dict = bid
                    bids.append(bid_dict)

            asks = []
            if hasattr(result, 'asks') and result.asks:
                for ask in result.asks:
                    if hasattr(ask, 'model_dump'):
                        ask_dict = ask.model_dump()
                    elif hasattr(ask, 'dict'):
                        ask_dict = ask.dict()
                    else:
                        ask_dict = ask
                    asks.append(ask_dict)

            # Sort orderbook
            def safe_price(order):
                if isinstance(order, dict):
                    return float(order.get('price', 0))
                elif hasattr(order, 'price'):
                    return float(order.price)
                return 0.0

            if bids:
                bids.sort(key=safe_price, reverse=True)
            if asks:
                asks.sort(key=safe_price)

            return {'bids': bids, 'asks': asks}

        except Exception as e:
            logger.error(f"Error fetching orderbook: {e}")
            return None

    def get_usdt_balance(self, include_frozen: bool = False) -> float:
        """Backward compatibility: Get balance as float"""
        balance_decimal = self.get_balance()
        return float(balance_decimal)

    def get_position_shares(self, market_id: int, outcome_side: str = "YES") -> Decimal:
        """Backward compatibility: Accept int market_id"""
        return self.get_position_size(str(market_id), outcome_side)

    def get_order_status(self, order_id: str) -> Optional[str]:
        """Backward compatibility: Get just status string"""
        order = self.get_order(order_id)
        if order:
            # Return uppercase status for backward compatibility
            return order.get('status', '').upper()
        return None

    def get_my_orders(
        self,
        market_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 20
    ) -> list[dict]:
        """Backward compatibility: Get orders list"""
        STATUS_CODE_MAP = {
            'PENDING': "1",
            'FINISHED': "2",
            'FILLED': "2",
            'CANCELLED': "3",
            'CANCELED': "3",
            'EXPIRED': "4",
            'FAILED': "5"
        }

        api_status = ""
        if status:
            status_upper = status.upper()
            if status_upper in STATUS_CODE_MAP:
                api_status = STATUS_CODE_MAP[status_upper]

        try:
            response = self._client.get_my_orders(
                market_id=market_id or 0,
                status=api_status,
                limit=min(limit, 20),
                page=1
            )

            if response.errno != 0:
                logger.error(f"API error fetching orders: {response.errmsg}")
                return []

            if not response.result or not hasattr(response.result, 'list'):
                return []

            orders = response.result.list
            if orders is None:
                return []

            # Convert to dicts
            converted_orders = []
            for order in orders:
                if hasattr(order, 'model_dump'):
                    order_dict = order.model_dump()
                elif hasattr(order, 'dict'):
                    order_dict = order.dict()
                elif isinstance(order, dict):
                    order_dict = order
                else:
                    continue

                # Add status_str for backward compatibility
                status_code = order_dict.get('status')
                if status_code is not None:
                    order_dict['status_str'] = self._normalize_status(status_code).upper()

                converted_orders.append(order_dict)

            return converted_orders

        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            return []

    def get_positions(self, market_id: Optional[int] = None) -> list[dict]:
        """Backward compatibility: Get positions list"""
        try:
            response = self._client.get_my_positions()

            if response.errno != 0:
                logger.error(f"API error fetching positions: {response.errmsg}")
                return []

            positions = []
            if hasattr(response, 'result') and response.result:
                result = response.result
                if hasattr(result, 'list'):
                    positions = result.list
                elif hasattr(result, 'data'):
                    positions = result.data
                elif hasattr(result, 'positions'):
                    positions = result.positions
                elif isinstance(result, list):
                    positions = result

            # Convert to dicts
            if positions:
                converted_positions = []
                for pos in positions:
                    if hasattr(pos, 'model_dump'):
                        converted_positions.append(pos.model_dump())
                    elif hasattr(pos, 'dict'):
                        converted_positions.append(pos.dict())
                    elif isinstance(pos, dict):
                        converted_positions.append(pos)
                    else:
                        converted_positions.append(pos)
                positions = converted_positions

            # Filter by market if specified
            if market_id is not None:
                positions = [p for p in positions if p.get('market_id') == market_id]

            return positions

        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    def get_balances(self) -> Optional[dict]:
        """
        Get all balances for the wallet.

        Returns:
            Balance dictionary with token addresses as keys, or None on error
        """
        try:
            response = self._client.get_my_balances()

            if response.errno != 0:
                logger.error(f"API error fetching balances: {response.errmsg}")
                return None

            if not response.result:
                logger.debug("No result in balance response")
                return None

            result = response.result

            # Extract balance data from Pydantic model
            balance_dict = {
                'wallet_address': getattr(result, 'wallet_address', None),
                'multi_sign_address': getattr(result, 'multi_sign_address', None),
                'chain_id': getattr(result, 'chain_id', None),
                'tokens': {}
            }

            # Process balances list
            balances_list = getattr(result, 'balances', [])
            if not balances_list:
                logger.debug("No balances in response")
                return balance_dict

            # Convert each token balance to dict
            for token_balance in balances_list:
                token_address = getattr(token_balance, 'quote_token', None)
                if not token_address:
                    continue

                balance_dict['tokens'][token_address.lower()] = {
                    'available': getattr(token_balance, 'available_balance', '0'),
                    'frozen': getattr(token_balance, 'frozen_balance', '0'),
                    'total': getattr(token_balance, 'total_balance', '0'),
                    'decimals': getattr(token_balance, 'token_decimals', 18)
                }

            logger.debug(f"Parsed {len(balance_dict['tokens'])} token balances")
            return balance_dict

        except Exception as e:
            logger.error(f"Error fetching balances: {e}")
            return None

    def get_token_balance(self, token_id: str) -> float:
        """
        Get available balance of a specific token (YES/NO shares).

        Args:
            token_id: Token ID (long hex string identifying the token)

        Returns:
            Token balance as float (in human-readable units, not wei)
        """
        balances = self.get_balances()

        if not balances or 'tokens' not in balances:
            logger.debug("No balance data returned from get_balances()")
            return 0.0

        tokens = balances['tokens']

        # Token IDs in response are lowercase
        token_id_lower = token_id.lower()

        if token_id_lower not in tokens:
            logger.debug(f"Token {token_id[:20]}... not found in balances")
            return 0.0

        token_data = tokens[token_id_lower]
        available_balance_str = token_data.get('available', '0')
        decimals = token_data.get('decimals', 18)

        try:
            balance_raw = float(available_balance_str)

            # SMART DETECTION: Check if value is already in human-readable format or wei
            if balance_raw < 1e10:  # Less than 10 billion = probably human-readable
                return balance_raw
            else:
                # Very large number - probably in wei
                return balance_raw / (10 ** decimals)

        except (ValueError, TypeError) as e:
            logger.error(f"Error converting token balance '{available_balance_str}': {e}")
            return 0.0

    def get_best_prices(self, token_id: str) -> Optional[tuple[float, float]]:
        """
        Get best bid and ask prices for a token.

        Args:
            token_id: The token ID

        Returns:
            Tuple of (best_bid, best_ask) or None if orderbook empty
        """
        orderbook = self.get_market_orderbook(token_id)

        if not orderbook:
            return None

        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])

        if not bids or not asks:
            return None

        best_bid = safe_float(bids[0].get('price', 0))
        best_ask = safe_float(asks[0].get('price', 0))

        return (best_bid, best_ask)

    def get_significant_positions(
        self,
        market_id: Optional[int] = None,
        min_shares: float = 5.0
    ) -> list[dict]:
        """
        Get positions with at least min_shares tokens.

        Filters out dust positions that are too small to be worth selling.

        Args:
            market_id: Optional market ID to filter by
            min_shares: Minimum shares to consider significant (default: 5.0)

        Returns:
            List of position dictionaries with shares_owned >= min_shares
        """
        all_positions = self.get_positions(market_id=market_id)

        if not all_positions:
            return []

        significant = []
        dust_count = 0

        for pos in all_positions:
            shares = float(pos.get('shares_owned', 0))

            if shares < min_shares:
                dust_count += 1
                continue

            significant.append(pos)

        if dust_count > 0:
            logger.debug(
                f"Filtered {dust_count} dust position(s) "
                f"(< {min_shares} shares) from {len(all_positions)} total"
            )

        return significant

    def redeem_positions(self, market_id: int) -> Optional[str]:
        """
        Redeem positions for a resolved market.

        Args:
            market_id: The resolved market ID

        Returns:
            Transaction hash or None on failure
        """
        # Require trading mode for blockchain operations
        try:
            self._require_trading_mode("redeem_positions")
        except RuntimeError as e:
            logger.warning(f"Cannot redeem positions: {e}")
            return None

        try:
            logger.info(f"Redeeming positions for market {market_id}")

            tx_hash = self._client.redeem(market_id=market_id)

            logger.info(f"Redeemed successfully: {tx_hash.hex()}")
            return tx_hash.hex()

        except NoPositionsToRedeem:
            logger.info("No positions to redeem")
            return None
        except Exception as e:
            logger.error(f"Error redeeming positions: {e}")
            return None

    def get_raw_client(self) -> Client:
        """Get underlying SDK client for advanced operations"""
        return self._client
