"""
Opinion Farming Bot - API Client Module
=======================================

Wrapper around the Opinion CLOB SDK with helper methods.
Provides a clean interface for all Opinion.trade API operations.

This module handles:
- Client initialization
- Market data fetching
- Order operations
- Balance checks
- Error handling and retries
"""

import time
from typing import Optional, Any
from decimal import Decimal


# === SSL CERTIFICATE FIX ===
# Opinion.trade proxy uses self-signed certificate
# Disable SSL verification to avoid connection errors
import ssl
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Monkey patch to disable SSL verification globally
import certifi
import os
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['REQUESTS_CA_BUNDLE'] = ''
os.environ['CURL_CA_BUNDLE'] = ''

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
from config import (
    API_HOST,
    API_KEY,
    PRIVATE_KEY,
    MULTI_SIG_ADDRESS,
    CHAIN_ID,
    RPC_URL
)
from logger_config import setup_logger
from utils import safe_float, safe_int, wei_to_usdt_float



# Initialize logger
logger = setup_logger(__name__)


class OpinionClient:
    """
    Wrapper class for Opinion.trade CLOB SDK.
    
    Provides simplified methods for common operations with
    built-in error handling and logging.
    
    Usage:
        client = OpinionClient()
        markets = client.get_all_active_markets()
        orderbook = client.get_market_orderbook(market_id)
    """
    
    def __init__(self):
        """
        Initialize the Opinion client with credentials from config.
        
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
        
        logger.debug("Initializing Opinion client...")
        
        # Create the underlying SDK client
        # Build parameters (multi_sig_addr is optional for regular wallets)
        client_params = {
            'host': API_HOST,
            'apikey': API_KEY,
            'chain_id': CHAIN_ID,
            'private_key': PRIVATE_KEY,
            'rpc_url': RPC_URL
        }
        
        # Only add multi_sig_addr if using Gnosis Safe or similar
        if MULTI_SIG_ADDRESS:
            logger.debug(f"Using multi-sig address: {MULTI_SIG_ADDRESS}")
            client_params['multi_sig_addr'] = MULTI_SIG_ADDRESS
        else:
            logger.debug("Using standard wallet (address derived from private_key)")
        
        self._client = Client(**client_params)
        
        logger.info("Opinion client initialized successfully")
    
    # =========================================================================
    # MARKET DATA METHODS
    # =========================================================================
    
    def _require_trading_mode(self, operation: str):
        """
        Check if trading operations are available.
        Raises error if running in read-only mode.
        
        Args:
            operation: Name of operation being attempted
            
        Raises:
            RuntimeError: If MULTI_SIG_ADDRESS not configured
        """
        if self._read_only_mode:
            raise RuntimeError(
                f"Cannot perform '{operation}' - bot is in READ-ONLY mode. "
                f"Set MULTI_SIG_ADDRESS in .env to enable trading operations."
            )
    
    def get_all_active_markets(self) -> list[dict]:
        """
        Fetch all active (ACTIVATED) markets with pagination.
        
        Returns:
            List of market dictionaries
            
        Example:
            >>> client = OpinionClient()
            >>> markets = client.get_all_active_markets()
            >>> print(f"Found {len(markets)} active markets")
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
                '''
                # Debug: sprawdź strukturę odpowiedzi
                print(f"\n{'='*60}")
                print(f"DEBUG: Response type: {type(response)}")
                print(f"DEBUG: Response dir: {dir(response)}")
                print(f"DEBUG: Response value: {response}")
                print(f"{'='*60}\n")
                '''
                
                # Check for API errors
                if hasattr(response, 'errno') and response.errno != 0:
                    logger.error(f"API error fetching markets: {response.errmsg}")
                    break
                
                # Try different possible structures
                if hasattr(response, 'result'):
                    # Check for response.result.list (OpenapiMarketListRespOpenAPI)
                    if hasattr(response.result, 'list'):
                        markets = response.result.list
                    # Fallback to response.result.data
                    elif hasattr(response.result, 'data'):
                        markets = response.result.data
                    # result might be the list directly
                    else:
                        markets = response.result if isinstance(response.result, list) else []
                elif hasattr(response, 'data'):
                    markets = response.data
                else:
                    # response might be the list directly
                    markets = response if isinstance(response, list) else []
                
                # Convert Pydantic models to dicts for compatibility with rest of code
                if markets:
                    converted_markets = []
                    for m in markets:
                        if hasattr(m, 'model_dump'):
                            # Pydantic v2
                            converted_markets.append(m.model_dump())
                        elif hasattr(m, 'dict'):
                            # Pydantic v1
                            converted_markets.append(m.dict())
                        else:
                            # Already a dict or other type
                            converted_markets.append(m)
                    markets = converted_markets
                
                '''
                print(f"DEBUG: Markets type: {type(markets)}, count: {len(markets) if markets else 0}")
                if markets:
                    print(f"DEBUG: First market sample: {markets[0] if isinstance(markets, list) else 'Not a list'}")
                '''
                logger.debug(f"Markets type: {type(markets)}, count: {len(markets) if markets else 0}")
                
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
    
    def get_market(self, market_id: int) -> Optional[dict]:
        """
        Fetch details for a specific market.
        
        Args:
            market_id: The market ID
            
        Returns:
            Market dictionary or None if not found
        """
        try:
            response = self._client.get_market(market_id=market_id)
            
            if response.errno != 0:
                logger.error(f"API error fetching market {market_id}: {response.errmsg}")
                return None
            
            # Extract market data
            result = response.result.data if response.result else None
            
            if not result:
                return None
            
            # Convert Pydantic model to dict for easier use
            if hasattr(result, 'model_dump'):
                return result.model_dump()
            elif hasattr(result, 'dict'):
                return result.dict()
            elif isinstance(result, dict):
                return result
            else:
                # Fallback: return as-is (will require attribute access)
                return result
            
        except Exception as e:
            logger.error(f"Error fetching market {market_id}: {e}")
            return None
    
    def get_market_orderbook(self, token_id: str) -> Optional[dict]:
        """
        Fetch orderbook for a specific token.
        
        Args:
            token_id: The token ID (yes_token_id or no_token_id)
            
        Returns:
            Orderbook dictionary with 'bids' and 'asks' lists, or None on error
            
        Example:
            >>> orderbook = client.get_market_orderbook(yes_token_id)
            >>> best_bid = float(orderbook['bids'][0]['price'])
        """
        try:
            response = self._client.get_orderbook(token_id=token_id)
            
            if response.errno != 0:
                logger.error(f"API error fetching orderbook: {response.errmsg}")
                return None
            
            if not response.result:
                return None
            
            # Extract bids and asks from response.result
            result = response.result
            
            # Convert Pydantic models to dicts
            bids = []
            if hasattr(result, 'bids') and result.bids:
                for bid in result.bids:
                    if hasattr(bid, 'model_dump'):
                        bids.append(bid.model_dump())
                    elif hasattr(bid, 'dict'):
                        bids.append(bid.dict())
                    else:
                        bids.append(bid)
            
            asks = []
            if hasattr(result, 'asks') and result.asks:
                for ask in result.asks:
                    if hasattr(ask, 'model_dump'):
                        asks.append(ask.model_dump())
                    elif hasattr(ask, 'dict'):
                        asks.append(ask.dict())
                    else:
                        asks.append(ask)

            # CRITICAL FIX: Sort orderbook to ensure correct best prices
            # bids: highest to lowest (descending)
            # asks: lowest to highest (ascending)
            # This ensures bids[0] = best bid, asks[0] = best ask
            def safe_price(order):
                """Extract price safely from order dict/object."""
                if isinstance(order, dict):
                    return float(order.get('price', 0))
                elif hasattr(order, 'price'):
                    return float(order.price)
                return 0.0

            if bids:
                bids.sort(key=safe_price, reverse=True)  # Descending
            if asks:
                asks.sort(key=safe_price)  # Ascending

            # DEBUG: Log orderbook after sorting for verification
            if bids and asks:
                logger.debug(f"📊 Orderbook sorted for token {token_id[:20]}...")
                logger.debug(f"   Best bid: ${safe_price(bids[0]):.4f} (from {len(bids)} bids)")
                logger.debug(f"   Best ask: ${safe_price(asks[0]):.4f} (from {len(asks)} asks)")
                logger.debug(f"   Spread: ${safe_price(asks[0]) - safe_price(bids[0]):.4f}")

            return {
                'bids': bids,
                'asks': asks
            }
            
        except Exception as e:
            # DEFENSIVE: Handle both string and int token_id (prevent crash on slice)
            if not token_id:
                token_display = "None"
            elif isinstance(token_id, int):
                token_display = f"<int:{token_id}>"  # Show wrong type for debugging
            else:
                # String - safe to slice
                token_str = str(token_id)
                token_display = token_str[:20] + "..." if len(token_str) > 20 else token_str
            logger.error(f"Error fetching orderbook for token {token_display}: {e}")
            return None
    
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
    
    # =========================================================================
    # ORDER METHODS
    # =========================================================================
    
    def place_buy_order(
        self,
        market_id: int,
        token_id: str,
        price: float,
        amount_usdt: float,
        check_approval: bool = True
    ) -> Optional[dict]:
        """
        Place a limit BUY order.
        ...
        """
        # Require trading mode for order placement
        self._require_trading_mode("place_buy_order")
        
        try:
            logger.info(f"Placing BUY order: {amount_usdt} USDT @ ${price:.4f}")
            
            order_input = PlaceOrderDataInput(
                marketId=market_id,
                tokenId=token_id,
                side=OrderSide.BUY,
                orderType=LIMIT_ORDER,
                price=str(price),
                makerAmountInQuoteToken=amount_usdt
            )
            
            response = self._client.place_order(order_input, check_approval=False)

            if response.errno != 0:
                logger.error(f"Failed to place BUY order: {response.errmsg}")
                return None

            # Extract result from response
            if not response.result:
                logger.error("No result in place_order response")
                return None

            result = response.result                      
            
            # Extract order_id from result.order_data
            order_id = None
            
            # V2AddOrderResp has structure: result.order_data.order_id
            if hasattr(result, 'order_data') and result.order_data is not None:
                order_data = result.order_data
                
                # Try direct attribute access first
                if hasattr(order_data, 'order_id') and order_data.order_id:
                    order_id = str(order_data.order_id)
                    logger.debug(f"Extracted order_id from result.order_data.order_id: {order_id}")
                
                # Fallback: try model_dump() if direct access fails
                elif hasattr(order_data, 'model_dump'):
                    try:
                        data_dict = order_data.model_dump()
                        if 'order_id' in data_dict and data_dict['order_id']:
                            order_id = str(data_dict['order_id'])
                            logger.debug(f"Extracted order_id from model_dump(): {order_id}")
                    except Exception as e:
                        logger.debug(f"model_dump() failed: {e}")
            
            if order_id:
                logger.info(f"BUY order placed successfully: {order_id}")
            else:
                logger.warning("Order placed but could not extract order_id")
                logger.warning(f"Response structure: {type(result)}")
                if hasattr(result, 'order_data'):
                    logger.warning(f"order_data type: {type(result.order_data)}")
            
            # Convert to dict for return
            if hasattr(result, 'model_dump'):
                result_dict = result.model_dump()
            elif hasattr(result, 'dict'):
                result_dict = result.dict()
            elif hasattr(result, '__dict__'):
                result_dict = result.__dict__
            else:
                result_dict = {'order_id': order_id} if order_id else {}
            
            # Ensure order_id is in the dict
            if order_id and 'order_id' not in result_dict:
                result_dict['order_id'] = order_id
            
            return result_dict
            
        except BalanceNotEnough:
            logger.error("Insufficient USDT balance for order")
            return None
        except InsufficientGasBalance:
            logger.error("Insufficient BNB for gas fees")
            return None
        except Exception as e:
            logger.error(f"Error placing BUY order: {e}")
            return None
    
    def place_sell_order(
        self,
        market_id: int,
        token_id: str,
        price: float,
        amount_tokens: float,
        check_approval: bool = True
    ) -> Optional[dict]:
        """
        Place a limit SELL order.
        
        Args:
            market_id: Market ID
            token_id: Token ID to sell
            price: Limit price per token
            amount_tokens: Amount of tokens to sell
            check_approval: Whether to check/request token approval
            
        Returns:
            Order result dictionary with order_id, or None on failure
        """
        try:
            # VALIDATION: Don't allow 0 or negative amounts
            if amount_tokens <= 0:
                logger.error(f"❌ Cannot place SELL order with amount={amount_tokens}")
                logger.error(f"   This indicates position balance check failed")
                logger.error(f"   Check get_position_shares() and filled_amount logs above")
                return None
            
            logger.info(f"Placing SELL order: {amount_tokens:.4f} tokens @ ${price:.4f}")

            # CRITICAL FIX: Floor to 1 decimal place to avoid API rounding errors
            # API rounds to 1 decimal during validation, causing errors like:
            # - We send: 163.78 (163.79 - 0.01)
            # - API validates: 163.8 (rounds 163.78 up!)
            # - Error: "Insufficient token balance: 163.8 required, but only 163.79 available"
            #
            # Solution: Floor to 1 decimal place BEFORE sending to API
            # - 163.79 → 163.7 (API validates 163.7 < 163.79 ✓)
            # - 100.15 → 100.1 (API validates 100.1 < 100.15 ✓)
            import math
            adjusted_amount = math.floor(amount_tokens * 10) / 10

            # Ensure we don't go to zero
            if adjusted_amount <= 0:
                logger.error(f"❌ Amount too small after rounding: floor({amount_tokens:.4f} * 10) / 10 = {adjusted_amount:.4f}")
                logger.error(f"   Cannot place SELL order with amount <= 0")
                return None

            loss_from_rounding = amount_tokens - adjusted_amount
            logger.debug(f"   Floored amount for API safety: {adjusted_amount:.1f} (original: {amount_tokens:.4f}, loss: {loss_from_rounding:.4f})")

            order_input = PlaceOrderDataInput(
                marketId=market_id,
                tokenId=token_id,
                side=OrderSide.SELL,
                orderType=LIMIT_ORDER,
                price=str(price),
                makerAmountInBaseToken=adjusted_amount
            )
            
            response = self._client.place_order(order_input, check_approval=check_approval)
            
            if response.errno != 0:
                logger.error(f"Failed to place SELL order: {response.errmsg}")
                return None
            
            # Extract order_data from response (not 'data', but 'order_data')
            result = response.result.order_data if response.result else None
            
            # Convert to dict and extract order_id
            if result:
                if hasattr(result, 'model_dump'):
                    result_dict = result.model_dump()
                elif hasattr(result, 'dict'):
                    result_dict = result.dict()
                elif hasattr(result, '__dict__'):
                    result_dict = result.__dict__
                else:
                    result_dict = {}
                
                # Extract order_id
                order_id = result_dict.get('order_id', 'unknown')
                logger.info(f"SELL order placed successfully: {order_id}")
                
                return result_dict
            
            return None
            
        except BalanceNotEnough:
            logger.error("Insufficient token balance for order")
            return None
        except InsufficientGasBalance:
            logger.error("Insufficient BNB for gas fees")
            return None
        except Exception as e:
            logger.error(f"Error placing SELL order: {e}")
            return None
    
    def get_order(self, order_id: str) -> Optional[dict]:
        """
        Get order details by order ID.
        
        Args:
            order_id: The order ID to look up
            
        Returns:
            Order dictionary or None if not found
        """
        try:
            response = self._client.get_order_by_id(order_id=order_id)
            
            if response.errno != 0:
                logger.error(f"API error fetching order {order_id}: {response.errmsg}")
                return None
            
            # Extract order_data from response (not 'data', but 'order_data')
            result = response.result.order_data if response.result else None
            
            # Convert Pydantic model to dict for easier access
            if result:
                if hasattr(result, 'model_dump'):
                    return result.model_dump()
                elif hasattr(result, 'dict'):
                    return result.dict()
                elif hasattr(result, '__dict__'):
                    return result.__dict__
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {e}")
            return None
    
    def get_order_status(self, order_id: str) -> Optional[str]:
        """
        Get just the status of an order.
        
        Args:
            order_id: The order ID
            
        Returns:
            Status string (e.g., 'PENDING', 'FILLED', 'CANCELLED') or None
            
        Note:
            API returns status as numeric enum:
            0 = PENDING
            1 = FILLED
            2 = PARTIALLY_FILLED
            3 = CANCELLED
        """
        # Status code to string mapping
        STATUS_MAP = {
            0: 'PENDING',
            1: 'FILLED',
            2: 'PARTIALLY_FILLED',
            3: 'CANCELLED'
        }
        
        order = self.get_order(order_id)
        if order:
            status_code = order.get('status')
            if status_code is not None:
                return STATUS_MAP.get(status_code, f'UNKNOWN({status_code})')
        return None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an active order.
        
        Args:
            order_id: The order ID to cancel
            
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

    def get_my_orders(
        self,
        market_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 20
    ) -> list[dict]:
        # Map our status strings to API status codes (as STRINGS!)
        # SDK expects string representation of numbers: "0", "1", "2", "3"
        STATUS_CODE_MAP = {
            'PENDING': "0",
            'OPEN': "0",
            'FILLED': "1",
            'PARTIALLY_FILLED': "2",
            'CANCELLED': "3"
        }

        # Convert status to API format (string number or empty string)
        api_status = ""  # Default: all statuses
        if status:
            status_upper = status.upper()
            if status_upper in STATUS_CODE_MAP:
                api_status = STATUS_CODE_MAP[status_upper]
            else:
                logger.warning(f"Unknown status '{status}', fetching all orders")
                api_status = ""
                
        logger.debug(f"Fetching orders: market_id={market_id or 0}, status='{api_status}', limit={limit}")
        
        logger.debug(f"Fetching orders: market_id={market_id or 0}, status='{api_status}', limit={limit}")
        
        try:
            # Call SDK method
            response = self._client.get_my_orders(
                market_id=market_id or 0,
                status=api_status,  # ← Już jest int albo ""
                limit=min(limit, 20),
                page=1
            )
            
            if response.errno != 0:
                logger.error(f"API error fetching orders: {response.errmsg}")
                return []
            
            # Extract orders from response
            if not response.result or not hasattr(response.result, 'list'):
                logger.debug("No orders in response")
                return []
            
            orders = response.result.list
            
            # Convert Pydantic models to dicts
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
                
                # Convert numeric status to string for consistency
                status_code = order_dict.get('status')
                if status_code is not None:
                    STATUS_MAP = {
                        0: 'PENDING',
                        1: 'FILLED',
                        2: 'PARTIALLY_FILLED',
                        3: 'CANCELLED'
                    }
                    order_dict['status_str'] = STATUS_MAP.get(status_code, f'UNKNOWN({status_code})')
                
                converted_orders.append(order_dict)
            
            logger.debug(f"Fetched {len(converted_orders)} orders")
            return converted_orders
            
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            return []
    
    # =========================================================================
    # BALANCE METHODS
    # =========================================================================
    
    def get_balances(self) -> Optional[dict]:
        """
        Get all balances for the wallet.
        
        Returns:
            Balance dictionary with token addresses as keys, or None on error
            Example: {
                'wallet_address': '0x707f...',
                'multi_sign_address': '0x756a...',
                'tokens': {
                    '0x55d398...': {
                        'available': '11',
                        'frozen': '0',
                        'total': '11',
                        'decimals': 18
                    }
                }
            }
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
    
    def get_usdt_balance(self) -> float:
        """
        Get available USDT balance.
        
        Returns:
            USDT balance as float in USDT
        """
        balances = self.get_balances()
        
        if not balances or 'tokens' not in balances:
            logger.debug("No balance data returned from get_balances()")
            return 0.0
        
        # USDT token address on BSC
        USDT_ADDRESS = '0x55d398326f99059ff775485246999027b3197955'.lower()
        
        tokens = balances['tokens']
        
        if USDT_ADDRESS not in tokens:
            logger.debug(f"USDT token not found. Available tokens: {list(tokens.keys())}")
            return 0.0
        
        usdt_data = tokens[USDT_ADDRESS]
        available_balance_str = usdt_data.get('available', '0')
        decimals = usdt_data.get('decimals', 18)
        
        try:
            # Convert string to float
            balance_raw = float(available_balance_str)
            
            # SMART DETECTION: Check if value is already in USDT or in wei
            # If balance_raw < 1000, it's likely already in USDT (not smallest unit)
            # Example: '11' = 11 USDT (not 0.000000000000000011 USDT)
            if balance_raw < 1000:
                # Likely already in USDT
                balance_usdt = balance_raw
                logger.debug(f"Balance appears to be in USDT already: {balance_usdt:.2f} USDT")
            else:
                # Large number - probably in smallest unit (wei)
                balance_usdt = balance_raw / (10 ** decimals)
                logger.debug(f"Converted from wei ({balance_raw}) to {balance_usdt:.6f} USDT")
            
            return balance_usdt
            
        except (ValueError, TypeError) as e:
            logger.error(f"Error converting USDT balance '{available_balance_str}': {e}")
            return 0.0
    
    def get_token_balance(self, token_id: str) -> float:
        """
        Get available balance of a specific token (YES/NO shares).
        
        Args:
            token_id: Token ID (long hex string identifying the token)
            
        Returns:
            Token balance as float (in human-readable units, not wei)
            
        Example:
            >>> client = OpinionClient()
            >>> balance = client.get_token_balance("113022332768771453...")
            >>> balance
            19.931363869468953546
        """
        balances = self.get_balances()
        
        if not balances or 'tokens' not in balances:
            logger.debug("No balance data returned from get_balances()")
            return 0.0
        
        tokens = balances['tokens']
        
        # Token IDs in response are lowercase
        token_id_lower = token_id.lower()
        
        if token_id_lower not in tokens:
            # Token not found - user probably doesn't own any
            logger.debug(f"Token {token_id[:20]}... not found in balances")
            logger.debug(f"Available tokens: {len(tokens)} total")
            return 0.0
        
        token_data = tokens[token_id_lower]
        available_balance_str = token_data.get('available', '0')
        decimals = token_data.get('decimals', 18)
        
        try:
            # Convert string to float
            balance_raw = float(available_balance_str)
            
            # SMART DETECTION: Check if value is already in human-readable format or wei
            # Opinion.trade typically returns token balances in human-readable format
            # (e.g., "19.931" not "19931000000000000000")
            if balance_raw < 1e10:  # Less than 10 billion = probably human-readable
                balance_tokens = balance_raw
                logger.debug(f"Token balance appears to be in human format: {balance_tokens:.10f}")
            else:
                # Very large number - probably in wei
                balance_tokens = balance_raw / (10 ** decimals)
                logger.debug(f"Converted from wei ({balance_raw}) to {balance_tokens:.10f} tokens")
            
            return balance_tokens
            
        except (ValueError, TypeError) as e:
            logger.error(f"Error converting token balance '{available_balance_str}': {e}")
            return 0.0
    
    # =========================================================================
    # POSITION METHODS
    # =========================================================================
    
    def get_positions(self, market_id: Optional[int] = None) -> list[dict]:
        """
        Get all positions, optionally filtered by market.

        Args:
            market_id: Optional market ID to filter by

        Returns:
            List of position dictionaries
        """
        try:
            response = self._client.get_my_positions()

            if response.errno != 0:
                logger.error(f"API error fetching positions: {response.errmsg}")
                return []

            # Try different possible response structures
            positions = []

            if hasattr(response, 'result') and response.result:
                result = response.result

                # Try result.list (similar to markets endpoint)
                if hasattr(result, 'list'):
                    positions = result.list
                # Try result.data
                elif hasattr(result, 'data'):
                    positions = result.data
                # Try result.positions
                elif hasattr(result, 'positions'):
                    positions = result.positions
                # result might be the list directly
                elif isinstance(result, list):
                    positions = result
                else:
                    # Try to convert Pydantic model to dict and extract positions
                    if hasattr(result, 'model_dump'):
                        result_dict = result.model_dump()
                    elif hasattr(result, 'dict'):
                        result_dict = result.dict()
                    elif hasattr(result, '__dict__'):
                        result_dict = result.__dict__
                    else:
                        result_dict = {}

                    # Look for positions in any key
                    for key in ['list', 'data', 'positions', 'items']:
                        if key in result_dict:
                            positions = result_dict[key]
                            break

            # Convert Pydantic models to dicts
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

            logger.debug(f"Fetched {len(positions)} positions")

            # Filter by market if specified
            if market_id is not None:
                positions = [p for p in positions if p.get('market_id') == market_id]
                logger.debug(f"Filtered to {len(positions)} positions for market {market_id}")

            return positions

        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            logger.debug(f"Exception details: {type(e).__name__}: {str(e)}")
            return []

    def get_significant_positions(
        self,
        market_id: Optional[int] = None,
        min_shares: float = 5.0
    ) -> list[dict]:
        """
        Get positions with at least min_shares tokens.

        Filters out dust positions that are too small to be worth selling.
        Dust positions will be accumulated and sold with future positions on same market.

        Args:
            market_id: Optional market ID to filter by
            min_shares: Minimum shares to consider significant (default: 5.0)

        Returns:
            List of position dictionaries with shares_owned >= min_shares

        Example:
            >>> client = OpinionClient()
            >>> positions = client.get_significant_positions(min_shares=5.0)
            >>> # Returns only positions with >= 5.0 shares (worth selling)
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
        self._require_trading_mode("redeem_positions")
        
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
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def is_market_resolved(self, market_id: int) -> bool:
        """
        Check if a market has been resolved.
        
        Args:
            market_id: The market ID to check
            
        Returns:
            True if resolved, False otherwise
        """
        market = self.get_market(market_id)
        if not market:
            return False
        
        status = market.get('status', '')
        return status == TopicStatus.RESOLVED.value
    
    def get_raw_client(self) -> Client:
        """
        Get the underlying SDK client for advanced operations.
        
        Returns:
            The raw Client instance
        """
        return self._client
    
    def get_position_shares(self, market_id: int, outcome_side: str = "YES") -> Decimal:
        """
        Get shares owned in specific position using get_my_positions()
        
        IMPORTANT: Shares (YES/NO tokens) are NOT in balance endpoints!
        They must be retrieved from get_my_positions() which returns PositionData
        with shares_owned field.
        
        Args:
            market_id: Market ID to check position for
            outcome_side: "YES" or "NO" (default: "YES")
        
        Returns:
            Decimal: Number of shares owned in this position, or 0 if no position found
            
        Example:
            >>> client = OpinionClient()
            >>> shares = client.get_position_shares(market_id=1546, outcome_side="YES")
            >>> print(f"You own {shares} YES tokens")
        """
        try:
            # Call get_my_positions - this returns ALL positions by default
            # We could filter by market_id in API call, but API uses pagination
            # so it's safer to get all and filter in code
            response = self._client.get_my_positions(
                market_id=market_id,  # Filter to specific market
                page=1,
                limit=50  # Should be enough for single market
            )
            
            if response.errno != 0:
                logger.warning(f"⚠️ get_my_positions failed: {response.errmsg}")
                return Decimal("0")
            
             # Get positions list from response
            positions = response.result.list
            
            # ENHANCED DEBUGGING
            logger.info(f"🔍 Checking positions for market {market_id}, looking for {outcome_side} side")
            logger.info(f"   Total positions returned: {len(positions)}")
            
            if len(positions) == 0:
                logger.warning(f"⚠️ API returned 0 positions for market {market_id}!")
                logger.warning(f"   This may indicate timing issue - order just filled?")
                return Decimal("0")
            
            # Find position matching market_id and outcome_side
            for i, pos in enumerate(positions):
                # Log every position for debugging
                logger.info(f"   Position {i+1}:")
                logger.info(f"      market_id: {pos.market_id}")
                logger.info(f"      outcome_side_enum: {getattr(pos, 'outcome_side_enum', 'MISSING')}")
                logger.info(f"      shares_owned: {getattr(pos, 'shares_owned', 'MISSING')}")
                
                # Check both market_id and outcome_side match
                # IMPORTANT: Case-insensitive comparison (API returns "Yes" but we search "YES")
                pos_side = getattr(pos, 'outcome_side_enum', '').upper()
                if pos.market_id == market_id and pos_side == outcome_side.upper():
                    shares = Decimal(str(pos.shares_owned))
                    logger.info(f"✅ Position found: {shares} {outcome_side} shares in market {market_id}")
                    return shares
            
            # No matching position found
            logger.debug(f"No {outcome_side} position found in market {market_id}")
            return Decimal("0")
            
        except Exception as e:
            logger.error(f"❌ Error getting position shares: {e}")
            logger.debug(f"Exception details: {type(e).__name__}: {str(e)}")
            return Decimal("0")

    def cleanup_resolved_positions(self) -> int:
        """
        Find and redeem all positions from resolved markets.
        
        Returns:
            Number of markets redeemed
            
        Example:
            >>> client = OpinionClient()
            >>> count = client.cleanup_resolved_positions()
            >>> print(f"Redeemed {count} resolved markets")
        """
        try:
            # Get all positions
            positions = self.get_positions()
            
            if not positions:
                logger.debug("No positions to cleanup")
                return 0
            
            # Track resolved markets
            resolved_markets = set()
            
            for pos in positions:
                market_id = pos.get('market_id')
                shares = float(pos.get('shares_owned', 0))
                
                if shares <= 0:
                    continue  # Skip empty positions
                
                # Check if market is resolved
                if self.is_market_resolved(market_id):
                    resolved_markets.add(market_id)
            
            if not resolved_markets:
                logger.info("✅ No resolved positions to cleanup")
                return 0
            
            logger.info(f"🔍 Found {len(resolved_markets)} resolved markets with positions")
            
            # Redeem each market
            redeemed_count = 0
            for market_id in resolved_markets:
                logger.info(f"💰 Attempting to redeem market #{market_id}...")
                
                tx_hash = self.redeem_positions(market_id)
                
                if tx_hash:
                    logger.info(f"✅ Redeemed market #{market_id}: {tx_hash}")
                    redeemed_count += 1
                else:
                    logger.warning(f"⚠️ Could not redeem market #{market_id}")
            
            logger.info(f"✅ Cleanup complete: {redeemed_count}/{len(resolved_markets)} markets redeemed")
            return redeemed_count
            
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")
            return 0

    def cleanup_resolved_positions(self) -> int:
        """
        Find and redeem all positions from resolved markets.
        
        Returns:
            Number of markets redeemed
            
        Example:
            >>> client = OpinionClient()
            >>> count = client.cleanup_resolved_positions()
            >>> print(f"Redeemed {count} resolved markets")
        """
        try:
            # Get all positions
            positions = self.get_positions()
            
            if not positions:
                logger.debug("No positions to cleanup")
                return 0
            
            # Track resolved markets
            resolved_markets = set()
            
            for pos in positions:
                # pos is already a dict (get_positions() converts Pydantic to dict)
                # But let's be defensive - handle both dict and Pydantic model
                if isinstance(pos, dict):
                    market_id = pos.get('market_id')
                    shares = float(pos.get('shares_owned', 0))
                else:
                    # Pydantic model - use attribute access
                    market_id = getattr(pos, 'market_id', None)
                    shares = float(getattr(pos, 'shares_owned', 0))
                
                if not market_id or shares <= 0:
                    continue  # Skip invalid or empty positions
                
                # Check if market is resolved
                try:
                    if self.is_market_resolved(market_id):
                        resolved_markets.add(market_id)
                except Exception as e:
                    logger.debug(f"Could not check if market {market_id} is resolved: {e}")
                    continue
            
            if not resolved_markets:
                logger.info("✅ No resolved positions to cleanup")
                return 0
            
            logger.info(f"🔍 Found {len(resolved_markets)} resolved markets with positions")
            
            # Redeem each market
            redeemed_count = 0
            for market_id in resolved_markets:
                logger.info(f"💰 Attempting to redeem market #{market_id}...")
                
                tx_hash = self.redeem_positions(market_id)
                
                if tx_hash:
                    logger.info(f"✅ Redeemed market #{market_id}: {tx_hash}")
                    redeemed_count += 1
                else:
                    logger.warning(f"⚠️ Could not redeem market #{market_id}")
            
            logger.info(f"✅ Cleanup complete: {redeemed_count}/{len(resolved_markets)} markets redeemed")
            return redeemed_count
            
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")
            return 0


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_client() -> OpinionClient:
    """
    Factory function to create an OpinionClient instance.
    
    Returns:
        Configured OpinionClient
        
    Raises:
        ValueError: If credentials are missing
    """
    return OpinionClient()


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("=== API Client Module Test ===")
    print("Note: This requires valid credentials in .env file")
    print()
    
    try:
        client = create_client()
        print("✅ Client created successfully")
        
        # Test market fetching
        markets = client.get_all_active_markets()
        print(f"✅ Fetched {len(markets)} active markets")
        
        if markets:
            # Test orderbook for first market
            first_market = markets[0]
            market_id = first_market.get('market_id')
            token_id = first_market.get('yes_token_id')
            
            print(f"\nTesting orderbook for market {market_id}...")
            orderbook = client.get_market_orderbook(token_id)
            
            if orderbook:
                bids = orderbook.get('bids', [])
                asks = orderbook.get('asks', [])
                print(f"✅ Orderbook: {len(bids)} bids, {len(asks)} asks")
            else:
                print("⚠️ Empty orderbook")
        
        print("\n✅ All API client tests passed!")
        
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
    except Exception as e:
        print(f"❌ Test failed: {e}")
