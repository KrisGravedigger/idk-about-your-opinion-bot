"""
Market Selector Handler
=======================

Handles market discovery, selection, and BUY order placement.

Extracted from AutonomousBot to improve code organization.
Responsible for the SCANNING stage.
"""

import time
from typing import Dict, Any, Optional

from logger_config import setup_logger
from utils import format_price, format_usdt, get_timestamp, safe_float, interruptible_sleep
from core.capital_manager import InsufficientCapitalError, PositionTooSmallError

logger = setup_logger(__name__)


class MarketSelector:
    """
    Handles market discovery and selection.

    Manages the SCANNING stage including:
    - Orphaned position detection
    - Market scanning and ranking
    - Orderbook validation
    - BUY order placement
    """

    def __init__(self, bot):
        """
        Initialize Market Selector.

        Args:
            bot: AutonomousBot instance (for access to client, config, etc.)
        """
        self.bot = bot
        self.client = bot.client
        self.config = bot.config
        # REMOVED: self.state = bot.state (use self.bot.state instead to avoid stale references)
        self.state_manager = bot.state_manager
        self.scanner = bot.scanner
        self.pricing = bot.pricing
        self.capital_manager = bot.capital_manager
        self.order_manager = bot.order_manager
        self.telegram = bot.telegram

    def check_for_orphaned_position(self) -> bool:
        """
        Check for orphaned positions from previous incomplete cycles.

        Returns:
            True if orphaned position found and recovered, False otherwise
        """
        logger.info("🔍 Checking for existing active orders...")

        try:
            # Check if we have any active positions with significant shares
            positions = self.client.get_significant_positions(min_shares=5.0)

            if not positions:
                return False

            # Take first significant position
            pos = positions[0]
            market_id = pos.get('market_id')
            shares = float(pos.get('shares_owned', 0))

            # Get outcome_side to determine which token_id to use
            outcome_side_enum = pos.get('outcome_side_enum', 'Yes')
            if isinstance(outcome_side_enum, str):
                outcome_side_enum = outcome_side_enum.upper()

            logger.warning(f"⚠️ Found existing position in market {market_id} with {shares:.4f} {outcome_side_enum} tokens")
            logger.warning(f"   This may be from previous incomplete cycle")
            logger.info(f"🔄 Recovering to SELL stage...")
            logger.info(f"   Position side: {outcome_side_enum}")

            # Fetch market details to get token_id
            logger.info(f"   Fetching market details to recover token_id...")
            try:
                market_details = self.client.get_market(market_id)

                if market_details:
                    # Extract correct token_id based on outcome_side
                    if outcome_side_enum.lower() == 'yes':
                        token_id = getattr(market_details, 'yes_token_id', '')
                    else:
                        token_id = getattr(market_details, 'no_token_id', '')

                    logger.info(f"   ✅ Recovered token_id: {token_id[:20] if token_id else 'EMPTY'}...")
                else:
                    logger.error(f"   ❌ Could not fetch market details for #{market_id}")
                    token_id = ''

            except Exception as e:
                logger.error(f"   ❌ Error fetching market details: {e}")
                token_id = ''

            # Validate token_id - CRITICAL for placing SELL orders
            if not token_id or token_id == '':
                logger.error(f"   ❌ Cannot recover position without valid token_id")
                logger.error(f"   This position cannot be managed by the bot")
                logger.info(f"   💡 Skipping this position - will look for new opportunities")
                return False

            # Recover state with real avg_price if available
            avg_price = pos.get('avg_price', 0)
            if avg_price <= 0:
                logger.error(f"   ❌ Cannot recover position without valid avg_price")
                logger.error(f"   Position avg_price: {avg_price}")
                logger.error(f"   This position cannot be managed by the bot (stop-loss won't work)")
                logger.info(f"   💡 Skipping this position - will look for new opportunities")
                return False

            self.bot.state['stage'] = 'BUY_FILLED'
            self.bot.state['current_position'] = {
                'market_id': market_id,
                'token_id': token_id,
                'outcome_side': outcome_side_enum,
                'market_title': f"Recovered market #{market_id}",
                'filled_amount': shares,
                'avg_fill_price': avg_price,
                'filled_usdt': shares * avg_price,
                'fill_timestamp': get_timestamp()
            }
            self.state_manager.save_state(self.bot.state)
            return True

        except Exception as e:
            logger.warning(f"⚠️ Could not check for existing orders: {e}")
            logger.info("   Proceeding with normal scanning")
            return False

    def validate_orderbook(self, best_bid: float, best_ask: float) -> bool:
        """
        Validate orderbook prices before trading.

        Args:
            best_bid: Best bid price
            best_ask: Best ask price

        Returns:
            True if orderbook is valid, False otherwise
        """
        spread = best_ask - best_bid

        if spread < 0:
            logger.error(f"❌ INVALID ORDERBOOK: Negative spread!")
            logger.error(f"   Best bid: ${best_bid:.4f}")
            logger.error(f"   Best ask: ${best_ask:.4f}")
            logger.error(f"   This indicates crossed market or API data error")
            logger.error(f"   CANNOT place order with invalid orderbook - resetting to SCANNING")
            return False

        if best_bid <= 0 or best_ask <= 0:
            logger.error(f"❌ INVALID ORDERBOOK: Zero or negative prices!")
            logger.error(f"   Best bid: ${best_bid:.4f}, Best ask: ${best_ask:.4f}")
            return False

        if best_bid > 1.0 or best_ask > 1.0:
            logger.warning(f"⚠️ SUSPICIOUS: Prices > $1.00 in prediction market!")
            logger.warning(f"   Best bid: ${best_bid:.4f}, Best ask: ${best_ask:.4f}")
            # Continue but log warning

        return True

    def place_buy_order(self, selected_market, position_size: float, buy_price: float) -> Optional[Dict[str, Any]]:
        """
        Place BUY order for selected market.

        Args:
            selected_market: Selected MarketScore object
            position_size: Position size in USDT
            buy_price: BUY price

        Returns:
            Order result dict or None if failed
        """
        logger.info("📝 Placing BUY order...")

        result = self.order_manager.place_buy(
            market_id=selected_market.market_id,
            token_id=selected_market.yes_token_id,
            price=buy_price,
            amount_usdt=position_size
        )

        if not result:
            logger.error("Failed to place BUY order")

            # Check if order was actually placed despite error
            logger.info("🔍 Verifying if order was actually placed despite error...")
            time.sleep(2)

            positions = self.client.get_positions(market_id=selected_market.market_id)
            if positions:
                logger.warning("⚠️ Position exists despite place_buy error!")
                logger.warning("   Order may have been placed - checking...")

                shares = float(positions[0].get('shares_owned', 0))
                if shares > 0:
                    logger.info(f"✅ Found {shares:.4f} tokens - order WAS placed")
                    logger.info(f"🔄 Recovering to BUY_FILLED stage...")

                    # Build minimal position state
                    self.bot.state['stage'] = 'BUY_FILLED'
                    self.bot.state['current_position'] = {
                        'market_id': selected_market.market_id,
                        'token_id': selected_market.yes_token_id,
                        'outcome_side': selected_market.outcome_side,
                        'market_title': selected_market.title,
                        'filled_amount': shares,
                        'avg_fill_price': buy_price,
                        'filled_usdt': shares * buy_price,
                        'fill_timestamp': get_timestamp()
                    }
                    self.state_manager.save_state(self.bot.state)
                    return {'recovered': True}

            return None

        return result

    def save_buy_state(self, selected_market, order_id: str, buy_price: float, position_size: float):
        """
        Save state after successful BUY order placement.

        Args:
            selected_market: Selected MarketScore object
            order_id: Order ID from API
            buy_price: BUY price
            position_size: Position size in USDT
        """
        logger.info(f"✅ BUY order placed successfully")
        logger.info(f"💾 Saving state IMMEDIATELY to prevent order loss...")

        # Update state
        self.bot.state['stage'] = 'BUY_PLACED'
        self.bot.state['current_position'] = {
            'market_id': selected_market.market_id,
            'token_id': selected_market.yes_token_id,
            'outcome_side': selected_market.outcome_side,
            'market_title': selected_market.title,
            'is_bonus': selected_market.is_bonus,
            'order_id': str(order_id),
            'side': 'BUY',
            'price': buy_price,
            'amount_usdt': position_size,
            'placed_at': get_timestamp()
        }

        # SAVE IMMEDIATELY
        self.state_manager.save_state(self.bot.state)

        logger.info(f"✅ State saved with order_id: {order_id}")
        logger.info(f"📍 Next stage: BUY_PLACED → BUY_MONITORING")

    def send_buy_notification(self, selected_market, buy_price: float, position_size: float):
        """
        Send Telegram notification about BUY order placement.

        Args:
            selected_market: Selected MarketScore object
            buy_price: BUY price
            position_size: Position size in USDT
        """
        # Get orderbook info for notification
        orderbook_info = {}
        try:
            orderbook = self.client.get_market_orderbook(selected_market.yes_token_id)
            if orderbook and 'bids' in orderbook and 'asks' in orderbook:
                bids = orderbook['bids']
                asks = orderbook['asks']
                if bids and asks:
                    best_bid = float(bids[0].get('price', 0)) if isinstance(bids[0], dict) else float(bids[0][0])
                    best_ask = float(asks[0].get('price', 0)) if isinstance(asks[0], dict) else float(asks[0][0])
                    orderbook_info = {
                        'spread': best_ask - best_bid,
                        'best_bid': best_bid,
                        'best_ask': best_ask
                    }
        except Exception as e:
            logger.debug(f"Could not fetch orderbook for notification: {e}")

        # Send notification
        self.telegram.send_state_change(
            new_stage='BUY_PLACED',
            market_id=selected_market.market_id,
            market_title=selected_market.title,
            price=buy_price,
            amount=position_size,
            **orderbook_info
        )

    def handle_scanning(self) -> bool:
        """
        SCANNING stage: Find best market to trade.

        Transitions to: BUY_PLACED (if market found)
        Transitions to: IDLE (if no suitable market)
        """
        logger.info("🔍 SCANNING - Finding best market...")

        # Check for orphaned positions first
        if self.check_for_orphaned_position():
            return True

        try:
            # Load bonus markets if configured
            bonus_file = self.config.get('BONUS_MARKETS_FILE')
            if bonus_file:
                self.scanner.load_bonus_markets(bonus_file)

            # Scan and rank markets
            top_markets = self.scanner.scan_and_rank(limit=5)

            if not top_markets:
                logger.warning("No suitable markets found")
                logger.info("Waiting 1 minute before next scan...")
                interruptible_sleep(60)  # Wait 1 minute, but responsive to CTRL+C
                return True

            # Select best market
            selected = top_markets[0]

            logger.info(f"✅ Selected: #{selected.market_id} (Score: {selected.score:.2f})")
            logger.info(f"   {selected.title}")
            if selected.is_bonus:
                logger.info("   🌟 BONUS MARKET")

            # Get fresh orderbook
            fresh_orderbook = self.scanner.get_fresh_orderbook(
                selected.market_id,
                selected.yes_token_id
            )

            if not fresh_orderbook:
                logger.error("Failed to get fresh orderbook")
                return False

            best_bid = fresh_orderbook['best_bid']
            best_ask = fresh_orderbook['best_ask']

            # Validate orderbook
            if not self.validate_orderbook(best_bid, best_ask):
                self.bot.state['stage'] = 'SCANNING'
                self.state_manager.save_state(self.bot.state)
                return False

            spread = best_ask - best_bid
            logger.info(f"   Bid: {format_price(best_bid)} | Ask: {format_price(best_ask)}")
            logger.info(f"   Spread: {format_price(spread)}")

            # Calculate position size
            try:
                position_size = self.capital_manager.get_position_size()
            except InsufficientCapitalError as e:
                logger.error(f"Insufficient capital: {e}")
                logger.info("Bot will exit - please add funds")

                # Cancel any orphaned orders
                if 'current_position' in self.bot.state and 'order_id' in self.bot.state['current_position']:
                    orphaned_order_id = self.bot.state['current_position']['order_id']
                    logger.warning(f"⚠️ Found orphaned order from previous attempt: {orphaned_order_id}")
                    logger.info(f"🧹 Cancelling orphaned order...")
                    try:
                        self.client.cancel_order(orphaned_order_id)
                        logger.info(f"✅ Cancelled orphaned order")
                    except Exception as cancel_err:
                        logger.warning(f"⚠️ Could not cancel orphaned order: {cancel_err}")

                self.state_manager.reset_position(self.bot.state)
                self.bot.state['stage'] = 'IDLE'
                self.state_manager.save_state(self.bot.state)
                return False
            except PositionTooSmallError as e:
                logger.error(f"Position too small: {e}")
                logger.info("Adjust CAPITAL settings in config")
                self.bot.state['stage'] = 'IDLE'
                self.state_manager.save_state(self.bot.state)
                return False

            logger.info(f"   Position size: {format_usdt(position_size)}")

            # Calculate BUY price
            buy_price = self.pricing.calculate_buy_price(best_bid, best_ask)
            logger.info(f"   BUY price: {format_price(buy_price)}")

            # Place BUY order
            result = self.place_buy_order(selected, position_size, buy_price)

            if not result:
                return False

            # Check if this was a recovery (order placed despite error)
            if result.get('recovered'):
                return True

            # Extract order_id
            order_id = None
            try:
                order_id = result.get('order_id', result.get('orderId', None))
                if not order_id:
                    logger.warning(f"⚠️ Could not extract order_id from result")
                    logger.warning(f"   Result keys: {list(result.keys()) if result else 'None'}")
                    order_id = 'unknown'
            except Exception as e:
                logger.warning(f"⚠️ Error extracting order_id: {e}")
                order_id = 'unknown'

            # Save state
            self.save_buy_state(selected, order_id, buy_price, position_size)

            # Send notification
            self.send_buy_notification(selected, buy_price, position_size)

            return True

        except Exception as e:
            logger.exception(f"Error in scanning: {e}")
            return False
