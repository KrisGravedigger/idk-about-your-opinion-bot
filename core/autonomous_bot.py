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
from utils import format_price, format_usdt, format_percent, get_timestamp, safe_float, interruptible_sleep

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
from transaction_history import TransactionHistory
from telegram_notifications import TelegramNotifier
from core.position_validator import PositionValidator
from core.position_recovery import PositionRecovery
from core.reconciliation_engine import ReconciliationEngine
from handlers.buy_handler import BuyHandler
from handlers.sell_handler import SellHandler
from handlers.market_selector import MarketSelector

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
        self.transaction_history = TransactionHistory()  # Transaction audit trail
        self.telegram = TelegramNotifier()  # Telegram notifications
        self.scanner = MarketScanner(client)
        self.pricing = PricingStrategy(config)
        self.order_manager = OrderManager(client)
        self.tracker = PositionTracker()
        self.validator = PositionValidator(client, config)  # Position validation
        self.recovery = PositionRecovery(client, config)  # Position recovery

        # CHANGED: Load state immediately in constructor
        # This allows autonomous_bot_main.py to modify state before run()
        self.state = self.state_manager.load_state()

        # Initialize reconciliation engine (requires state_manager and transaction_history)
        self.reconciliation = ReconciliationEngine(
            config=config,
            client=client,
            state_manager=self.state_manager,
            transaction_history=self.transaction_history
        )

        # Initialize handlers (requires state to be loaded first)
        self.market_selector = MarketSelector(self)
        self.buy_handler = BuyHandler(self)
        self.sell_handler = SellHandler(self)

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

        logger.debug("After display_summary - preparing to send Telegram notification...")

        # Send Telegram notification: Bot started
        try:
            logger.debug("Fetching balance for Telegram notification...")
            balance = self.client.get_usdt_balance()
            logger.debug(f"Balance fetched: ${balance:.2f}")
        except Exception as e:
            logger.warning(f"Could not fetch balance for Telegram notification: {e}")
            balance = 0.0

        logger.debug("Sending bot_start notification to Telegram...")
        self.telegram.send_bot_start(
            stats=self.pnl_stats.get_summary(),
            config=self.config,
            balance=balance
        )
        logger.debug("Telegram notification sent (async)")

        try:
            # Send initial heartbeat to verify current state (async to avoid blocking)
            logger.debug("Sending initial heartbeat (async)...")
            # Set last_heartbeat BEFORE sending to prevent duplicate in first cycle
            from datetime import datetime
            self.last_heartbeat = datetime.now()
            import threading
            heartbeat_thread = threading.Thread(target=self._send_heartbeat_now, daemon=True)
            heartbeat_thread.start()
            logger.debug("Initial heartbeat thread started")
            # Don't wait for it - let it finish in background
        except Exception as e:
            logger.warning(f"Could not send initial heartbeat: {e}")

        logger.debug("Preparing to start main loop...")
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
                    interruptible_sleep(self.cycle_delay * 3)  # Longer delay on error, but responsive

                # Check if heartbeat should be sent
                self._check_and_send_heartbeat()

                # Brief pause between cycles (responsive to CTRL+C)
                interruptible_sleep(self.cycle_delay)
        
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
        # This is the FIRST LINE OF DEFENSE against state/API discrepancies
        # Uses ReconciliationEngine for graceful recovery

        try:
            logger.debug("🔍 Pre-stage check: Detecting state discrepancies...")

            # Detect any discrepancies between state and API reality
            discrepancy = self.reconciliation.detect_discrepancy(self.state)

            if discrepancy:
                # Found a discrepancy - attempt reconciliation
                logger.info(f"⚠️  Discrepancy detected: {discrepancy.type.value}")

                result = self.reconciliation.reconcile(
                    state=self.state,
                    discrepancy=discrepancy,
                    telegram_notifier=self.telegram
                )

                if result.success:
                    # Reconciliation succeeded - reload state and adjust stage
                    self.state = self.state_manager.load_state()
                    stage = self.state.get('stage', stage)
                    logger.info(f"✅ Reconciliation successful - continuing with stage: {stage}")
                else:
                    # Reconciliation failed - log and continue (may fail later)
                    logger.warning(f"⚠️  Reconciliation failed: {result.reason}")
                    logger.warning(f"   Continuing with current stage, but issues may persist")

        except Exception as e:
            logger.debug(f"Pre-stage discrepancy check failed (non-critical): {e}")

        # ================================================================
        # Execute stage handler
        # ================================================================

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
        return self.market_selector.handle_scanning()
    
    def _handle_buy_placed(self) -> bool:
        """
        BUY_PLACED stage: BUY order placed, ready to monitor.

        Transitions to: BUY_MONITORING
        """
        return self.buy_handler.handle_buy_placed()
    
    def _handle_buy_monitoring(self) -> bool:
        """
        BUY_MONITORING stage: Monitor BUY order until filled.
        
        Transitions to: BUY_FILLED (if filled)
        Transitions to: SCANNING (if cancelled/deteriorated)
        """
        return self.buy_handler.handle_buy_monitoring()

    def _handle_buy_filled(self) -> bool:
        """
        BUY_FILLED stage: BUY filled, ready to place SELL.
        
        Transitions to: SELL_PLACED
        """
        return self.buy_handler.handle_buy_filled()

    def _handle_sell_placed(self) -> bool:
        """
        SELL_PLACED stage: SELL order placed, ready to monitor.
        
        Transitions to: SELL_MONITORING
        """
        return self.sell_handler.handle_sell_placed()

    def _handle_sell_monitoring(self) -> bool:
        """
        SELL_MONITORING stage: Monitor SELL order until filled.
        
        Transitions to: COMPLETED (if filled)
        Transitions to: BUY_FILLED (if cancelled/expired - retry)
        Transitions to: SCANNING (if stop-loss/deteriorated)
        """
        return self.sell_handler.handle_sell_monitoring()

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

        # IMPORTANT: Reload state from disk to get fresh stage info
        # Monitor callbacks use stale self.state which can be outdated
        try:
            fresh_state = self.state_manager.load_state()
            if fresh_state:
                self.state = fresh_state
        except Exception as e:
            logger.warning(f"Could not reload state for heartbeat: {e}")

        # Gather information for heartbeat
        stage = self.state.get('stage', 'IDLE')
        position = self.state.get('current_position', {})
        market_info = None
        order_info = None
        position_value = 0.0
        outcome_side = None

        # Get market info and order details if in active position
        if position and position.get('market_id'):
            try:
                market_id = position['market_id']
                token_id = position.get('token_id')
                outcome_side = position.get('outcome_side', 'UNKNOWN')
                market_title = position.get('market_title', f'Market #{market_id}')

                # DEBUG: Log which token we're fetching orderbook for
                logger.debug(f"💓 Heartbeat: Fetching orderbook for market #{market_id}")
                logger.debug(f"   token_id: {token_id[:20] if token_id else 'None'}...")
                logger.debug(f"   outcome_side: {outcome_side}")

                # Get orderbook using token_id (FIXED: was using market_id which doesn't work)
                orderbook = None
                if token_id:
                    orderbook = self.client.get_market_orderbook(token_id)
                    if orderbook:
                        logger.debug(f"   ✅ Orderbook fetched successfully")
                    else:
                        logger.warning(f"   ⚠️ Orderbook fetch returned None for token {token_id[:20]}...")

                if orderbook and 'bids' in orderbook and 'asks' in orderbook:
                    bids = orderbook['bids']
                    asks = orderbook['asks']

                    if bids and asks:
                        # Extract best prices
                        best_bid = float(bids[0].get('price', 0)) if isinstance(bids[0], dict) else float(bids[0][0])
                        best_ask = float(asks[0].get('price', 0)) if isinstance(asks[0], dict) else float(asks[0][0])
                        spread = best_ask - best_bid

                        # DEBUG: Log orderbook prices for verification
                        logger.debug(f"   📊 Orderbook prices:")
                        logger.debug(f"      Best bid: ${best_bid:.4f}")
                        logger.debug(f"      Best ask: ${best_ask:.4f}")
                        logger.debug(f"      Spread: ${spread:.4f}")

                        # VALIDATION: Check if orderbook data makes sense
                        if spread < 0:
                            logger.warning(f"   ⚠️ SUSPICIOUS: Negative spread detected! bid=${best_bid:.4f} > ask=${best_ask:.4f}")
                            logger.warning(f"   This indicates crossed market or data error")
                        if best_bid <= 0 or best_ask <= 0:
                            logger.warning(f"   ⚠️ SUSPICIOUS: Zero or negative price detected!")
                        if best_bid > 1.0 or best_ask > 1.0:
                            logger.warning(f"   ⚠️ SUSPICIOUS: Price > $1.00 in prediction market!")

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
            position_value=position_value,
            outcome_side=outcome_side
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