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
from typing import Dict, Any, Optional
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
                
                # Brief pause between cycles
                time.sleep(self.cycle_delay)
        
        except KeyboardInterrupt:
            logger.info("")
            logger.info("⛔ Bot stopped by user")
            logger.info("")
            self._display_session_summary()
            return 0
        
        except Exception as e:
            logger.exception(f"Unexpected error in main loop: {e}")
            return 1
        
        logger.info("")
        logger.info("✅ Bot execution completed")
        self._display_session_summary()
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
                positions = self.client.get_positions()
                
                if positions:
                    # We have positions but state says IDLE/SCANNING
                    # This is a CRITICAL inconsistency
                    logger.warning("=" * 60)
                    logger.warning("⚠️  CRITICAL: State inconsistency detected!")
                    logger.warning(f"   State says: {stage}")
                    logger.warning(f"   API shows: {len(positions)} active position(s)")
                    logger.warning("=" * 60)
                    
                    # Find first position with significant shares
                    for pos in positions:
                        market_id = pos.get('market_id')
                        shares = float(pos.get('shares_owned', 0))
                        
                        if shares >= 1.0:
                            logger.warning(f"🔄 AUTO-RECOVERY: Found position in market #{market_id}")
                            logger.warning(f"   Shares: {shares:.4f}")
                            logger.info(f"   Recovering to BUY_FILLED stage to handle SELL...")
                            
                            # Force state to BUY_FILLED so bot will place SELL
                            self.state['stage'] = 'BUY_FILLED'
                            self.state['current_position'] = {
                                'market_id': market_id,
                                'token_id': pos.get('token_id', ''),
                                'market_title': pos.get('title', f"Recovered market #{market_id}"),
                                'filled_amount': shares,
                                'avg_fill_price': pos.get('avg_price', 0.01),  # Fallback
                                'filled_usdt': shares * pos.get('avg_price', 0.01),
                                'fill_timestamp': get_timestamp()
                            }
                            self.state_manager.save_state(self.state)
                            
                            # Change stage to BUY_FILLED for this execution
                            stage = 'BUY_FILLED'
                            logger.info("✅ State recovered - will execute BUY_FILLED handler")
                            break
                            
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
            # Query all pending orders from API
            # Note: This requires adding get_pending_orders() method to api_client.py
            # For now, we'll check positions and orders via existing methods
            
            # Check if we have any active positions with tokens (indicating partial fill)
            positions = self.client.get_positions()
            for pos in positions:
                market_id = pos.get('market_id')
                shares = float(pos.get('shares_owned', 0))
                
                if shares >= 1.0:  # Significant position exists
                    logger.warning(f"⚠️ Found existing position in market {market_id} with {shares:.4f} tokens")
                    logger.warning(f"   This may be from previous incomplete cycle")
                    logger.info(f"🔄 Recovering to SELL stage...")
                    
                    # Recover state as if we're ready to SELL
                    self.state['stage'] = 'BUY_FILLED'
                    self.state['current_position'] = {
                        'market_id': market_id,
                        'token_id': pos.get('token_id', ''),  # Need to extract from position
                        'market_title': f"Recovered market #{market_id}",
                        'filled_amount': shares,
                        'avg_fill_price': 0.01,  # Fallback - will be recalculated if needed
                        'filled_usdt': shares * 0.01,
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
                # Strategy 1: Find pending order on this market
                logger.info("🔍 Searching for pending orders on this market...")
                orders = self.client.get_my_orders(
                    market_id=market_id,
                    status='PENDING',
                    limit=20
                )
                
                if orders:
                    # Found pending order(s) on this market
                    logger.info(f"✅ Found {len(orders)} pending order(s) on market #{market_id}")
                    
                    # Find order with non-zero amount (skip dust/old orders)
                    recovered_order = None
                    for order in orders:
                        # Check maker_amount field (could be in different fields depending on API response)
                        amount = float(order.get('maker_amount', 0) or order.get('amount', 0) or order.get('maker_amount_in_quote_token', 0))
                        
                        if amount >= 0.10:  # Minimum meaningful order size
                            recovered_order = order
                            logger.info(f"   Selected order with amount: ${amount:.2f}")
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
            
            if not order_status or order_status in terminal_statuses:
                if order_status:
                    logger.warning(f"⚠️ Order status is '{order_status}' - order is not active")
                else:
                    logger.warning("⚠️ Order not found in API")
                
                logger.info("🔄 Checking if position exists (tokens to sell)...")
                
                # Check if we have tokens from this position
                verified_shares = self.client.get_position_shares(
                    market_id=market_id,
                    outcome_side="YES"
                )
                tokens = float(verified_shares)
                
                if tokens >= 1.0:  # Have significant position
                    logger.info(f"✅ Found position with {tokens:.4f} tokens")
                    
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
                    logger.info(f"   Order was {order_status or 'not found'} without fill")
                    logger.info("   Resetting to SCANNING for new market")
                    
                    self.state_manager.reset_position(self.state)
                    self.state['stage'] = 'SCANNING'
                    self.state_manager.save_state(self.state)
                    return True
            
            # Order exists and is active - proceed with normal monitoring
            logger.info(f"✅ Order is active (status: {order_status}) - starting monitor")
                    
        except Exception as e:
            logger.warning(f"⚠️ Could not verify order status: {e}")
            logger.info("   Proceeding with normal monitoring (may fail if order doesn't exist)")
        
        # Calculate timeout
        timeout_hours = self.config['BUY_ORDER_TIMEOUT_HOURS']
        timeout_at = datetime.now() + timedelta(hours=self.config['BUY_ORDER_TIMEOUT_HOURS'])
        
        # Create monitor and start monitoring
        monitor = BuyMonitor(self.config, self.client, self.state)
        
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
                verified_shares = self.client.get_position_shares(
                    market_id=market_id,
                    outcome_side="YES"
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
        
        elif status in ['cancelled', 'expired', 'timeout', 'deteriorated']:
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
        token_id = position['token_id']
        filled_amount = position['filled_amount']
        
        # SAFETY CHECK: Verify filled_amount is valid before attempting SELL
        if not filled_amount or filled_amount <= 0:
            logger.error(f"❌ Invalid filled_amount in state: {filled_amount}")
            logger.error(f"   Cannot place SELL with 0 tokens!")
            logger.info(f"🔄 Re-checking position from API...")
            
            try:
                verified_shares = self.client.get_position_shares(
                    market_id=market_id,
                    outcome_side="YES"
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
                self.state_manager.save_state(self.state)
            else:
                logger.error(f"❌ Cannot recover avg_fill_price - no valid price in state!")
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
                market_id = position['market_id']
                verified_shares = self.client.get_position_shares(
                    market_id=market_id,
                    outcome_side="YES"
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
            order_status = self.client.get_order_status(sell_order_id)
            
            # If order doesn't exist or is in terminal state
            # Status codes: PENDING, FILLED, PARTIALLY_FILLED, CANCELLED
            terminal_statuses = ['CANCELLED', 'FILLED', 'PARTIALLY_FILLED']
            
            if not order_status or order_status in terminal_statuses:
                if order_status:
                    logger.warning(f"⚠️ SELL order status is '{order_status}' - order is not active")
                else:
                    logger.warning("⚠️ SELL order not found in API")
                
                logger.info("🔄 Checking if position still exists...")
                
                # Check if we still have tokens
                verified_shares = self.client.get_position_shares(
                    market_id=market_id,
                    outcome_side="YES"
                )
                tokens = float(verified_shares)
                
                if tokens >= 1.0:  # Still have tokens
                    logger.info(f"✅ Still have {tokens:.4f} tokens")
                    
                    if order_status in ['FILLED', 'PARTIALLY_FILLED']:
                        logger.info(f"   SELL order was {order_status} but we still have tokens?")
                        logger.info(f"   This is unusual - going back to BUY_FILLED")
                    else:
                        logger.info(f"   SELL order was {order_status or 'not found'} but tokens remain")
                        logger.info(f"   Going back to BUY_FILLED to place new SELL order")
                    
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
                    logger.warning(f"⚠️ No tokens found (only {tokens:.4f})")
                    
                    if order_status in ['FILLED', 'PARTIALLY_FILLED']:
                        logger.info(f"   SELL order was {order_status} successfully")
                        logger.info("   Marking as COMPLETED")
                        self.state['stage'] = 'COMPLETED'
                        self.state_manager.save_state(self.state)
                        return True
                    else:
                        logger.info(f"   Order was {order_status or 'not found'} and no tokens remain")
                        logger.info("   Resetting to SCANNING")
                        
                        self.state_manager.reset_position(self.state)
                        self.state['stage'] = 'SCANNING'
                        self.state_manager.save_state(self.state)
                        return True
            
            # Order exists and is active - proceed with normal monitoring
            logger.info(f"✅ SELL order is active (status: {order_status}) - starting monitor")
                    
        except Exception as e:
            logger.warning(f"⚠️ Could not verify SELL order status: {e}")
            logger.info("   Proceeding with normal monitoring (may fail if order doesn't exist)")
        
        # Calculate timeout
        timeout_hours = self.config['SELL_ORDER_TIMEOUT_HOURS']
        timeout_at = datetime.now() + timedelta(hours=timeout_hours)
        
        # Create monitor and start monitoring
        monitor = SellMonitor(self.config, self.client, self.state)
        
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
        
        elif status in ['cancelled', 'expired']:
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
    
    def _display_session_summary(self):
        """Display summary of current session."""
        logger.info("")
        logger.info("=" * 60)
        logger.info("SESSION SUMMARY".center(60))
        logger.info("=" * 60)
        
        stats = self.state['statistics']
        
        logger.info(f"   Total trades: {stats['total_trades']}")
        logger.info(f"   Wins: {stats['wins']} | Losses: {stats['losses']}")
        logger.info(f"   Win rate: {stats['win_rate_percent']:.1f}%")
        logger.info(f"   Total P&L: ${stats['total_pnl_usdt']:.2f}")
        logger.info(f"   Avg P&L per trade: ${stats['total_pnl_percent']:.2f}")
        
        logger.info("=" * 60)


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("Use autonomous_bot_main.py to run the bot")
    print("This module requires full configuration and API client")