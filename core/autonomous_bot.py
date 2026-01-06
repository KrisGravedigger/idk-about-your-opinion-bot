"""
Autonomous Bot Orchestrator
===========================

Main brain that orchestrates the complete trading cycle using all modules.

State Machine:
    IDLE → SCANNING → BUY_PLACED → BUY_MONITORING → BUY_FILLED → 
    SELL_PLACED → SELL_MONITORING → COMPLETED → IDLE (repeat)

Modules Used:
    - CapitalManager: Calculate position size
    - StateManager: Load/save state
    - MarketScanner: Find best markets
    - PricingStrategy: Calculate BUY/SELL prices
    - OrderManager: Place orders
    - BuyMonitor: Monitor BUY fills
    - SellMonitor: Monitor SELL fills
    - LiquidityChecker: Check liquidity
    - PositionTracker: Calculate P&L

Usage:
    from core.autonomous_bot import AutonomousBot
    
    bot = AutonomousBot(config, client)
    bot.run()  # Runs until interrupted
"""

import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from logger_config import setup_logger
from utils import format_price, format_usdt, format_percent, get_timestamp

# Import all required modules
from core.capital_manager import CapitalManager, InsufficientCapitalError, PositionTooSmallError
from core.state_manager import StateManager
from market_scanner import MarketScanner
from strategies.pricing import PricingStrategy
from order_manager import OrderManager
from monitoring.buy_monitor import BuyMonitor
from monitoring.sell_monitor import SellMonitor
from monitoring.liquidity_checker import LiquidityChecker
from position_tracker import PositionTracker
from pnl_statistics import PnLStatistics
from telegram_notifications import TelegramNotifier

logger = setup_logger(__name__)


class AutonomousBot:
    """
    Autonomous trading bot orchestrator.
    
    Manages complete trading cycle from market selection to position closing.
    
    Attributes:
        config: Configuration dictionary
        client: API client instance
        capital_manager: Capital management module
        state_manager: State persistence module
        scanner: Market scanner module
        pricing: Pricing strategy module
        order_manager: Order placement module
        buy_monitor: BUY monitoring module
        sell_monitor: SELL monitoring module
        tracker: Position tracker module
    """
    
    def __init__(self, config: Dict[str, Any], client):
        """
        Initialize Autonomous Bot.
        
        Args:
            config: Configuration dictionary
            client: OpinionClient instance
        """
        self.config = config
        self.client = client
        
        # Initialize all modules
        self.capital_manager = CapitalManager(config, client)
        self.state_manager = StateManager()
        self.pnl_stats = PnLStatistics()  # Separate P&L statistics manager
        self.telegram = TelegramNotifier()  # Telegram notifications
        self.scanner = MarketScanner(client)
        self.pricing = PricingStrategy(config)
        self.order_manager = OrderManager(client)
        self.tracker = PositionTracker()

        # CHANGED: Load state immediately in constructor
        # This allows autonomous_bot_main.py to modify state before run()
        self.state = self.state_manager.load_state()

        # Config shortcuts
        self.cycle_delay = config.get('CYCLE_DELAY_SECONDS', 10)
        self.max_cycles = config.get('MAX_CYCLES', None)  # None = infinite
        self.heartbeat_interval_hours = config.get('TELEGRAM_HEARTBEAT_INTERVAL_HOURS', 1.0)
        self.last_heartbeat = None  # Track last heartbeat time
        
        logger.info("🤖 Autonomous Bot initialized")
        logger.debug(f"   Modules loaded: {self._list_modules()}")
    
    def _list_modules(self) -> str:
        """List all initialized modules for logging."""
        modules = [
            'CapitalManager',
            'StateManager',
            'MarketScanner',
            'PricingStrategy',
            'OrderManager',
            'PositionTracker'
        ]
        return ', '.join(modules)
    
    # =========================================================================
    # MAIN RUN LOOP
    # =========================================================================
    
    def run(self) -> int:
        """
        Main bot execution loop.
        
        Runs until interrupted or max cycles reached.
        
        Returns:
            0 on success, 1 on failure
        """
        logger.info("")
        logger.info("=" * 60)
        logger.info("🚀 STARTING AUTONOMOUS BOT")
        logger.info("=" * 60)
        logger.info("")

        # Display current P&L statistics at startup
        self.pnl_stats.display_summary(logger)

        # Send Telegram notification: Bot started
        try:
            balance = self.client.get_usdt_balance()
        except Exception as e:
            logger.warning(f"Could not fetch balance for Telegram notification: {e}")
            balance = 0.0

        self.telegram.send_bot_start(
            stats=self.pnl_stats.get_summary(),
            config=self.config,
            balance=balance
        )

        try:
            # Send initial heartbeat to verify current state
            logger.debug("Sending initial heartbeat...")
            self._send_heartbeat_now()
        except Exception as e:
            logger.warning(f"Could not send initial heartbeat: {e}")

        try:
            # State already loaded in __init__
            # But reload here to catch any changes made in autonomous_bot_main.py
            if self.state is None:
                self.state = self.state_manager.load_state()
            
            cycle_count = 0
            
            while True:
                cycle_count += 1
                
                # Check max cycles limit
                if self.max_cycles and cycle_count > self.max_cycles:
                    logger.info(f"Reached max cycles limit ({self.max_cycles})")
                    break
                
                # Get current stage
                stage = self.state.get('stage', 'IDLE')
                
                logger.info(f"📍 Cycle #{cycle_count} | Stage: {stage}")
                
                # Execute stage handler
                success = self._execute_stage(stage)

                if not success:
                    logger.error(f"Stage {stage} failed - pausing before retry")
                    time.sleep(self.cycle_delay * 3)  # Longer delay on error

                # Check if heartbeat should be sent
                self._check_and_send_heartbeat()

                # Brief pause between cycles
                time.sleep(self.cycle_delay)
        
        except KeyboardInterrupt:
            logger.info("")
            logger.info("⛔ Bot stopped by user")
            logger.info("")
            self._display_session_summary()

            # Send Telegram notification: Bot stopped
            try:
                logger.info("📱 Sending shutdown notification to Telegram...")
                result = self.telegram.send_bot_stop(
                    stats=self.pnl_stats.get_summary(),
                    last_logs=self._get_recent_logs()
                )
                if result:
                    logger.info("✅ Shutdown notification sent successfully")
                else:
                    logger.warning("⚠️ Shutdown notification failed to send")
            except Exception as e:
                logger.error(f"❌ Error sending shutdown notification: {e}")
                import traceback
                logger.debug(traceback.format_exc())

            return 0

        except Exception as e:
            logger.exception(f"Unexpected error in main loop: {e}")

            # Send Telegram notification: Bot stopped with error
            try:
                logger.info("📱 Sending error shutdown notification to Telegram...")
                result = self.telegram.send_bot_stop(
                    stats=self.pnl_stats.get_summary(),
                    last_logs=self._get_recent_logs()
                )
                if result:
                    logger.info("✅ Error shutdown notification sent")
                else:
                    logger.warning("⚠️ Error shutdown notification failed")
            except Exception as notify_error:
                logger.error(f"❌ Error sending shutdown notification: {notify_error}")

            return 1

        logger.info("")
        logger.info("✅ Bot execution completed")
        self._display_session_summary()

        # Send Telegram notification: Bot stopped normally
        try:
            logger.info("📱 Sending completion notification to Telegram...")
            result = self.telegram.send_bot_stop(
                stats=self.pnl_stats.get_summary(),
                last_logs=self._get_recent_logs()
            )
            if result:
                logger.info("✅ Completion notification sent")
            else:
                logger.warning("⚠️ Completion notification failed")
        except Exception as e:
            logger.error(f"❌ Error sending completion notification: {e}")

        return 0
    
    def _execute_stage(self, stage: str) -> bool:
        """
        Execute handler for current stage.
        
        Args:
            stage: Current stage name
            
        Returns:
            True if stage executed successfully, False otherwise
        """
        
        # ================================================================
        # CRITICAL: Before executing ANY stage, verify state consistency
        # ================================================================
        # This is the FIRST LINE OF DEFENSE against orphaned orders
        
        if stage in ['IDLE', 'SCANNING']:
            # These stages should NOT have active positions
            # But check anyway in case of state corruption
            try:
                logger.debug("🔍 Pre-stage check: Verifying no orphaned positions...")
                positions = self.client.get_significant_positions(min_shares=1.0)

                if positions:
                    # We have significant positions but state says IDLE/SCANNING
                    # This is a CRITICAL inconsistency
                    logger.warning("=" * 60)
                    logger.warning("⚠️  CRITICAL: State inconsistency detected!")
                    logger.warning(f"   State says: {stage}")
                    logger.warning(f"   API shows: {len(positions)} significant position(s)")
                    logger.warning("=" * 60)

                # Take first significant position (dust already filtered by get_significant_positions)
                pos = positions[0]
                market_id = pos.get('market_id')
                shares = float(pos.get('shares_owned', 0))

                logger.warning(f"🔄 AUTO-RECOVERY: Found position in market #{market_id}")
                logger.warning(f"   Shares: {shares:.4f}")
                logger.info(f"   Recovering to BUY_FILLED stage to handle SELL...")

                # Get outcome_side to determine which token_id to use
                outcome_side_enum = pos.get('outcome_side_enum', 'Yes')
                logger.info(f"   Position side: {outcome_side_enum}")

                # Fetch market details to get token_id
                logger.info(f"   Fetching market details to recover token_id...")
                try:
                    market_details = self.client.get_market(market_id)

                    if market_details:
                        # Extract correct token_id based on outcome_side_enum
                        # NOTE: market_details is Pydantic model, use attribute access
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

                # Force state to BUY_FILLED so bot will place SELL
                # Try to get real avg_price from position, fallback to calculation
                avg_price = pos.get('avg_price', 0)

                if avg_price <= 0:
                    # Try to calculate from position value (if API provides it)
                    # Common field names: 'total_value', 'value', 'cost_basis', 'invested'
                    total_value = (
                        pos.get('total_value', 0) or
                        pos.get('value', 0) or
                        pos.get('cost_basis', 0) or
                        pos.get('invested', 0)
                    )

                    if total_value > 0 and shares > 0:
                        avg_price = total_value / shares
                        logger.info(f"✅ Calculated avg_price from position: ${avg_price:.4f}")
                        logger.info(f"   (value=${total_value:.2f} / shares={shares:.4f})")
                    else:
                        logger.warning(f"⚠️ Cannot calculate avg_price - no value field in position")
                        logger.warning(f"   Using minimal fallback $0.01")
                        logger.warning(f"   Stop-loss may not work correctly with fallback price")
                        avg_price = 0.01

                self.state['stage'] = 'BUY_FILLED'
                self.state['current_position'] = {
                    'market_id': market_id,
                    'token_id': token_id,  # ← FIXED: use recovered token_id, not pos.get()
                    'outcome_side': outcome_side_enum,
                    'market_title': pos.get('title', f"Recovered market #{market_id}"),
                    'filled_amount': shares,
                    'avg_fill_price': avg_price,
                    'filled_usdt': shares * avg_price,
                    'fill_timestamp': get_timestamp()
                }
                self.state_manager.save_state(self.state)

                # Change stage to BUY_FILLED for this execution
                stage = 'BUY_FILLED'
                logger.info("✅ State recovered - will execute BUY_FILLED handler")
                # NOTE: We're in _execute_stage(), not run() loop
                # Can't use break here - just continue to execute BUY_FILLED handler below
            except Exception as e:
                logger.debug(f"Pre-stage check failed (non-critical): {e}")
        
        handlers = {
            'IDLE': self._handle_idle,
            'SCANNING': self._handle_scanning,
            'BUY_PLACED': self._handle_buy_placed,
            'BUY_MONITORING': self._handle_buy_monitoring,
            'BUY_FILLED': self._handle_buy_filled,
            'SELL_PLACED': self._handle_sell_placed,
            'SELL_MONITORING': self._handle_sell_monitoring,
            'COMPLETED': self._handle_completed
        }
        
        handler = handlers.get(stage)
        
        if not handler:
            logger.error(f"Unknown stage: {stage}")
            # Reset to IDLE on unknown stage
            self.state['stage'] = 'IDLE'
            self.state_manager.save_state(self.state)
            return False
        
        try:
            return handler()
        except Exception as e:
            logger.exception(f"Error in {stage} handler: {e}")
            return False
    
    # =========================================================================
    # STAGE HANDLERS
    # =========================================================================
    
    def _handle_idle(self) -> bool:
        """
        IDLE stage: Bot is waiting to start new cycle.
        
        Transitions to: SCANNING
        """
        logger.info("💤 IDLE - Ready to start new cycle")
        
        # CLEANUP: Redeem any resolved positions before starting new cycle
        logger.info("🧹 Checking for resolved positions to cleanup...")
        try:
            redeemed = self.client.cleanup_resolved_positions()
            if redeemed > 0:
                logger.info(f"✅ Cleaned up {redeemed} resolved market(s)")
        except Exception as e:
            logger.warning(f"⚠️ Cleanup failed (non-critical): {e}")
        
        # Transition to scanning
        self.state['stage'] = 'SCANNING'
        self.state['cycle_number'] = self.state.get('cycle_number', 0) + 1
        self.state['started_at'] = get_timestamp()
        
        self.state_manager.save_state(self.state)
        
        return True
    
    def _handle_scanning(self) -> bool:
        """
        SCANNING stage: Find best market to trade.
        
        Transitions to: BUY_PLACED (if market found)
        Transitions to: IDLE (if no suitable market)
        """
        logger.info("🔍 SCANNING - Finding best market...")
        
        # SELF-HEALING: Check for orphaned active orders before scanning
        logger.info("🔍 Checking for existing active orders...")
        try:
            # Check if we have any active positions with significant shares
            # Dust positions (< 1.0 shares) are automatically filtered out
            positions = self.client.get_significant_positions(min_shares=1.0)

            if positions:
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
                        # NOTE: market_details is Pydantic model, use attribute access not .get()
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

                # Recover state with real avg_price if available
                avg_price = pos.get('avg_price', 0)
                if avg_price <= 0:
                    logger.warning(f"⚠️ Recovered position missing avg_price, using minimal fallback $0.01")
                    logger.warning(f"   Stop-loss may not work correctly with fallback price")
                    avg_price = 0.01

                self.state['stage'] = 'BUY_FILLED'
                self.state['current_position'] = {
                    'market_id': market_id,
                    'token_id': token_id,
                    'outcome_side': outcome_side_enum,
                    'market_title': f"Recovered market #{market_id}",
                    'filled_amount': shares,
                    'avg_fill_price': avg_price,
                    'filled_usdt': shares * avg_price,
                    'fill_timestamp': get_timestamp()
                }
                self.state_manager.save_state(self.state)
                return True
        except Exception as e:
            logger.warning(f"⚠️ Could not check for existing orders: {e}")
            logger.info("   Proceeding with normal scanning")
        
        try:
            # Load bonus markets if configured
            bonus_file = self.config.get('BONUS_MARKETS_FILE')
            if bonus_file:
                self.scanner.load_bonus_markets(bonus_file)
            
            # Scan and rank markets
            top_markets = self.scanner.scan_and_rank(limit=5)
            
            if not top_markets:
                logger.warning("No suitable markets found")
                logger.info("Waiting before next scan...")
                
                # Stay in SCANNING stage
                time.sleep(60)  # Wait 1 minute before retry
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
            
            logger.info(f"   Bid: {format_price(best_bid)} | Ask: {format_price(best_ask)}")
            
            # Calculate position size
            try:
                position_size = self.capital_manager.get_position_size()
            except InsufficientCapitalError as e:
                logger.error(f"Insufficient capital: {e}")
                logger.info("Bot will exit - please add funds")
                
                # CRITICAL: If we have current_position with order_id, cancel it
                # (This handles case where order was placed BEFORE capital check failed)
                if 'current_position' in self.state and 'order_id' in self.state['current_position']:
                    orphaned_order_id = self.state['current_position']['order_id']
                    logger.warning(f"⚠️ Found orphaned order from previous attempt: {orphaned_order_id}")
                    logger.info(f"🧹 Cancelling orphaned order to prevent duplicate positions...")
                    try:
                        self.client.cancel_order(orphaned_order_id)
                        logger.info(f"✅ Cancelled orphaned order")
                    except Exception as cancel_err:
                        logger.warning(f"⚠️ Could not cancel orphaned order: {cancel_err}")
                
                self.state_manager.reset_position(self.state)
                self.state['stage'] = 'IDLE'
                self.state_manager.save_state(self.state)
                return False
            except PositionTooSmallError as e:
                logger.error(f"Position too small: {e}")
                logger.info("Adjust CAPITAL settings in config")
                self.state['stage'] = 'IDLE'
                self.state_manager.save_state(self.state)
                return False
            
            logger.info(f"   Position size: {format_usdt(position_size)}")
            
            # Calculate BUY price
            buy_price = self.pricing.calculate_buy_price(best_bid, best_ask)
            
            logger.info(f"   BUY price: {format_price(buy_price)}")
            
            # Place BUY order
            logger.info("📝 Placing BUY order...")
            
            result = self.order_manager.place_buy(
                market_id=selected.market_id,
                token_id=selected.yes_token_id,
                price=buy_price,
                amount_usdt=position_size
            )
            
            if not result:
                logger.error("Failed to place BUY order")
                
                # CRITICAL: Check if failure was due to capital issues after placement attempt
                # In this case, order might have been placed but we got error response
                logger.info("🔍 Verifying if order was actually placed despite error...")
                
                # Wait 2 seconds for API to update
                time.sleep(2)
                
                # Check for recent orders on this market
                positions = self.client.get_positions(market_id=selected.market_id)
                if positions:
                    logger.warning("⚠️ Position exists despite place_buy error!")
                    logger.warning("   Order may have been placed - checking...")
                    
                    # Try to recover by checking if we have tokens
                    shares = float(positions[0].get('shares_owned', 0))
                    if shares > 0:
                        logger.info(f"✅ Found {shares:.4f} tokens - order WAS placed")
                        logger.info(f"🔄 Recovering to BUY_FILLED stage...")
                        
                        # Build minimal position state
                        self.state['stage'] = 'BUY_FILLED'
                        self.state['current_position'] = {
                            'market_id': selected.market_id,
                            'token_id': selected.yes_token_id,
                            'outcome_side': selected.outcome_side,  # NOWE: z selected market
                            'market_title': selected.title,
                            'filled_amount': shares,
                            'avg_fill_price': buy_price,
                            'filled_usdt': shares * buy_price,
                            'fill_timestamp': get_timestamp()
                        }
                        self.state_manager.save_state(self.state)
                        return True
                
                # No position found - order truly failed
                return False
            
            # ================================================================
            # CRITICAL: Save state IMMEDIATELY after successful place_buy()
            # This prevents lost orders if any error occurs below
            # ================================================================
            
            logger.info(f"✅ BUY order placed successfully")
            logger.info(f"💾 Saving state IMMEDIATELY to prevent order loss...")
            
            # Extract order_id with defensive error handling
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
            
            # Update state - MINIMAL data first, details can be added later
            self.state['stage'] = 'BUY_PLACED'
            self.state['current_position'] = {
                'market_id': selected.market_id,
                'token_id': selected.yes_token_id,
                'outcome_side': selected.outcome_side,  # NOWE: "YES" lub "NO"
                'market_title': selected.title,
                'is_bonus': selected.is_bonus,
                'order_id': str(order_id),
                'side': 'BUY',
                'price': buy_price,
                'amount_usdt': position_size,
                'placed_at': get_timestamp()
            }
            
            # SAVE IMMEDIATELY - before any logging or validation
            self.state_manager.save_state(self.state)

            logger.info(f"✅ State saved with order_id: {order_id}")
            logger.info(f"📍 Next stage: BUY_PLACED → BUY_MONITORING")

            # Get orderbook info for notification
            orderbook_info = {}
            try:
                orderbook = self.client.get_market_orderbook(selected.yes_token_id)
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

            # Send Telegram notification: BUY order placed
            self.telegram.send_state_change(
                new_stage='BUY_PLACED',
                market_id=selected.market_id,
                market_title=selected.title,
                price=buy_price,
                amount=position_size,
                **orderbook_info
            )

            return True
            
        except Exception as e:
            logger.exception(f"Error in scanning: {e}")
            return False
    
    def _handle_buy_placed(self) -> bool:
        """
        BUY_PLACED stage: BUY order placed, ready to monitor.
        
        Transitions to: BUY_MONITORING
        """
        logger.info("📋 BUY_PLACED - Transitioning to monitoring")
        
        # Simply transition to monitoring
        self.state['stage'] = 'BUY_MONITORING'
        self.state_manager.save_state(self.state)
        
        return True
    
    def _handle_buy_monitoring(self) -> bool:
        """
        BUY_MONITORING stage: Monitor BUY order until filled.
        
        Transitions to: BUY_FILLED (if filled)
        Transitions to: SCANNING (if cancelled/deteriorated)
        """
        logger.info("⏳ BUY_MONITORING - Waiting for fill...")
        
        position = self.state['current_position']
        order_id = position['order_id']
        market_id = position['market_id']
        
        # SELF-HEALING: If order_id is 'unknown', find it from API
        if order_id == 'unknown':
            logger.warning("⚠️ order_id is 'unknown' - attempting to recover from API...")
            logger.info("   This happens when bot recovered from orphaned PENDING order")
            logger.info("")
            
            try:
                # Use FILLED status (paradoxically includes pending orders with $0 filled)
                # Same logic as in autonomous_bot_main.py recovery
                orders = self.client.get_my_orders(
                    market_id=market_id,
                    status='FILLED',  # Status "1" includes orders with any fill amount (even $0!)
                    limit=20
                )

                # 🔍 DEBUG: Log ALL order details
                logger.info(f"🔍 DEBUG: API returned {len(orders)} orders:")
                for i, order in enumerate(orders):
                    logger.info(f"   Order #{i+1}:")
                    logger.info(f"      order_id: {order.get('order_id', 'N/A')}")
                    logger.info(f"      status: {order.get('status', 'N/A')} ({order.get('status_str', 'N/A')})")
                    logger.info(f"      side: {order.get('side', 'N/A')}")
                    logger.info(f"      price: {order.get('price', 'N/A')}")
                    logger.info(f"      maker_amount: {order.get('maker_amount', 'N/A')}")
                    logger.info(f"      amount: {order.get('amount', 'N/A')}")
                    logger.info(f"      filled_amount: {order.get('filled_amount', 'N/A')}")
                    logger.info(f"      ALL KEYS: {list(order.keys())}")

                    # Check if order is truly pending (filled_amount near 0)
                    order_amount = float(order.get('order_amount', 0) or 0)
                    filled_amount = float(order.get('filled_amount', 0) or 0)
                    
                    logger.info(f"      order_amount: ${order_amount:.2f}")
                    logger.info(f"      filled_amount: ${filled_amount:.2f}")
                    
                    # Skip if already significantly filled
                    if filled_amount > 0.10:
                        logger.info(f"      ⏭️  Skipping - already filled ${filled_amount:.2f}")
                        continue
                    
                    # Skip if no meaningful order_amount
                    if order_amount < 0.10:
                        logger.info(f"      ⏭️  Skipping - dust order (amount < $0.10)")
                        continue
                    
                    # This is our pending order!
                    recovered_order_id = order.get('order_id')
                    logger.info(f"   ✅ Selected order: {recovered_order_id}")

                if orders:
                    # Found pending order(s) on this market
                    logger.info(f"✅ Found {len(orders)} pending order(s) on market #{market_id}")
                    
                    # Find order with non-zero amount (skip dust/old orders)
                    recovered_order = None
                    for order in orders:
                        # CRITICAL: Extract order amount from correct API field
                        # API returns different field names depending on order type:
                        # - 'order_amount' = total USDT value (main field for BUY orders)
                        # - 'maker_amount' = deprecated/old field
                        # - 'amount' = not present in current API
                        order_amount_str = order.get('order_amount', 0)
                        maker_amount_str = order.get('maker_amount', 0) 
                        amount_str = order.get('amount', 0)

                        # Try order_amount first (correct field for BUY orders)
                        if order_amount_str and order_amount_str != 'N/A':
                            try:
                                amount = float(order_amount_str)
                            except (ValueError, TypeError):
                                amount = 0.0
                        else:
                            # Fallback to other fields
                            try:
                                amount = float(maker_amount_str or amount_str or 0)
                            except (ValueError, TypeError):
                                amount = 0.0

                        logger.debug(f"   Order amount extracted: ${amount:.2f}")

                        if amount >= 0.10:  # Minimum meaningful order size
                            recovered_order = order
                            logger.info(f"   ✅ Selected order with amount: ${amount:.2f}")
                            break
                    
                    if not recovered_order:
                        logger.warning(f"⚠️ All {len(orders)} pending orders are dust (amount < $0.10)")
                        logger.info("   No real order to recover - checking if position exists...")
                        # Kod sprawdzający position (jak już jest poniżej)
                        # ...
                        return True
                    recovered_order_id = recovered_order.get('order_id')
                    
                    logger.info(f"   Order ID: {recovered_order_id}")
                    logger.info(f"   Side: {recovered_order.get('side', 'UNKNOWN')}")
                    logger.info(f"   Price: ${float(recovered_order.get('price', 0)):.4f}")
                    logger.info(f"   Amount: ${float(recovered_order.get('maker_amount', 0)):.2f}")
                    logger.info("")
                    
                    # Update state with recovered order_id
                    position['order_id'] = recovered_order_id


                    # CRITICAL FIX: Recover token_id from market details
                    # Without valid token_id, liquidity checks will crash
                    logger.info("🔍 Recovering token_id from market details...")

                    try:
                        # Extract outcome side from recovered order
                        # API returns outcome_side_enum: "Yes" or "No" (capitalized)
                        outcome_side_enum = recovered_order.get('outcome_side_enum', 'Yes')
                        logger.debug(f"   Outcome side: {outcome_side_enum}")
                        
                        # Fetch market using EXISTING get_market() method
                        market_details = self.client.get_market(market_id)
                        
                        if not market_details:
                            logger.warning(f"   ⚠️ Could not fetch market #{market_id} details")
                            token_id = 'unknown'
                            position['token_id'] = token_id
                        else:
                            # Extract correct token_id based on outcome side
                            # Market dict has: 'yes_token_id' and 'no_token_id' fields
                            if outcome_side_enum.lower() == 'yes':
                                token_id = market_details.get('yes_token_id', '')
                            else:
                                token_id = market_details.get('no_token_id', '')
                            
                            if token_id:
                                logger.info(f"   ✅ Recovered token_id: {token_id[:20] if len(token_id) > 20 else token_id}...")
                                position['token_id'] = token_id
                                position['outcome_side'] = outcome_side_enum
                            else:
                                logger.warning(f"   ⚠️ No token_id found in market details")
                                token_id = 'unknown'
                                position['token_id'] = token_id

                    except Exception as e:
                        logger.warning(f"   ⚠️ Failed to recover token_id: {e}")
                        import traceback
                        logger.debug(traceback.format_exc())
                        token_id = 'unknown'
                        position['token_id'] = token_id

                    self.state_manager.save_state(self.state)

                    logger.info("✅ order_id recovered and saved to state")
                    logger.info("📍 Continuing with normal BUY monitoring...")
                    logger.info("")

                    # Update local variable for monitoring below
                    order_id = recovered_order_id

                    # Fall through to normal monitoring code below
                    
                else:
                    # No pending orders found - check if already filled
                    logger.warning("⚠️ No pending orders found on this market")
                    logger.info("   Checking if order already filled...")
                    
                    verified_shares = self.client.get_position_shares(
                        market_id=market_id,
                        outcome_side="YES"
                    )
                    tokens = float(verified_shares)
                    
                    if tokens >= 1.0:
                        logger.info(f"✅ Order already filled! Found {tokens:.4f} tokens")
                        logger.info("   Skipping monitoring - moving to BUY_FILLED")
                        
                        # Update state with filled data
                        position['filled_amount'] = tokens
                        position['avg_fill_price'] = position.get('price', 0.01)
                        position['filled_usdt'] = tokens * position['avg_fill_price']
                        position['fill_timestamp'] = get_timestamp()
                        
                        self.state['stage'] = 'BUY_FILLED'
                        self.state_manager.save_state(self.state)
                        return True
                    else:
                        logger.warning(f"⚠️ No pending order AND no filled position")
                        logger.warning(f"   Order may have been cancelled or doesn't exist")
                        logger.info("   Resetting to SCANNING to find new market")
                        
                        self.state_manager.reset_position(self.state)
                        self.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.state)
                        return True
                        
            except Exception as e:
                logger.error(f"❌ Could not recover order_id: {e}")
                logger.info("   Resetting to SCANNING")
                
                self.state_manager.reset_position(self.state)
                self.state['stage'] = 'SCANNING'
                self.state_manager.save_state(self.state)
                return True
        
        # CRITICAL: If we recovered order_id above, this check now passes
        # and we continue with normal monitoring
        
        # SELF-HEALING: Verify order is still active before starting monitor
        logger.info("🔍 Verifying order status before monitoring...")
        try:
            order_status = self.client.get_order_status(order_id)
            
            # If order doesn't exist or is in terminal state (can't be monitored)
            # Status codes: PENDING, FILLED, PARTIALLY_FILLED, CANCELLED
            terminal_statuses = ['CANCELLED', 'FILLED']
            
            if order_status is None or order_status in terminal_statuses:
                if order_status == 'CANCELLED':
                    logger.warning(f"⚠️ BUY order is CANCELLED")
                elif order_status == 'FILLED':
                    logger.info(f"✅ BUY order already completed")
                else:
                    logger.warning("⚠️ BUY order not found in API")
                
                logger.info("🔄 Checking if position exists (tokens to sell)...")
                
                # Check if we have tokens from this position
                # RETRY LOGIC: Position may not be visible immediately after fill
                verified_shares = None
                max_retries = 3
                retry_delay = 2  # seconds

                for attempt in range(1, max_retries + 1):
                    verified_shares = self.client.get_position_shares(
                        market_id=market_id,
                        outcome_side="YES"
                    )
                    tokens = float(verified_shares)
                    
                    if tokens > 0:
                        logger.info(f"✅ Position found on attempt {attempt}: {tokens:.4f} tokens")
                        break
                    
                    if attempt < max_retries:
                        logger.info(f"⚠️ Attempt {attempt}/{max_retries}: Position not visible yet")
                        logger.info(f"   Retrying in {retry_delay} seconds...")
                        import time
                        time.sleep(retry_delay)
                    else:
                        logger.warning(f"⚠️ After {max_retries} attempts, still no position")

                if verified_shares is None:
                    tokens = 0.0
                else:
                    tokens = float(verified_shares)
                
                if tokens >= 1.0:  # Have significant position
                    outcome_side = position.get('outcome_side', 'YES')
                    logger.info(f"✅ Found position with {tokens:.4f} {outcome_side} tokens")
                    
                    if order_status in ['FILLED', 'PARTIALLY_FILLED']:
                        logger.info(f"   Order was {order_status} - switching to BUY_FILLED")
                    else:
                        logger.info(f"   Order was {order_status or 'not found'} but position exists")
                        logger.info(f"   This may be partial fill - switching to SELL")
                    
                    # Update state as if BUY was filled
                    position['filled_amount'] = tokens
                    position['avg_fill_price'] = position.get('price', 0.01)
                    position['filled_usdt'] = tokens * position['avg_fill_price']
                    position['fill_timestamp'] = get_timestamp()
                    
                    self.state['stage'] = 'BUY_FILLED'
                    self.state_manager.save_state(self.state)
                    return True
                    
                else:
                    logger.warning(f"⚠️ No significant position found (only {tokens:.4f} tokens)")
                    
                    # CRITICAL: This may be API timing delay!
                    # Order status updated faster than position data
                    if order_status == 'FILLED':
                        logger.info(f"   Order status='FILLED' but position not visible yet")
                        logger.info(f"   This is likely API timing delay (position update lag)")
                        logger.info(f"   🔄 RETRYING: Will check again in next monitoring cycle")
                        logger.info(f"   Bot will proceed to normal monitoring which includes retry logic")
                        
                        # DON'T reset! Let monitor handle this with retries
                        # Normal monitoring has fill checks that will eventually see the position
                        logger.info(f"✅ Order is active (timing issue) - proceeding to monitor")
                        # Fall through to normal monitoring code below
                        
                    elif order_status == 'CANCELLED':
                        logger.info(f"   Order was CANCELLED without fill - reset to find new market")
                        
                        self.state_manager.reset_position(self.state)
                        self.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.state)
                        return True
                        
                    else:
                        logger.warning(f"   Order not found in API and no position exists")
                        logger.info(f"   Resetting to SCANNING for new market")
                        
                        self.state_manager.reset_position(self.state)
                        self.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.state)
                        return True
            
            # Order exists and is active - proceed with normal monitoring
            logger.info(f"✅ Order is active (status: {order_status}) - starting monitor")
                    
        except Exception as e:
            logger.warning(f"⚠️ Could not verify order status: {e}")
            logger.info("   Proceeding with normal monitoring (may fail if order doesn't exist)")
        
        # Calculate timeout based on when order was originally placed
        timeout_hours = self.config['BUY_ORDER_TIMEOUT_HOURS']

        # IMPORTANT: Use placed_at from state if available (handles bot restarts)
        placed_at_str = position.get('placed_at')
        if placed_at_str:
            try:
                # Parse ISO format timestamp (from get_timestamp())
                placed_at = datetime.fromisoformat(placed_at_str.replace('Z', '+00:00'))
                timeout_at = placed_at + timedelta(hours=timeout_hours)
                logger.debug(f"Using placed_at from state: {placed_at_str}")
                logger.debug(f"Timeout at: {timeout_at.strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception as e:
                logger.warning(f"Could not parse placed_at '{placed_at_str}': {e}")
                logger.info("Falling back to current time for timeout calculation")
                timeout_at = datetime.now() + timedelta(hours=timeout_hours)
        else:
            # Fallback: use current time (shouldn't happen in normal flow)
            logger.debug("No placed_at in state, using current time for timeout")
            timeout_at = datetime.now() + timedelta(hours=timeout_hours)

        # Create monitor and start monitoring
        monitor = BuyMonitor(self.config, self.client, self.state, heartbeat_callback=self._check_and_send_heartbeat)

        result = monitor.monitor_until_filled(order_id, timeout_at)
        
        status = result['status']
        
        # Handle different outcomes
        if status == 'filled':
            logger.info("✅ BUY order filled!")
            
            # Update state with fill data
            # CRITICAL FIX: Verify filled_amount from actual position, not just order data
            # API get_order() may return filled_shares=0 or wrong field name
            filled_from_monitor = result.get('filled_amount', 0)
            
            # Double-check with actual position shares
            try:
                market_id = position['market_id']
                outcome_side = position.get('outcome_side', 'YES')
                verified_shares = self.client.get_position_shares(
                    market_id=market_id,
                    outcome_side=outcome_side
                )
                verified_amount = float(verified_shares)
                
                if verified_amount > 0:
                    logger.info(f"✅ Verified filled_amount from position: {verified_amount:.10f} tokens")
                    position['filled_amount'] = verified_amount
                else:
                    logger.warning(f"⚠️ Position check returned 0, using monitor value: {filled_from_monitor}")
                    position['filled_amount'] = filled_from_monitor
                    
            except Exception as e:
                logger.warning(f"⚠️ Could not verify position, using monitor value: {e}")
                position['filled_amount'] = filled_from_monitor
            
            position['avg_fill_price'] = result.get('avg_fill_price', position.get('price', 0))
            position['filled_usdt'] = result.get('filled_usdt', 0)
            position['fill_timestamp'] = result.get('fill_timestamp')
            
            self.state['stage'] = 'BUY_FILLED'
            self.state_manager.save_state(self.state)

            
            return True
        
        elif status in ['cancelled', 'canceled', 'expired', 'timeout', 'deteriorated']:  # Support both US/UK spelling
            logger.warning(f"BUY order {status}: {result.get('reason')}")
            logger.info("Resetting to find new market...")

            # Cancel order if still active
            if status in ['timeout', 'deteriorated']:
                try:
                    self.client.cancel_order(order_id)
                    logger.info("Order cancelled")
                except:
                    pass
            
            # Reset position and go back to scanning
            self.state_manager.reset_position(self.state)
            self.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.state)
            
            return True
        
        else:
            logger.error(f"Unexpected monitoring result: {status}")
            return False
    
    def _handle_buy_filled(self) -> bool:
        """
        BUY_FILLED stage: BUY filled, ready to place SELL.
        
        Transitions to: SELL_PLACED
        """
        logger.info("💰 BUY_FILLED - Preparing SELL order...")
        
        position = self.state['current_position']
        market_id = position['market_id']
        token_id = position.get('token_id')
        filled_amount = position['filled_amount']
        
        # =====================================================================
        # CRITICAL VALIDATION: Check token_id is valid string (not int/None)
        # =====================================================================
        logger.info(f"🔍 DEBUG: token_id={token_id}, type={type(token_id).__name__}")
        
        if not token_id or isinstance(token_id, int):
            logger.error(f"❌ Invalid token_id detected: {token_id} (type: {type(token_id).__name__})")
            logger.error(f"   This is legacy bug from old state.json!")
            logger.info(f"🔄 Attempting recovery from market details...")
            
            try:
                # Fetch market to get correct token_id
                market_details = self.client.get_market(market_id)
                
                if not market_details:
                    logger.error(f"   ❌ Could not fetch market #{market_id}")
                    logger.error(f"   Cannot place SELL without valid token_id")
                    logger.info(f"   Resetting to SCANNING")
                    
                    self.state_manager.reset_position(self.state)
                    self.state['stage'] = 'SCANNING'
                    self.state_manager.save_state(self.state)
                    return False
                
                # Get outcome_side from position (defaults to YES if missing)
                outcome_side = position.get('outcome_side', 'YES')
                logger.info(f"   Position outcome_side: {outcome_side}")
                
                # Extract correct token_id
                if outcome_side.upper() == 'YES':
                    token_id = market_details.get('yes_token_id', '')
                else:
                    token_id = market_details.get('no_token_id', '')
                
                if not token_id:
                    logger.error(f"   ❌ Market details missing token_id field!")
                    logger.error(f"   Cannot proceed without valid token_id")
                    logger.info(f"   Resetting to SCANNING")
                    
                    self.state_manager.reset_position(self.state)
                    self.state['stage'] = 'SCANNING'
                    self.state_manager.save_state(self.state)
                    return False
                
                logger.info(f"   ✅ Recovered token_id: {token_id[:20]}...")
                
                # Update state with valid token_id
                position['token_id'] = token_id
                self.state_manager.save_state(self.state)
                
                logger.info(f"   💾 State updated with valid token_id")
                
            except Exception as e:
                logger.error(f"   ❌ Recovery failed: {e}")
                logger.error(f"   Cannot place SELL without valid token_id")
                logger.info(f"   Resetting to SCANNING")
                
                self.state_manager.reset_position(self.state)
                self.state['stage'] = 'SCANNING'
                self.state_manager.save_state(self.state)
                return False
        
        # Validation passed - token_id is now valid string
        logger.info(f"✅ token_id validated: {token_id[:20]}...")

        # =====================================================================
        # MANUAL SALE DETECTION: Check if position was sold manually
        # =====================================================================
        # If user manually sold tokens via web interface, state.json will have
        # incorrect filled_amount. We need to detect this and reset state.
        logger.info("🔍 Verifying actual position vs state.json...")

        try:
            outcome_side = position.get('outcome_side', 'YES')
            verified_shares = self.client.get_position_shares(
                market_id=market_id,
                outcome_side=outcome_side
            )
            actual_tokens = float(verified_shares)
            expected_tokens = filled_amount

            logger.info(f"   Expected: {expected_tokens:.4f} tokens (from state.json)")
            logger.info(f"   Actual: {actual_tokens:.4f} tokens (from API)")

            # Check if actual position is significantly smaller than expected
            if expected_tokens > 0:
                difference = expected_tokens - actual_tokens
                difference_pct = (difference / expected_tokens) * 100

                logger.info(f"   Difference: {difference:.4f} tokens ({difference_pct:.1f}%)")

                # If >95% of tokens are missing, position was likely sold manually
                MANUAL_SALE_THRESHOLD = 95.0

                if difference_pct > MANUAL_SALE_THRESHOLD:
                    logger.warning("=" * 70)
                    logger.warning("⚠️  MANUAL SALE DETECTED!")
                    logger.warning(f"   Expected {expected_tokens:.4f} tokens but found only {actual_tokens:.4f}")
                    logger.warning(f"   {difference_pct:.1f}% of position is missing (threshold: {MANUAL_SALE_THRESHOLD}%)")
                    logger.warning("   Position was likely sold manually via web interface")
                    logger.warning("=" * 70)
                    logger.info("")

                    # Check if remaining tokens are dust (< 1.0)
                    if actual_tokens < 1.0:
                        logger.info("💡 Action: Remaining position is dust - resetting to SCANNING")
                        logger.info(f"   Dust positions ({actual_tokens:.4f} tokens) cannot be sold")
                        logger.info(f"   API requires minimum 1.0 tokens for SELL orders")
                    else:
                        logger.info("💡 Action: Resetting to SCANNING to find new market")
                        logger.info(f"   Manual sale has left {actual_tokens:.4f} tokens")

                    logger.info("")

                    # Reset and find new market
                    self.state_manager.reset_position(self.state)
                    self.state['stage'] = 'SCANNING'
                    self.state_manager.save_state(self.state)
                    return True

                # If difference is moderate (5-95%), update filled_amount to actual
                elif difference_pct > 5.0:
                    logger.warning(f"⚠️  Position mismatch: {difference_pct:.1f}% difference")
                    logger.info(f"   Updating filled_amount to actual: {actual_tokens:.4f}")
                    filled_amount = actual_tokens
                    position['filled_amount'] = actual_tokens
                    self.state_manager.save_state(self.state)

        except Exception as e:
            logger.warning(f"⚠️ Could not verify position (non-critical): {e}")
            logger.info("   Proceeding with state.json values")

        # =====================================================================
        # DUST POSITION CHECK: Verify position is large enough to sell
        # =====================================================================
        # API requires makerAmountInBaseToken >= 1.0 for SELL orders
        # Positions < 1.0 shares (dust) cannot be sold and should be abandoned
        MIN_SELLABLE_SHARES = 1.0

        if filled_amount < MIN_SELLABLE_SHARES:
            logger.warning("=" * 70)
            logger.warning(f"⚠️  DUST POSITION DETECTED!")
            logger.warning(f"   Position has {filled_amount:.4f} shares (< {MIN_SELLABLE_SHARES} minimum)")
            logger.warning(f"   API requires makerAmountInBaseToken >= 1.0 for SELL orders")
            logger.warning(f"   This position cannot be sold - likely from partial fill")
            logger.warning("=" * 70)
            logger.info("")
            logger.info("💡 Action: Abandoning dust position and resetting to SCANNING")
            logger.info("   Dust positions are typically worth < $1 and not worth selling")
            logger.info("")

            # Reset and find new market
            self.state_manager.reset_position(self.state)
            self.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.state)
            return True

        logger.info(f"✅ Position size OK: {filled_amount:.4f} shares (>= {MIN_SELLABLE_SHARES} minimum)")

        # SAFETY CHECK: Verify filled_amount is valid before attempting SELL
        if not filled_amount or filled_amount <= 0:
            logger.error(f"❌ Invalid filled_amount in state: {filled_amount}")
            logger.error(f"   Cannot place SELL with 0 tokens!")
            logger.info(f"🔄 Re-checking position from API...")
            
            try:
                outcome_side = position.get('outcome_side', 'YES')
                verified_shares = self.client.get_position_shares(
                    market_id=market_id,
                    outcome_side=outcome_side
                )
                filled_amount = float(verified_shares)
                
                if filled_amount > 0:
                    logger.info(f"✅ Recovered filled_amount from position: {filled_amount:.10f}")
                    position['filled_amount'] = filled_amount
                    
                    # ALSO recover avg_fill_price if missing (required by SellMonitor)
                    # Use BUY order limit price as fallback - close enough for stop-loss
                    if not position.get('avg_fill_price') or position.get('avg_fill_price') == 0:
                        fallback_price = position.get('price', 0)
                        if fallback_price > 0:
                            logger.info(f"✅ Using BUY order price as avg_fill_price: ${fallback_price:.4f}")
                            logger.info(f"   (This is fallback - normally set by BuyMonitor)")
                            position['avg_fill_price'] = fallback_price
                        else:
                            logger.warning(f"⚠️ No valid price found - using minimal fallback $0.01")
                            logger.warning(f"   Stop-loss may not work correctly with fallback price")
                            position['avg_fill_price'] = 0.01
                    
                    self.state_manager.save_state(self.state)
                else:
                    logger.error(f"❌ Position still shows 0 tokens!")
                    logger.error(f"   This indicates BUY order may not be truly filled")
                    logger.error(f"   Resetting to SCANNING to avoid stuck loop")
                    
                    self.state_manager.reset_position(self.state)
                    self.state['stage'] = 'SCANNING'
                    self.state_manager.save_state(self.state)
                    return True
                    
            except Exception as e:
                logger.error(f"❌ Failed to verify position: {e}")
                logger.error(f"   Resetting to SCANNING")
                
                self.state_manager.reset_position(self.state)
                self.state['stage'] = 'SCANNING'
                self.state_manager.save_state(self.state)
                return True
        
        try:
            # Get fresh orderbook for SELL pricing
            fresh_orderbook = self.scanner.get_fresh_orderbook(market_id, token_id)
            
            if not fresh_orderbook:
                logger.error("Failed to get orderbook for SELL")
                return False
            
            best_bid = fresh_orderbook['best_bid']
            best_ask = fresh_orderbook['best_ask']
            
            # ================================================================
            # HANDLE EDGE CASE: Empty orderbook (99:1 lopsided market)
            # ================================================================
            # When market is heavily one-sided (e.g. 99% UP, 1% DOWN),
            # there may be NO asks because nobody wants to bet on losing side.
            # In this case, we use fallback prices to still place SELL order.
            
            if not best_ask or best_ask == 0:
                logger.warning("⚠️ ⚠️  No asks in orderbook (lopsided 99:1 market)")
                logger.warning("   Everyone betting same outcome - no counter-offers")
                logger.warning("   Using fallback: SELL at $0.99 (near-maximum price)")
                best_ask = 0.96 # Fallback to near-max price
                
                # If no bid either, create synthetic spread
                if not best_bid or best_bid == 0:
                    logger.warning("   No bids either - using synthetic bid $0.95")
                    best_bid = 0.95
            
            # Validate we have valid prices
            if best_bid <= 0 or best_ask <= 0:
                logger.error(f"❌ Invalid orderbook prices after fallback:")
                logger.error(f"   Bid: {best_bid}, Ask: {best_ask}")
                logger.error(f"   Cannot place SELL order without valid prices")
                return False
            
            logger.info(f"   Bid: {format_price(best_bid)} | Ask: {format_price(best_ask)}")
            
            # Calculate SELL price
            sell_price = self.pricing.calculate_sell_price(best_bid, best_ask)
            
            logger.info(f"   SELL price: {format_price(sell_price)}")
            
            # Place SELL order
            logger.info("📝 Placing SELL order...")
            
            result = self.order_manager.place_sell(
                market_id=market_id,
                token_id=token_id,
                price=sell_price,
                amount_tokens=filled_amount
            )
            
            if not result:
                logger.error("Failed to place SELL order")
                return False
            
            sell_order_id = result.get('order_id', result.get('orderId', 'unknown'))
            
            logger.info(f"✅ SELL order placed: {sell_order_id}")
            
            # Update state
            position['sell_order_id'] = sell_order_id
            position['sell_price'] = sell_price
            position['sell_placed_at'] = get_timestamp()

            self.state['stage'] = 'SELL_PLACED'
            self.state_manager.save_state(self.state)

            # Send Telegram notification: SELL order placed
            self.telegram.send_state_change(
                new_stage='SELL_PLACED',
                market_id=position.get('market_id'),
                market_title=position.get('market_title'),
                price=sell_price,
                amount=position.get('filled_amount', 0) * sell_price
            )

            return True
            
        except Exception as e:
            logger.exception(f"Error placing SELL: {e}")
            return False
            
    def _handle_sell_placed(self) -> bool:
        """
        SELL_PLACED stage: SELL order placed, ready to monitor.
        
        Transitions to: SELL_MONITORING
        """
        logger.info("📋 SELL_PLACED - Transitioning to monitoring")
        
        # Simply transition to monitoring
        self.state['stage'] = 'SELL_MONITORING'
        self.state_manager.save_state(self.state)
        
        return True
    
    def _handle_sell_monitoring(self) -> bool:
        """
        SELL_MONITORING stage: Monitor SELL order until filled.
        
        Transitions to: COMPLETED (if filled)
        Transitions to: BUY_FILLED (if cancelled/expired - retry)
        Transitions to: SCANNING (if stop-loss/deteriorated)
        """
        logger.info("⏳ SELL_MONITORING - Waiting for fill...")
        
        position = self.state['current_position']
        
        # CRITICAL: Verify avg_fill_price exists before SellMonitor starts
        # (SellMonitor requires this for stop-loss calculation)
        if not position.get('avg_fill_price') or position.get('avg_fill_price') == 0:
            logger.warning(f"⚠️ avg_fill_price missing in SELL_MONITORING stage!")
            logger.info(f"🔄 Recovering avg_fill_price from BUY order...")
            
            fallback_price = position.get('price', 0)
            if fallback_price > 0:
                logger.info(f"✅ Using BUY order price as avg_fill_price: ${fallback_price:.4f}")
                logger.info(f"   (Recovery after restart - normally set by BuyMonitor)")
                position['avg_fill_price'] = fallback_price
            else:
                logger.error(f"❌ Cannot recover avg_fill_price - no valid price in state!")
                logger.error(f"   Stop-loss will not work without valid buy price")
                logger.error(f"   Resetting to SCANNING to avoid errors")
                
                self.state_manager.reset_position(self.state)
                self.state['stage'] = 'SCANNING'
                self.state_manager.save_state(self.state)
                return True
        
        # ALSO verify filled_amount (shouldn't be 0 at this stage)
        filled_amount = position.get('filled_amount', 0)
        if not filled_amount or filled_amount <= 0:
            logger.error(f"❌ Invalid filled_amount in SELL_MONITORING: {filled_amount}")
            logger.info(f"🔄 Re-checking position from API...")
            
            try:
                outcome_side = position.get('outcome_side', 'YES')
                verified_shares = self.client.get_position_shares(
                    market_id=market_id,
                    outcome_side=outcome_side
                )
                filled_amount = float(verified_shares)
                
                if filled_amount > 0:
                    logger.info(f"✅ Recovered filled_amount: {filled_amount:.10f}")
                    position['filled_amount'] = filled_amount
                    self.state_manager.save_state(self.state)
                else:
                    logger.error(f"❌ No position found - resetting to SCANNING")
                    self.state_manager.reset_position(self.state)
                    self.state['stage'] = 'SCANNING'
                    self.state_manager.save_state(self.state)
                    return True
            except Exception as e:
                logger.error(f"❌ Failed to verify position: {e}")
                self.state_manager.reset_position(self.state)
                self.state['stage'] = 'SCANNING'
                self.state_manager.save_state(self.state)
                return True
        
        sell_order_id = position['sell_order_id']
        market_id = position['market_id']
        
        # SELF-HEALING: Verify order is still active before starting monitor
        logger.info("🔍 Verifying SELL order status before monitoring...")
        try:
            # Get full order details (not just status string)
            order_details = self.client.get_order(sell_order_id)
            
            # Initialize variables (needed for scope outside if/else)
            order_is_terminal = False
            is_cancelled = False
            is_fully_filled = False
            order_status = 'UNKNOWN'
            order_filled_amount = 0.0
            order_amount = 0.0
            fill_percentage = 0.0
            
            if not order_details:
                logger.warning("⚠️ SELL order not found in API")
                order_is_terminal = True
            else:
                order_status = order_details.get('status_str', 'UNKNOWN')
                order_filled_amount = float(order_details.get('filled_amount', 0) or 0)
                order_amount = float(order_details.get('order_amount', 0) or 0)
                
                logger.info(f"   Order status: {order_status}")
                logger.info(f"   Filled: ${order_filled_amount:.2f} / ${order_amount:.2f}")
                
                # Calculate fill percentage
                fill_percentage = (order_filled_amount / order_amount * 100) if order_amount > 0 else 0
                
                # Check if order is TRULY terminal
                # Don't trust status='FILLED' alone - check actual filled_amount
                is_fully_filled = (fill_percentage >= 99.0)  # 99%+ = consider fully filled
                is_cancelled = (order_status == 'CANCELLED')
                
                if is_cancelled:
                    logger.warning(f"⚠️ SELL order was CANCELLED")
                    order_is_terminal = True
                elif is_fully_filled:
                    logger.info(f"✅ SELL order is fully FILLED ({fill_percentage:.1f}% = ${order_filled_amount:.2f})")
                    order_is_terminal = True
                else:
                    # Order is NOT terminal (0-98% filled) - still active
                    logger.info(f"✅ Order is active ({fill_percentage:.1f}% filled) - starting monitor")
                    order_is_terminal = False
            
            # If order is terminal, check position and decide what to do
            if order_is_terminal:
                logger.info("🔄 Checking if position still exists...")

                # Check if we still have tokens
                outcome_side = position.get('outcome_side', 'YES')
                verified_shares = self.client.get_position_shares(
                    market_id=market_id,
                    outcome_side=outcome_side
                )
                tokens = float(verified_shares)
                expected_tokens = position.get('filled_amount', 0)

                logger.info(f"   Expected: {expected_tokens:.4f} tokens (from state.json)")
                logger.info(f"   Actual: {tokens:.4f} tokens (from API)")

                # Check for manual sale (significant drop in position)
                if expected_tokens > 0:
                    difference = expected_tokens - tokens
                    difference_pct = (difference / expected_tokens) * 100

                    logger.info(f"   Difference: {difference:.4f} tokens ({difference_pct:.1f}%)")

                    MANUAL_SALE_THRESHOLD = 95.0

                    if difference_pct > MANUAL_SALE_THRESHOLD:
                        logger.warning("=" * 70)
                        logger.warning("⚠️  MANUAL SALE DETECTED!")
                        logger.warning(f"   Expected {expected_tokens:.4f} tokens but found only {tokens:.4f}")
                        logger.warning(f"   {difference_pct:.1f}% of position is missing (threshold: {MANUAL_SALE_THRESHOLD}%)")
                        logger.warning("   Position was likely sold manually via web interface")
                        logger.warning("=" * 70)
                        logger.info("")
                        logger.info("💡 Action: Manual sale detected - resetting to SCANNING")
                        logger.info("")

                        # Reset and find new market
                        self.state_manager.reset_position(self.state)
                        self.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.state)
                        return True

                if tokens >= 1.0:  # Still have significant tokens
                    logger.info(f"✅ Still have {tokens:.4f} tokens")
                    logger.info(f"   Order is terminal but tokens remain - going back to BUY_FILLED to place new SELL")

                    # Update filled_amount in case it changed
                    position['filled_amount'] = tokens

                    # Remove old SELL order data
                    if 'sell_order_id' in position:
                        del position['sell_order_id']
                    if 'sell_price' in position:
                        del position['sell_price']

                    self.state['stage'] = 'BUY_FILLED'
                    self.state_manager.save_state(self.state)
                    return True

                else:
                    logger.warning(f"⚠️ No significant tokens found (only {tokens:.4f})")

                    if order_details and is_fully_filled:
                        logger.info(f"   SELL order completed successfully")
                        logger.info("   Marking as COMPLETED")
                        self.state['stage'] = 'COMPLETED'
                        self.state_manager.save_state(self.state)
                        return True
                    else:
                        logger.info(f"   Order terminal without completion - resetting to SCANNING")

                        self.state_manager.reset_position(self.state)
                        self.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.state)
                        return True
            
            # If we reach here, order is NOT terminal - proceed with monitoring
                    
        except Exception as e:
            logger.warning(f"⚠️ Could not verify SELL order status: {e}")
            logger.info("   Proceeding with normal monitoring (may fail if order doesn't exist)")
        
        # Calculate timeout based on when SELL order was originally placed
        timeout_hours = self.config['SELL_ORDER_TIMEOUT_HOURS']

        # IMPORTANT: Use sell_placed_at from state if available (handles bot restarts)
        sell_placed_at_str = position.get('sell_placed_at')
        if sell_placed_at_str:
            try:
                # Parse ISO format timestamp (from get_timestamp())
                sell_placed_at = datetime.fromisoformat(sell_placed_at_str.replace('Z', '+00:00'))
                timeout_at = sell_placed_at + timedelta(hours=timeout_hours)
                logger.debug(f"Using sell_placed_at from state: {sell_placed_at_str}")
                logger.debug(f"Timeout at: {timeout_at.strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception as e:
                logger.warning(f"Could not parse sell_placed_at '{sell_placed_at_str}': {e}")
                logger.info("Falling back to current time for timeout calculation")
                timeout_at = datetime.now() + timedelta(hours=timeout_hours)
        else:
            # Fallback: use current time (shouldn't happen in normal flow)
            logger.debug("No sell_placed_at in state, using current time for timeout")
            timeout_at = datetime.now() + timedelta(hours=timeout_hours)

        # Create monitor and start monitoring
        monitor = SellMonitor(self.config, self.client, self.state, heartbeat_callback=self._check_and_send_heartbeat)

        result = monitor.monitor_until_filled(sell_order_id, timeout_at)
        
        status = result['status']
        
        # Handle different outcomes
        if status == 'filled':
            logger.info("✅ SELL order filled!")
            
            # Update state with fill data
            position['sell_filled_amount'] = result['filled_amount']
            position['avg_sell_price'] = result['avg_fill_price']
            position['sell_proceeds'] = result['filled_usdt']
            position['sell_fill_timestamp'] = result['fill_timestamp']
            
            # Calculate P&L
            pnl = self.tracker.calculate_pnl(
                buy_cost_usdt=position['filled_usdt'],
                buy_tokens=position['filled_amount'],
                buy_price=position['avg_fill_price'],
                sell_tokens=result['filled_amount'],
                sell_price=result['avg_fill_price']
            )
            
            # Display P&L
            self.tracker.display_pnl(pnl)
            
            # Add to history
            self.tracker.add_to_history(pnl, position['market_id'])
            
            # Update statistics
            self._update_statistics(pnl)
            
            self.state['stage'] = 'COMPLETED'
            self.state_manager.save_state(self.state)
            
            return True
        
        elif status in ['cancelled', 'canceled', 'expired']:  # Support both US/UK spelling
            logger.warning(f"SELL order {status}: {result.get('reason')}")
            logger.info("Retrying SELL order...")

            # Go back to BUY_FILLED to place new SELL
            self.state['stage'] = 'BUY_FILLED'

            # Clear old SELL data
            if 'sell_order_id' in position:
                del position['sell_order_id']
            if 'sell_price' in position:
                del position['sell_price']

            self.state_manager.save_state(self.state)

            return True
        
        elif status == 'stop_loss_triggered':
            logger.warning(f"🛑 Stop-loss triggered: {result.get('reason')}")
            logger.info("Position closed at loss - finding new market...")

            # Send Telegram notification: Stop-loss triggered
            current_price = result.get('current_price', 0)
            buy_price = position.get('avg_fill_price', 0)
            pnl_percent = result.get('pnl_percent', 0)

            self.telegram.send_stop_loss(
                market_id=position.get('market_id', 0),
                market_title=position.get('market_title', 'Unknown market'),
                current_price=current_price,
                buy_price=buy_price,
                pnl_percent=pnl_percent,
                action='triggered'
            )

            # TODO: Could calculate P&L here if stop-loss order filled
            # For now, just reset and move on

            # Update statistics (record as loss)
            stats = self.state['statistics']
            stats['losses'] += 1
            stats['consecutive_losses'] += 1
            
            # Reset position
            self.state_manager.reset_position(self.state)
            self.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.state)
            
            return True
        
        elif status in ['timeout', 'deteriorated']:
            logger.warning(f"SELL order {status}: {result.get('reason')}")
            logger.info("Cancelling and finding new market...")
            
            # Cancel order if still active
            try:
                self.client.cancel_order(sell_order_id)
                logger.info("Order cancelled")
            except:
                pass
            
            # Reset position and go back to scanning
            self.state_manager.reset_position(self.state)
            self.state['stage'] = 'SCANNING'
            self.state_manager.save_state(self.state)
            
            return True
        
        else:
            logger.error(f"Unexpected monitoring result: {status}")
            return False
    
    def _handle_completed(self) -> bool:
        """
        COMPLETED stage: Trade cycle completed.

        Transitions to: IDLE (ready for new cycle)
        """
        logger.info("✅ COMPLETED - Trade cycle finished")

        # Reset position for new cycle
        self.state_manager.reset_position(self.state)
        self.state['stage'] = 'IDLE'
        self.state_manager.save_state(self.state)

        logger.info(f"📊 Total trades: {self.state['statistics']['total_trades']}")
        logger.info(f"💰 Total P&L: ${self.state['statistics']['total_pnl_usdt']:.2f}")
        logger.info("")

        # Send state change notification
        stats = self.state['statistics']
        self.telegram.send_state_change(
            new_stage='IDLE',
            market_id=None,
            market_title=f"Trade completed - {stats['total_trades']} total trades, ${stats['total_pnl_usdt']:.2f} P&L"
        )

        return True
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _update_statistics(self, pnl):
        """
        Update statistics after completed trade.

        Args:
            pnl: PositionPnL object
        """
        # Update separate P&L statistics file
        self.pnl_stats.update_after_trade(
            pnl_usdt=float(pnl.pnl),
            pnl_percent=float(pnl.pnl_percent)
        )

        # Also keep state.json statistics for backwards compatibility
        # (in case state.json is used elsewhere)
        stats = self.state['statistics']

        stats['total_trades'] += 1

        if pnl.is_profitable():
            stats['wins'] += 1
            stats['consecutive_losses'] = 0  # Reset streak
        else:
            stats['losses'] += 1
            stats['consecutive_losses'] += 1

        stats['total_pnl_usdt'] += float(pnl.pnl)
        stats['total_pnl_percent'] = (
            (stats['total_pnl_usdt'] / stats['total_trades'])
            if stats['total_trades'] > 0 else 0
        )

        stats['win_rate_percent'] = (
            (stats['wins'] / stats['total_trades'] * 100)
            if stats['total_trades'] > 0 else 0
        )

        self.state['last_updated_at'] = get_timestamp()

    def _check_and_send_heartbeat(self):
        """Check if heartbeat should be sent and send it if needed."""
        if self.heartbeat_interval_hours <= 0:
            return  # Heartbeat disabled

        from datetime import datetime

        now = datetime.now()

        # Send heartbeat if:
        # 1. Never sent before, OR
        # 2. Enough time has passed since last heartbeat
        should_send = (
            self.last_heartbeat is None or
            (now - self.last_heartbeat).total_seconds() >= self.heartbeat_interval_hours * 3600
        )

        if not should_send:
            return

        self._send_heartbeat_now()

    def _send_heartbeat_now(self):
        """Send heartbeat immediately (called by _check_and_send_heartbeat or on startup)."""
        from datetime import datetime

        now = datetime.now()

        # Gather information for heartbeat
        stage = self.state.get('stage', 'IDLE')
        position = self.state.get('current_position', {})
        market_info = None
        order_info = None
        position_value = 0.0

        # Get market info and order details if in active position
        if position and position.get('market_id'):
            try:
                market_id = position['market_id']
                token_id = position.get('token_id')
                market_title = position.get('market_title', f'Market #{market_id}')

                # Get orderbook using token_id (FIXED: was using market_id which doesn't work)
                orderbook = None
                if token_id:
                    orderbook = self.client.get_market_orderbook(token_id)

                if orderbook and 'bids' in orderbook and 'asks' in orderbook:
                    bids = orderbook['bids']
                    asks = orderbook['asks']

                    if bids and asks:
                        # Extract best prices
                        best_bid = float(bids[0].get('price', 0)) if isinstance(bids[0], dict) else float(bids[0][0])
                        best_ask = float(asks[0].get('price', 0)) if isinstance(asks[0], dict) else float(asks[0][0])
                        spread = best_ask - best_bid

                        # Build market info
                        market_info = {
                            'market_id': market_id,
                            'market_title': market_title,
                            'spread': spread,
                            'best_bid': best_bid,
                            'best_ask': best_ask
                        }

                        # Calculate position value
                        if 'filled_amount' in position:
                            # Estimate position value using mid-price
                            mid_price = (best_bid + best_ask) / 2
                            position_value = float(position['filled_amount']) * mid_price

                        # Get order details for active monitoring stages
                        if stage in ['BUY_MONITORING', 'SELL_MONITORING', 'BUY_PLACED', 'SELL_PLACED']:
                            order_id = None
                            if stage in ['BUY_MONITORING', 'BUY_PLACED']:
                                order_id = position.get('order_id')
                            elif stage in ['SELL_MONITORING', 'SELL_PLACED']:
                                order_id = position.get('sell_order_id')

                            if order_id and order_id != 'unknown':
                                try:
                                    order = self.client.get_order(order_id)
                                    if order:
                                        # Get order price and amounts
                                        our_price = float(order.get('price', position.get('price', 0)))
                                        order_amount = float(order.get('order_amount', 0))
                                        filled_amount = float(order.get('filled_amount', 0))

                                        # Side is numeric: 1=BUY, 2=SELL
                                        order_side_num = order.get('side', 1 if 'BUY' in stage else 2)
                                        order_side = 'BUY' if order_side_num == 1 else 'SELL'

                                        # Calculate order position in orderbook
                                        if order_side == 'BUY':
                                            distance = best_bid - our_price
                                            distance_pct = (distance / best_bid * 100) if best_bid > 0 else 0
                                            # Find our position in bids
                                            position_in_book = self._find_order_position_in_book(our_price, bids, 'bids')
                                        else:  # SELL
                                            distance = our_price - best_ask
                                            distance_pct = (distance / best_ask * 100) if best_ask > 0 else 0
                                            # Find our position in asks
                                            position_in_book = self._find_order_position_in_book(our_price, asks, 'asks')

                                        order_info = {
                                            'order_id': order_id,
                                            'side': order_side,
                                            'our_price': our_price,
                                            'order_amount': order_amount,
                                            'filled_amount': filled_amount,
                                            'filled_percent': (filled_amount / order_amount * 100) if order_amount > 0 else 0,
                                            'distance_from_best': distance,
                                            'distance_percent': distance_pct,
                                            'position_in_book': position_in_book
                                        }
                                except Exception as e:
                                    logger.debug(f"Could not fetch order details for heartbeat: {e}")

            except Exception as e:
                logger.debug(f"Could not fetch market info for heartbeat: {e}")

        # Get current balance
        try:
            balance = self.client.get_usdt_balance()
        except Exception as e:
            logger.debug(f"Could not fetch balance for heartbeat: {e}")
            balance = 0.0

        # Send heartbeat
        self.telegram.send_heartbeat(
            stage=stage,
            market_info=market_info,
            order_info=order_info,
            balance=balance,
            position_value=position_value
        )

        self.last_heartbeat = now
        logger.debug(f"💓 Heartbeat sent at {now.strftime('%H:%M:%S')}")

    def _find_order_position_in_book(self, our_price: float, book_side: list, side: str) -> dict:
        """
        Find where our order is positioned in the orderbook.

        Args:
            our_price: Our order price
            book_side: List of bids or asks from orderbook
            side: 'bids' or 'asks'

        Returns:
            Dictionary with position info and simple visualization
        """
        if not book_side:
            return {'position': 0, 'total_levels': 0, 'ahead_volume': 0}

        position = 0
        ahead_volume = 0.0
        levels_ahead = []

        # For bids: higher prices are better (descending order)
        # For asks: lower prices are better (ascending order)
        for i, level in enumerate(book_side):
            level_price = float(level.get('price', 0)) if isinstance(level, dict) else float(level[0])
            level_size = float(level.get('size', 0)) if isinstance(level, dict) else float(level[1])

            if side == 'bids':
                # For BUY orders: if level price is higher than ours, it's ahead
                if level_price > our_price:
                    position = i + 1
                    ahead_volume += level_size
                    if len(levels_ahead) < 5:  # Keep top 5 levels for visualization
                        levels_ahead.append({'price': level_price, 'size': level_size})
                else:
                    break
            else:  # asks
                # For SELL orders: if level price is lower than ours, it's ahead
                if level_price < our_price:
                    position = i + 1
                    ahead_volume += level_size
                    if len(levels_ahead) < 5:
                        levels_ahead.append({'price': level_price, 'size': level_size})
                else:
                    break

        return {
            'position': position,
            'total_levels': len(book_side),
            'ahead_volume': ahead_volume,
            'levels_ahead': levels_ahead
        }

    def _get_recent_logs(self, num_lines: int = 20) -> List[str]:
        """
        Get last N lines from log file.

        Args:
            num_lines: Number of lines to retrieve

        Returns:
            List of log lines (max num_lines)
        """
        from pathlib import Path

        # Try to read from log file
        log_file = Path(self.config.get('LOG_FILE', 'opinion_farming_bot.log'))

        if not log_file.exists():
            return ["Log file not found"]

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                # Read all lines and get last N
                lines = f.readlines()
                return [line.strip() for line in lines[-num_lines:]]

        except Exception as e:
            logger.debug(f"Could not read log file: {e}")
            return [f"Error reading logs: {e}"]

    def _display_session_summary(self):
        """Display summary of current session from separate P&L statistics file."""
        # Use the separate P&L statistics file (persists even if state.json is deleted)
        self.pnl_stats.display_summary(logger)


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("Use autonomous_bot_main.py to run the bot")
    print("This module requires full configuration and API client")