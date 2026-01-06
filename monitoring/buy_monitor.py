"""
BUY Monitor Module
==================

Monitors BUY order until filled, cancelled, expired, or timeout.

Key responsibilities:
- Poll order status at regular intervals
- Detect fill, cancellation, expiration, timeout
- Periodic liquidity checks (every 5th iteration)
- Extract fill data from order or trades fallback
- Return structured result dict

Extracted from mvp_stage3.py for reusability.

Usage:
    from monitoring.buy_monitor import BuyMonitor
    
    monitor = BuyMonitor(config, client, state)
    result = monitor.monitor_until_filled(order_id, timeout_at)
    
    if result['status'] == 'filled':
        print(f"Filled {result['filled_amount']} tokens at {result['avg_fill_price']}")
"""

import time
from typing import Dict, Any, Tuple
from datetime import datetime, timedelta
from logger_config import setup_logger
from utils import safe_float, format_price, format_percent, get_timestamp
from monitoring.liquidity_checker import LiquidityChecker

logger = setup_logger(__name__)


class BuyMonitor:
    """
    Monitors BUY order status and liquidity conditions.
    
    Attributes:
        config: Configuration dictionary
        client: API client instance
        state: Current bot state dictionary
        liquidity_checker: LiquidityChecker instance
    """
    
    def __init__(self, config: Dict[str, Any], client, state: Dict[str, Any], heartbeat_callback=None):
        """
        Initialize BUY Monitor.

        Args:
            config: Configuration dictionary
            client: OpinionClient instance
            state: Current state dictionary (for market/token info)
            heartbeat_callback: Optional callback function to send heartbeat notifications

        Example:
            >>> monitor = BuyMonitor(config, client, state)
        """
        self.config = config
        self.client = client
        self.state = state
        self.heartbeat_callback = heartbeat_callback

        # Initialize liquidity checker
        self.liquidity_checker = LiquidityChecker(config, client)

        # Extract config values
        self.check_interval = config['FILL_CHECK_INTERVAL_SECONDS']
        self.timeout_hours = config['BUY_ORDER_TIMEOUT_HOURS']

        logger.debug(
            f"BuyMonitor initialized: "
            f"check_interval={self.check_interval}s, "
            f"timeout={self.timeout_hours}h"
        )
    
    def monitor_until_filled(
        self,
        order_id: str,
        timeout_at: datetime
    ) -> Dict[str, Any]:
        """
        Monitor order until filled, cancelled, expired, or timeout.
        
        Args:
            order_id: Order ID to monitor
            timeout_at: Datetime when monitoring should timeout
            
        Returns:
            Dictionary with structure:
            {
                'status': 'filled' | 'timeout' | 'cancelled' | 'expired' | 'deteriorated',
                'filled_amount': float (tokens, if filled),
                'avg_fill_price': float (if filled),
                'filled_usdt': float (if filled),
                'fill_timestamp': str (if filled),
                'reason': str (if not filled)
            }
        
        Example:
            >>> timeout_at = datetime.now() + timedelta(hours=24)
            >>> result = monitor.monitor_until_filled('ord_123', timeout_at)
            >>> if result['status'] == 'filled':
            ...     print(f"Got {result['filled_amount']} tokens")
        """
        logger.info("🔄 Starting BUY order monitoring")
        logger.info(f"   Order ID: {order_id}")
        logger.info(f"   Check interval: {self.check_interval}s")
        logger.info(f"   Timeout: {timeout_at.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")
        
        # Extract market info from state
        # State can have data in root OR in current_position depending on stage
        market_id = self.state.get('market_id') or self.state.get('current_position', {}).get('market_id')
        token_id = self.state.get('token_id') or self.state.get('current_position', {}).get('token_id')
        
        # current_price in state is OUR order price, not best bid from orderbook
        # For liquidity check we need the INITIAL best bid that was in orderbook
        # This should be stored separately, but for now use our order price as approximation
        initial_best_bid = safe_float(
            self.state.get('initial_best_bid') or 
            self.state.get('current_price') or 
            self.state.get('current_position', {}).get('price') or
            0
        )
        
        # Log what we got to debug
        logger.debug(f"Liquidity check params: market_id={market_id}, initial_bid=${initial_best_bid:.4f}")

        # Validate token_id exists
        if not token_id:
            # Try alternate location in state
            token_id = self.state.get('current_position', {}).get('token_id')
            
            if not token_id:
                logger.error("❌ CRITICAL: token_id missing from state!")
                logger.error(f"   State keys: {list(self.state.keys())}")
                logger.error(f"   Current position keys: {list(self.state.get('current_position', {}).keys())}")
                raise ValueError("token_id is required for monitoring but missing from state")
        
        check_count = 0
        last_liquidity_check = 0
        LIQUIDITY_CHECK_INTERVAL = 5  # Check every 5th iteration
        
        try:
            while True:
                check_count += 1
                check_time = datetime.now().strftime("%H:%M:%S")
                
                # =============================================================
                # CHECK: TIMEOUT
                # =============================================================
                if datetime.now() >= timeout_at:
                    logger.warning("")
                    logger.warning("=" * 50)
                    logger.warning("⏰ BUY ORDER TIMEOUT")
                    logger.warning("=" * 50)
                    logger.warning(f"   Order has been pending for {self.timeout_hours} hours")
                    logger.warning("   Exiting monitoring")
                    logger.warning("")
                    
                    return {
                        'status': 'timeout',
                        'filled_amount': None,
                        'avg_fill_price': None,
                        'filled_usdt': None,
                        'fill_timestamp': None,
                        'reason': f'Order pending for {self.timeout_hours} hours without fill'
                    }
                
                # =============================================================
                # PERIODIC LIQUIDITY CHECK
                # =============================================================
                if check_count - last_liquidity_check >= LIQUIDITY_CHECK_INTERVAL:
                    logger.debug(f"[{check_time}] 🔍 Checking liquidity...")
                    
                    # DEFENSIVE: Check if token_id is valid before liquidity check
                    # Recovery may not have token_id immediately available
                    if not token_id or token_id == 'unknown' or isinstance(token_id, int):
                        logger.warning(f"⚠️ Invalid token_id for liquidity check")
                        logger.warning(f"   token_id: {token_id} (type: {type(token_id).__name__})")
                        logger.info(f"   Skipping liquidity deterioration detection for this cycle")
                        logger.info(f"   Bot will still monitor order fill status")
                        liquidity = {'is_acceptable': True}  # Skip check, assume OK
                    else:
                        # Normal liquidity check with valid token_id
                        liquidity = self.liquidity_checker.check_liquidity(
                            market_id=market_id,
                            token_id=token_id,
                            initial_best_bid=initial_best_bid
                        )
                    
                    if not liquidity['ok']:
                        logger.warning("")
                        logger.warning("=" * 50)
                        logger.warning("⚠️  LIQUIDITY DETERIORATED")
                        logger.warning("=" * 50)
                        logger.warning(f"   Reason: {liquidity['deterioration_reason']}")
                        logger.warning(f"   Current bid: {format_price(liquidity['current_best_bid'])}")
                        logger.warning(f"   Current spread: {format_percent(liquidity['current_spread_pct'])}")
                        logger.warning("")
                        
                        # If auto-cancel enabled, return deteriorated status
                        if self.config.get('LIQUIDITY_AUTO_CANCEL', True):
                            logger.warning("   Auto-cancel enabled - exiting monitoring")
                            logger.warning("   Bot will cancel order and find new market")
                            logger.warning("")
                            
                            return {
                                'status': 'deteriorated',
                                'filled_amount': None,
                                'avg_fill_price': None,
                                'filled_usdt': None,
                                'fill_timestamp': None,
                                'reason': liquidity['deterioration_reason']
                            }
                    else:
                        logger.debug(
                            f"[{check_time}] ✅ Liquidity OK - "
                            f"Bid: {format_price(liquidity['current_best_bid'])}, "
                            f"Spread: {format_percent(liquidity['current_spread_pct'])}"
                        )
                    
                    last_liquidity_check = check_count
                
                # =============================================================
                # SEND HEARTBEAT IF CALLBACK PROVIDED
                # =============================================================
                if self.heartbeat_callback:
                    try:
                        self.heartbeat_callback()
                    except Exception as e:
                        logger.debug(f"Heartbeat callback failed: {e}")

                # =============================================================
                # GET ORDER STATUS
                # =============================================================
                order = self.client.get_order(order_id)

                if not order:
                    logger.warning(f"[{check_time}] ⚠️  Failed to fetch order status")
                    time.sleep(self.check_interval)
                    continue
                
                status = order.get('status')  # int: 0=pending, 1=partial, 2=finished, 3=cancelled, 4=expired
                status_enum = order.get('status_enum', 'unknown')
                
                # =============================================================
                # CHECK: ORDER FILLED
                # =============================================================
                if status_enum == 'Finished' or status == 2:
                    logger.info("")
                    logger.info("=" * 50)
                    logger.info("✅ BUY ORDER FILLED!")
                    logger.info("=" * 50)
                    
                    # Extract fill data
                    filled_amount, avg_fill_price, filled_usdt = self._extract_fill_data(order)
                    
                    logger.info(f"   Filled: {filled_amount:.4f} YES tokens")
                    logger.info(f"   Avg price: {format_price(avg_fill_price)}")
                    logger.info(f"   Total cost: ${filled_usdt:.2f}")
                    logger.info("")
                    
                    return {
                        'status': 'filled',
                        'filled_amount': filled_amount,
                        'avg_fill_price': avg_fill_price,
                        'filled_usdt': filled_usdt,
                        'fill_timestamp': get_timestamp(),
                        'reason': None
                    }
                
                # =============================================================
                # CHECK: ORDER CANCELLED/EXPIRED
                # =============================================================
                # Support both US spelling (Canceled) and UK spelling (Cancelled)
                if status_enum in ['Cancelled', 'Canceled', 'Expired'] or status in [3, 4]:
                    logger.error(f"[{check_time}] ❌ Order {status_enum}!")
                    logger.warning("")
                    logger.warning(f"⚠️  Order was {status_enum.lower()}")
                    logger.warning(f"   Possible reasons:")
                    logger.warning(f"   - Market was resolved before order filled")
                    logger.warning(f"   - Order was manually canceled")
                    logger.warning(f"   - Exchange/platform canceled the order")
                    logger.warning(f"   - Insufficient balance")
                    logger.warning(f"   - Order expired")
                    logger.warning("")
                    logger.warning(f"📊 Diagnostics:")
                    logger.warning(f"   Order ID: {order_id}")
                    logger.warning(f"   Bot will search for new market")
                    logger.warning("")

                    return {
                        'status': status_enum.lower(),
                        'filled_amount': None,
                        'avg_fill_price': None,
                        'filled_usdt': None,
                        'fill_timestamp': None,
                        'reason': f'Order {status_enum.lower()}'
                    }
                
                # =============================================================
                # ORDER STILL PENDING
                # =============================================================
                logger.info(f"[{check_time}] ⏳ Order {status_enum}... (check #{check_count})")
                
                time.sleep(self.check_interval)
        
        except KeyboardInterrupt:
            logger.info("")
            logger.info("⛔ Monitoring stopped by user")
            logger.info("")
            # Re-raise KeyboardInterrupt so main loop can send shutdown notification
            raise
        
        except Exception as e:
            logger.exception(f"Unexpected error during monitoring: {e}")
            
            return {
                'status': 'error',
                'filled_amount': None,
                'avg_fill_price': None,
                'filled_usdt': None,
                'fill_timestamp': None,
                'reason': f'Error: {str(e)}'
            }
    
    def _extract_fill_data(self, order: Dict[str, Any]) -> Tuple[float, float, float]:
        """
        Extract fill data from order response.
        
        Tries primary fields first (filled_shares, price, filled_amount).
        Falls back to extracting from trades[] array if primary data missing.
        
        Args:
            order: Order dictionary from API
            
        Returns:
            Tuple of (filled_amount_tokens, avg_fill_price, filled_usdt)
        
        Example:
            >>> order = {'filled_shares': 150.5, 'price': 0.066, 'filled_amount': 9.93}
            >>> tokens, price, usdt = monitor._extract_fill_data(order)
            >>> tokens
            150.5
        """
        # Try primary fields
        filled_shares = safe_float(order.get('filled_shares', 0))
        fill_price = safe_float(order.get('price', 0))
        filled_usdt = safe_float(order.get('filled_amount', 0))
        
        # DEBUG: Log what we got from primary fields
        logger.debug(f"   Primary fields: shares={filled_shares}, price={fill_price}, usdt={filled_usdt}")
        
        # Validation: if data is missing, extract from trades
        if filled_shares == 0 or fill_price == 0:
            logger.warning("⚠️  Missing fill data in order, extracting from trades...")
            
            trades = order.get('trades', [])
            if trades:
                total_shares = 0.0
                total_cost = 0.0
                
                # DEBUG: Log raw trades data
                logger.info(f"   🔍 DEBUG: Processing {len(trades)} trade(s)")
                logger.info(f"   🔍 DEBUG: First trade raw data: {trades[0] if trades else 'NONE'}")
                
                for trade in trades:
                    # Extract shares and amount (already in human-readable format)
                    shares = safe_float(trade.get('shares', 0))
                    cost = safe_float(trade.get('amount', 0))
                    
                    logger.debug(f"      Trade: shares={shares}, cost={cost}")
                    
                    total_shares += shares
                    total_cost += cost
                
                filled_shares = total_shares
                fill_price = (total_cost / total_shares) if total_shares > 0 else 0
                filled_usdt = total_cost
                
                logger.info(f"   ✅ Extracted from {len(trades)} trade(s)")
                logger.info(f"   🔍 DEBUG: Extracted totals: shares={filled_shares}, price={fill_price}, usdt={filled_usdt}")
                
                # Sanity check: extracted values must be non-zero
                if filled_shares == 0 or filled_usdt == 0:
                    logger.error(f"   ❌ EXTRACTION FAILED!")
                    logger.error(f"   filled_shares={filled_shares}, filled_usdt={filled_usdt}")
                    logger.error(f"   Raw trades: {trades}")
            else:
                logger.error("   ❌ No trades data available")
        
        # FALLBACK: Calculate from order amount and price if still missing
        if filled_shares == 0:
            logger.warning("⚠️  FALLBACK: Calculating fill data from order fields")
            
            # Try to get from order amount (USDT spent) and price
            amount_usdt = safe_float(order.get('amount', 0))
            price = safe_float(order.get('price', 0))
            
            if amount_usdt > 0 and price > 0:
                filled_shares = amount_usdt / price
                fill_price = price
                filled_usdt = amount_usdt
                
                logger.info(f"   ✅ Calculated from order: amount={amount_usdt}, price={price}")
                logger.info(f"   Result: shares={filled_shares:.4f}, price={fill_price:.4f}, usdt={filled_usdt:.2f}")
            else:
                logger.error(f"   ❌ FALLBACK FAILED - insufficient order data")
                logger.error(f"   amount={amount_usdt}, price={price}")
                logger.error(f"   Full order: {order}")
        
        return (filled_shares, fill_price, filled_usdt)


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("Use test_buy_monitor.py for comprehensive testing")