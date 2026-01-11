#!/usr/bin/env python3
"""
Opinion Farming Bot - Autonomous Mode Entry Point
==================================================

Main entry point for running the autonomous trading bot.

The bot operates as a state machine with the following cycle:

    IDLE → SCANNING → BUY_PLACED → BUY_MONITORING → BUY_FILLED →
    SELL_PLACED → SELL_MONITORING → COMPLETED → IDLE (repeat)

Features:
    - Automatic market selection using scanner + scoring
    - Capital management (fixed or percentage mode)
    - Market making pricing strategy
    - BUY/SELL order monitoring with timeout
    - Stop-loss protection on SELL orders
    - Liquidity deterioration detection
    - P&L tracking and statistics
    - State persistence across restarts

Usage:
    python autonomous_bot_main.py [OPTIONS]

Options:
    --max-cycles N     Run for N cycles then exit (default: infinite)
    --dry-run          Run in simulation mode (no real orders)
    --reset-state      Clear state.json before starting

Configuration:
    Edit config.py to adjust bot behavior:
    - CAPITAL_MODE: 'fixed' or 'percentage'
    - ENABLE_STOP_LOSS: Enable/disable stop-loss protection
    - And many more...

State Persistence:
    The bot saves its state to state.json after each stage transition.
    If interrupted (Ctrl+C), you can restart and it will resume from
    the last saved state.

Safety:
    - Always test with small amounts first
    - Monitor the bot regularly
    - Set appropriate stop-loss thresholds
    - Use MIN_BALANCE_TO_CONTINUE_USDT to prevent over-trading

Examples:
    # Run indefinitely
    python autonomous_bot_main.py

    # Run for 5 cycles then stop
    python autonomous_bot_main.py --max-cycles 5

    # Start fresh (clear previous state)
    python autonomous_bot_main.py --reset-state
"""

import sys
import argparse
from pathlib import Path

# Fix for Windows UTF-8 console output (handles emoji and unicode characters)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Local imports
from config_loader import config
from logger_config import setup_logger, log_startup_banner
from api_client import create_client
from core.autonomous_bot import AutonomousBot
from utils import clear_state, get_timestamp

# Import config validator
from config_validator import validate_full_config, validate_credentials

# Initialize logger
logger = setup_logger(__name__)


def parse_arguments():
    """
    Parse command line arguments.
    
    Returns:
        argparse.Namespace with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Opinion Farming Bot - Autonomous Mode',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--max-cycles',
        type=int,
        default=None,
        metavar='N',
        help='Run for N cycles then exit (default: run indefinitely)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulation mode - no real orders placed (NOT IMPLEMENTED YET)'
    )
    
    parser.add_argument(
        '--reset-state',
        action='store_true',
        help='Clear state.json before starting (start fresh)'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Opinion Farming Bot v0.1 - Autonomous Mode'
    )
    
    return parser.parse_args()


def display_welcome_banner():
    """Display welcome banner with important information."""
    print()
    print("=" * 70)
    print("OPINION FARMING BOT - AUTONOMOUS MODE".center(70))
    print("=" * 70)
    print()
    print("⚠️  IMPORTANT SAFETY REMINDERS:")
    print()
    print("   1. This bot trades real money - USE AT YOUR OWN RISK")
    print("   2. Always test with SMALL amounts first")
    print("   3. Monitor the bot regularly - don't leave unattended")
    print("   4. Check config.py settings before running")
    print("   5. Stop-loss is enabled by default but NOT foolproof")
    print()
    print("📚 Documentation: Check README.md for full details")
    print("🐛 Issues: Report bugs via GitHub or contact support")
    print()
    print("Press Ctrl+C at any time to stop the bot gracefully")
    print("=" * 70)
    print()


def display_config_summary(config):
    """
    Display summary of important config settings.
    
    Args:
        config: Configuration dictionary
    """
    logger.info("📋 Configuration Summary:")
    logger.info(f"   Capital mode: {config['CAPITAL_MODE']}")
    
    if config['CAPITAL_MODE'] == 'fixed':
        logger.info(f"   Capital amount: ${config['CAPITAL_AMOUNT_USDT']:.2f}")
    else:
        logger.info(f"   Capital percentage: {config['CAPITAL_PERCENTAGE']:.0f}%")
    
    logger.info(f"   Stop-loss: {'ENABLED' if config.get('ENABLE_STOP_LOSS', True) else 'DISABLED'}")
    
    if config.get('ENABLE_STOP_LOSS'):
        logger.info(f"   Stop-loss threshold: {config['STOP_LOSS_TRIGGER_PERCENT']}%")
    
    logger.info("")


def main():
    """
    Main function for autonomous bot.
    
    Returns:
        0 on success, 1 on failure
    """
    # Parse arguments
    args = parse_arguments()
    
    # Display welcome banner
    display_welcome_banner()
    
    # Log startup
    log_startup_banner(logger, "Autonomous Bot")
    
    # =========================================================================
    # VALIDATE CONFIGURATION
    # =========================================================================
    logger.info("🔧 Validating configuration...")

    # Build config dict from config_loader (merges config.py + bot_config.json + .env)
    # This allows GUI changes to take effect
    config_dict = {
        # Capital Management
        'capital_mode': config.CAPITAL_MODE,
        'capital_amount_usdt': config.CAPITAL_AMOUNT_USDT,
        'capital_percentage': config.CAPITAL_PERCENTAGE,
        'min_balance_to_continue_usdt': config.MIN_BALANCE_TO_CONTINUE_USDT,
        'min_position_size_usdt': config.MIN_POSITION_SIZE_USDT,
        'min_position_for_points_usdt': config.MIN_POSITION_FOR_POINTS_USDT,
        'warn_if_below_points_threshold': config.WARN_IF_BELOW_POINTS_THRESHOLD,

        # Pricing
        'safety_margin_cents': config.SAFETY_MARGIN_CENTS,

        # Monitoring
        'fill_check_interval_seconds': config.FILL_CHECK_INTERVAL_SECONDS,
        'buy_order_timeout_hours': config.BUY_ORDER_TIMEOUT_HOURS,
        'sell_order_timeout_hours': config.SELL_ORDER_TIMEOUT_HOURS,

        # Liquidity
        'liquidity_auto_cancel': config.LIQUIDITY_AUTO_CANCEL,
        'liquidity_bid_drop_threshold': config.LIQUIDITY_BID_DROP_THRESHOLD,
        'liquidity_spread_threshold': config.LIQUIDITY_SPREAD_THRESHOLD,

        # Stop-loss
        'enable_stop_loss': config.ENABLE_STOP_LOSS,
        'stop_loss_trigger_percent': config.STOP_LOSS_TRIGGER_PERCENT,
        'stop_loss_aggressive_offset': config.STOP_LOSS_AGGRESSIVE_OFFSET,

        # Bot config
        'bonus_markets_file': config.BONUS_MARKETS_FILE,
        'scoring_profile': config.DEFAULT_SCORING_PROFILE,
        'cycle_delay_seconds': 10,
        'max_cycles': args.max_cycles,

        # Telegram
        'telegram_heartbeat_interval_hours': config.TELEGRAM_HEARTBEAT_INTERVAL_HOURS,

        # Logging
        'log_file': config.LOG_FILE,

        # API Credentials (for validation)
        'api_key': config.API_KEY,
        'private_key': config.PRIVATE_KEY,
        'multi_sig_address': config.MULTI_SIG_ADDRESS if hasattr(config, 'MULTI_SIG_ADDRESS') else '',
        'rpc_url': config.RPC_URL,
    }

    # Validate configuration
    is_valid, errors, warnings = validate_full_config(config_dict)

    if not is_valid:
        logger.error("Configuration errors found:")
        for error in errors:
            logger.error(f"   - {error}")
        return 1

    # Show warnings if any
    if warnings:
        logger.warning("Configuration warnings:")
        for warning in warnings:
            logger.warning(f"   ⚠️ {warning}")

    logger.info("   Configuration valid ✓")
    logger.info("")

    # Build uppercase config dict for bot (legacy compatibility)
    config_dict = {
        # Capital Management
        'CAPITAL_MODE': config.CAPITAL_MODE,
        'CAPITAL_AMOUNT_USDT': config.CAPITAL_AMOUNT_USDT,
        'CAPITAL_PERCENTAGE': config.CAPITAL_PERCENTAGE,
        'MIN_BALANCE_TO_CONTINUE_USDT': config.MIN_BALANCE_TO_CONTINUE_USDT,
        'MIN_POSITION_SIZE_USDT': config.MIN_POSITION_SIZE_USDT,
        'MIN_POSITION_FOR_POINTS_USDT': config.MIN_POSITION_FOR_POINTS_USDT,
        'WARN_IF_BELOW_POINTS_THRESHOLD': config.WARN_IF_BELOW_POINTS_THRESHOLD,

        # Pricing
        'SAFETY_MARGIN_CENTS': config.SAFETY_MARGIN_CENTS,

        # Monitoring
        'FILL_CHECK_INTERVAL_SECONDS': config.FILL_CHECK_INTERVAL_SECONDS,
        'BUY_ORDER_TIMEOUT_HOURS': config.BUY_ORDER_TIMEOUT_HOURS,
        'SELL_ORDER_TIMEOUT_HOURS': config.SELL_ORDER_TIMEOUT_HOURS,

        # Liquidity
        'LIQUIDITY_AUTO_CANCEL': config.LIQUIDITY_AUTO_CANCEL,
        'LIQUIDITY_BID_DROP_THRESHOLD': config.LIQUIDITY_BID_DROP_THRESHOLD,
        'LIQUIDITY_SPREAD_THRESHOLD': config.LIQUIDITY_SPREAD_THRESHOLD,

        # Stop-loss
        'ENABLE_STOP_LOSS': config.ENABLE_STOP_LOSS,
        'STOP_LOSS_TRIGGER_PERCENT': config.STOP_LOSS_TRIGGER_PERCENT,
        'STOP_LOSS_AGGRESSIVE_OFFSET': config.STOP_LOSS_AGGRESSIVE_OFFSET,

        # Bot config
        'BONUS_MARKETS_FILE': config.BONUS_MARKETS_FILE,
        'SCORING_PROFILE': config.DEFAULT_SCORING_PROFILE,
        'CYCLE_DELAY_SECONDS': 10,
        'MAX_CYCLES': args.max_cycles,

        # Telegram
        'TELEGRAM_HEARTBEAT_INTERVAL_HOURS': config.TELEGRAM_HEARTBEAT_INTERVAL_HOURS,

        # Logging
        'LOG_FILE': config.LOG_FILE
    }

    # =========================================================================
    # APPLY LIQUIDITY FARMING OVERRIDES
    # =========================================================================
    # Support both USE_LIQUIDITY_FARMING and USE_SPREAD_FARMING (backward compat)
    if config.USE_LIQUIDITY_FARMING or config.USE_SPREAD_FARMING:
        strategy_name = "Liquidity Farming" if config.USE_LIQUIDITY_FARMING else "Spread Farming (deprecated)"
        strategy_config = config.LIQUIDITY_FARMING_CONFIG  # Both point to same config now

        logger.info(f"🎯 {strategy_name} mode ACTIVE - applying overrides...")
        logger.info(f"   Scoring profile: {strategy_config['scoring_profile']}")
        logger.info(f"   Probability range: {strategy_config['outcome_min_probability']*100:.0f}%-{strategy_config['outcome_max_probability']*100:.0f}%")
        logger.info(f"   Min spread: {strategy_config['min_spread_pct']}% (0% = no filter)")

        # Override config with liquidity farming parameters
        config_dict['SCORING_PROFILE'] = strategy_config['scoring_profile']

        # Override outcome filters in config_loader (for other modules)
        config.OUTCOME_MIN_PROBABILITY = strategy_config['outcome_min_probability']
        config.OUTCOME_MAX_PROBABILITY = strategy_config['outcome_max_probability']

        # Override orderbook balance range (None = disable hard filter)
        if strategy_config['orderbook_balance_range'] is not None:
            config.ORDERBOOK_BALANCE_RANGE = strategy_config['orderbook_balance_range']
        else:
            config.ORDERBOOK_BALANCE_RANGE = None

        # Override min hours until close (None = disable filter)
        if strategy_config['min_hours_until_close'] is not None:
            config.MIN_HOURS_UNTIL_CLOSE = strategy_config['min_hours_until_close']
        else:
            config.MIN_HOURS_UNTIL_CLOSE = None

        logger.info("   ✓ Overrides applied")
        logger.info("")

    # Display config summary
    display_config_summary(config_dict)
    
    # =========================================================================
    # HANDLE --reset-state
    # =========================================================================
    if args.reset_state:
        logger.info("🗑️  Clearing previous state (--reset-state flag)...")
        clear_state()
        logger.info("   State cleared ✓")
        logger.info("")
    
    # =========================================================================
    # HANDLE --dry-run
    # =========================================================================
    if args.dry_run:
        logger.error("❌ --dry-run mode not implemented yet")
        logger.info("   This feature will be added in a future update")
        logger.info("   For now, bot operates in LIVE mode only")
        return 1
    
    # =========================================================================
    # INITIALIZE CLIENT
    # =========================================================================
    try:
        logger.info("🔌 Connecting to Opinion.trade...")
        client = create_client()
        logger.info("   Connected ✓")
        logger.info("")
    except Exception as e:
        logger.error(f"Failed to initialize API client: {e}")
        logger.error("Check your API_KEY and API_SECRET in config.py")
        return 1
    
    # =========================================================================
    # INITIALIZE BOT (moved before balance check)
    # =========================================================================
    try:
        logger.info("🤖 Initializing Autonomous Bot...")
        bot = AutonomousBot(config, client)
        logger.info("   Bot initialized ✓")
        logger.info("")
    except Exception as e:
        logger.error(f"Failed to initialize bot: {e}")
        return 1
    
    # =========================================================================
    # CHECK IF RESUMING EXISTING POSITION
    # =========================================================================
    # Quick check: if we have an open position, skip balance check
    # (position value is locked in tokens, not in free USDT balance)
    from core.state_manager import StateManager
    from utils import get_timestamp
    
    state_mgr = StateManager()
    existing_state = state_mgr.load_state()
    
    has_open_position = (
        existing_state 
        and existing_state.get('stage') not in ['IDLE', 'SCANNING', 'COMPLETED']
    )
    
    # =========================================================================
    # SELF-HEALING: Check API for orphaned positions
    # =========================================================================
    # Even if state.json says IDLE, we might have positions in API
    # This happens when:
    # 1. Order was placed but save_state() failed
    # 2. Bot was killed after place_buy() but before state update
    # 3. Manual trading was done outside bot
    
    if not has_open_position:
        logger.info("🔍 Checking API for orphaned positions...")

        try:
            # Get only significant positions (filters out dust < 5.0 shares automatically)
            positions = client.get_significant_positions(min_shares=5.0)

            if positions:
                logger.warning("=" * 70)
                logger.warning("⚠️  ORPHANED POSITION DETECTED!")
                logger.warning(f"   state.json says: {existing_state.get('stage', 'UNKNOWN')}")
                logger.warning(f"   But API shows: {len(positions)} significant position(s)")
                logger.warning("=" * 70)
                logger.info("")

                # Take first significant position (dust already filtered)
                pos = positions[0]
                market_id = pos.get('market_id')
                shares = float(pos.get('shares_owned', 0))

                logger.info(f"🔄 AUTO-RECOVERY:")
                logger.info(f"   Market: #{market_id}")
                logger.info(f"   Shares: {shares:.4f}")
                logger.info("")

                # CRITICAL: Before recovering, check if position value meets minimum
                # API requires order value >= $1.30, not just shares >= 1.0!
                should_recover = False

                # Get market details to find token_id AND check order value
                logger.info("   Fetching market details for token_id...")
                try:
                    market_data = client.get_market(market_id)
                    if not market_data:
                        logger.warning(f"   ⚠️ Could not fetch market data")
                        logger.warning(f"   Cannot verify order value - skipping recovery")
                        token_id = ''
                    else:
                        # Get outcome_side
                        outcome_side_enum = pos.get('outcome_side_enum', 'Yes')

                        # Handle both dict and Pydantic model returns
                        if isinstance(market_data, dict):
                            if outcome_side_enum.lower() == 'yes':
                                token_id = market_data.get('yes_token_id', '')
                            else:
                                token_id = market_data.get('no_token_id', '')
                        else:
                            if outcome_side_enum.lower() == 'yes':
                                token_id = getattr(market_data, 'yes_token_id', '')
                            else:
                                token_id = getattr(market_data, 'no_token_id', '')

                        if not token_id:
                            logger.warning(f"   ⚠️ Token ID is empty")
                            logger.warning(f"   Cannot verify order value - skipping recovery")
                        else:
                            logger.info(f"   ✅ Found token_id: {token_id[:40]}...")

                            # Get orderbook to check current price
                            logger.info(f"   Checking order value...")
                            try:
                                orderbook = client.get_market_orderbook(token_id)
                                if orderbook and 'asks' in orderbook:
                                    asks = orderbook.get('asks', [])
                                    if asks:
                                        # Get best ask price (already sorted by api_client)
                                        best_ask = float(asks[0].get('price', 0)) if isinstance(asks[0], dict) else float(asks[0][0])

                                        # Calculate order value after floor rounding
                                        import math
                                        sellable_amount = math.floor(shares * 10) / 10
                                        order_value = sellable_amount * best_ask

                                        MIN_ORDER_VALUE = 1.30

                                        logger.info(f"   Position: {shares:.4f} shares")
                                        logger.info(f"   After floor: {sellable_amount:.1f} shares")
                                        logger.info(f"   Current ask: ${best_ask:.4f}")
                                        logger.info(f"   Order value: ${order_value:.2f}")
                                        logger.info(f"   Minimum: ${MIN_ORDER_VALUE:.2f}")

                                        if order_value < MIN_ORDER_VALUE:
                                            logger.warning("=" * 70)
                                            logger.warning(f"⚠️  DUST POSITION - cannot recover!")
                                            logger.warning(f"   Order value ${order_value:.2f} < ${MIN_ORDER_VALUE:.2f} minimum")
                                            logger.warning(f"   Position cannot be sold due to API minimum")
                                            logger.warning(f"   Skipping startup recovery - bot will stay in SCANNING")
                                            logger.warning("=" * 70)
                                            logger.info("")
                                            should_recover = False
                                        else:
                                            logger.info(f"   ✅ Order value OK - proceeding with recovery")
                                            should_recover = True
                                    else:
                                        logger.warning(f"   ⚠️ Orderbook has no asks - skipping recovery")
                                else:
                                    logger.warning(f"   ⚠️ Could not fetch orderbook - skipping recovery")
                            except Exception as e:
                                logger.warning(f"   ⚠️ Error checking orderbook: {e}")
                                logger.warning(f"   Cannot verify order value - skipping recovery")
                except Exception as e:
                    logger.warning(f"   ⚠️ Error fetching market: {e}")
                    logger.warning(f"   Cannot verify order value - skipping recovery")
                    token_id = ''

                # Only proceed with recovery if order value check passed
                if should_recover:
                    logger.info("   🔍 Checking if SELL order already exists...")
                    existing_sell_order = None
                    try:
                        # Check for ACTIVE orders (status='1'), not FILLED
                        orders = client.get_my_orders(
                            market_id=market_id,
                            status='1',  # 1 = ACTIVE orders
                            limit=20
                        )

                        for order in orders:
                            order_side = order.get('side', -1)
                            filled_amount = float(order.get('filled_amount', 0) or 0)
                            order_amount = float(order.get('order_amount', 0) or 0)

                            # Side: 1=BUY, 2=SELL
                            if order_side == 2:
                                existing_sell_order = order
                                logger.info(f"   ✅ Found existing SELL order: {order.get('order_id')[:40]}...")
                                logger.info(f"      Filled: ${filled_amount:.2f} / ${order_amount:.2f}")
                                break
                    except Exception as e:
                        logger.warning(f"   ⚠️ Could not check for existing orders: {e}")

                    logger.info("")
                    logger.info("💡 Bot will SKIP balance check and monitor position")
                    logger.info("")

                    # CRITICAL: Load bot.state before modifying
                    if bot.state is None:
                        bot.state = bot.state_manager.load_state()

                    # If SELL order exists, go to SELL_MONITORING
                    # Otherwise, go to BUY_FILLED to place new SELL
                    if existing_sell_order:
                        logger.info(f"   Action: Will MONITOR existing SELL order")
                        bot.state['stage'] = 'SELL_PLACED'
                        bot.state['current_position'] = {
                            'market_id': market_id,
                            'token_id': token_id,
                            'market_title': getattr(market_data, 'title', f"Market #{market_id}") if market_data else f"Market #{market_id}",
                            'filled_amount': shares,
                            'avg_fill_price': 0.31,
                            'filled_usdt': shares * 0.31,
                            'fill_timestamp': get_timestamp(),
                            'sell_order_id': existing_sell_order.get('order_id'),
                            'sell_price': float(existing_sell_order.get('price', 0)),
                            'sell_placed_at': get_timestamp()
                        }
                    else:
                        logger.info(f"   Action: Will place NEW SELL order")
                        bot.state['stage'] = 'BUY_FILLED'
                        bot.state['current_position'] = {
                            'market_id': market_id,
                            'token_id': token_id,
                            'outcome_side': outcome_side_enum.upper(),  # CRITICAL: Set outcome_side from API
                            'market_title': getattr(market_data, 'title', f"Market #{market_id}") if market_data else f"Market #{market_id}",
                            'filled_amount': shares,
                            'avg_fill_price': pos.get('avg_price', 0.01),
                            'filled_usdt': shares * pos.get('avg_price', 0.01),
                            'fill_timestamp': get_timestamp()
                        }
                    bot.state_manager.save_state(bot.state)

                    logger.info("✅ State recovered and saved")
                    logger.info(f"📍 Bot will start in BUY_FILLED → SELL_PLACED")
                    logger.info("")

                    has_open_position = True

            else:
                # No significant positions found (dust < 5.0 shares or no positions at all)
                # Check if this is pending order with frozen balance (not just old dust)
                # Get ALL positions (including dust) to check frozen balance
                all_positions = client.get_positions()

                if all_positions:
                    logger.info("⚠️  No significant positions (all have < 5.0 shares)")
                    logger.info("   Checking if any are PENDING orders (not just dust)...")

                    try:
                        balances = client.get_balances()
                        if not balances or 'tokens' not in balances:
                            logger.warning("   Could not get balances - treating as dust")
                            logger.info("")
                        else:
                            # Check USDT token for frozen balance
                            USDT_ADDRESS = '0x55d398326f99059ff775485246999027b3197955'.lower()
                            tokens = balances['tokens']

                            if USDT_ADDRESS in tokens:
                                usdt_data = tokens[USDT_ADDRESS]
                                frozen_str = usdt_data.get('frozen', '0')
                                frozen_balance = float(frozen_str)

                                logger.info(f"   USDT frozen balance: ${frozen_balance:.2f}")

                                if frozen_balance >= 1.0:
                                    logger.warning("   ⚠️  FOUND: Frozen balance indicates PENDING order!")
                                    logger.info("")
                                    logger.info("🔄 AUTO-RECOVERY:")

                                    # Find the market with PENDING order
                                    recovered_market = None

                                    try:
                                        logger.info("   🔍 Searching for pending order matching frozen balance...")

                                        # Get ALL pending orders (no market filter)
                                        all_pending_orders = client.get_my_orders(
                                            market_id=0,
                                            status='FILLED',  # (SIC!)
                                            limit=20
                                        )

                                        logger.info(f"   Found {len(all_pending_orders)} pending orders across all markets")

                                        # Find order with amount close to frozen balance
                                        for order in all_pending_orders:
                                            order_market_id = order.get('market_id')
                                            order_amount = float(order.get('order_amount', 0) or 0)

                                            # Match if amounts are close (within $0.50)
                                            if abs(order_amount - frozen_balance) < 0.50:
                                                logger.info(f"   ✅ Found matching order:")
                                                logger.info(f"      Market: #{order_market_id}")
                                                logger.info(f"      Order amount: ${order_amount:.2f}")
                                                logger.info(f"      Frozen balance: ${frozen_balance:.2f}")

                                                # Find corresponding position (if exists)
                                                for pos in all_positions:
                                                    if pos.get('market_id') == order_market_id:
                                                        recovered_market = pos
                                                        break

                                                # If no position found, create minimal one
                                                if not recovered_market:
                                                    recovered_market = {
                                                        'market_id': order_market_id,
                                                        'token_id': order.get('outcome_side', 'YES'),  # Fallback
                                                        'title': order.get('market_title', f"Market #{order_market_id}")
                                                    }

                                                break

                                        if not recovered_market:
                                            logger.warning("   ⚠️ Could not find order matching frozen balance")
                                            logger.info("   Using first position as fallback")
                                            if all_positions:
                                                recovered_market = all_positions[0]

                                    except Exception as e:
                                        logger.warning(f"   Error searching for pending order: {e}")
                                        logger.info("   Using first position as fallback")
                                        if all_positions:
                                            recovered_market = all_positions[0]

                                    if not recovered_market and all_positions:
                                        # Fallback: use first position
                                        recovered_market = all_positions[0]

                                    if recovered_market:
                                        market_id = recovered_market.get('market_id')

                                        logger.info(f"   Market: #{market_id}")
                                        logger.info(f"   Frozen: ${frozen_balance:.2f}")
                                        logger.info("")
                                        logger.info("💡 Bot will SKIP balance check and monitor order")
                                        logger.info("")

                                        # Force state to BUY_PLACED (order exists but we don't have order_id)
                                        # Bot will transition to BUY_MONITORING and try to recover order_id there
                                        bot.state['stage'] = 'BUY_PLACED'
                                        bot.state['current_position'] = {
                                            'market_id': market_id,
                                            'token_id': recovered_market.get('token_id', ''),
                                            'market_title': recovered_market.get('title', f"Recovered market #{market_id}"),
                                            'order_id': 'unknown',  # Will be resolved in BUY_MONITORING
                                            'side': 'BUY',
                                            'price': 0.314,  # Approximate from UI (31.4¢)
                                            'amount_usdt': frozen_balance,
                                            'placed_at': get_timestamp()
                                        }
                                        bot.state_manager.save_state(bot.state)

                                        logger.info("✅ State recovered and saved")
                                        logger.info(f"📍 Bot will start in BUY_PLACED → BUY_MONITORING")
                                        logger.info("")

                                        has_open_position = True
                                else:
                                    logger.info("   No significant frozen balance - these are dust/old positions")
                                    logger.info("")
                            else:
                                logger.warning("   USDT token not found in balances")
                                logger.info("   Treating positions as dust")
                                logger.info("")

                    except Exception as e:
                        logger.warning(f"   Could not check frozen balance: {e}")
                        logger.info("   Treating positions as dust")
                        logger.info("")
                else:
                    logger.info("✅ No orphaned positions found")
                    logger.info("")
                
        except Exception as e:
            logger.warning(f"⚠️ Could not check for orphaned positions: {e}")
            logger.info("   Proceeding with normal startup")
            logger.info("")
            
            # Check if we at least set has_open_position before exception
            if bot.state and bot.state.get('stage') not in ['IDLE', 'SCANNING', 'COMPLETED']:
                has_open_position = True
                logger.info("   But state was already recovered - will skip balance check")
                logger.info("")
    
    # =========================================================================
    # SKIP BALANCE CHECK IF RECOVERING POSITION
    # =========================================================================
    if has_open_position:
        stage = bot.state.get('stage', existing_state.get('stage', 'UNKNOWN'))
        logger.info(f"📋 Resuming existing position from stage: {stage}")
        logger.info("   Skipping balance check (value locked in position)")
        logger.info("")
    else:
        # =====================================================================
        # CHECK BALANCE (only for new positions)
        # =====================================================================
        try:
            balance = client.get_usdt_balance()
            logger.info(f"💰 Current balance: ${balance:.2f} USDT")

            if balance < config.MIN_BALANCE_TO_CONTINUE_USDT:
                logger.error(f"⚠️  Balance (${balance:.2f}) is below minimum (${config.MIN_BALANCE_TO_CONTINUE_USDT:.2f})")
                logger.error("   Please add funds before running bot")
                return 1

            logger.info("   Balance sufficient ✓")
            logger.info("")
        except Exception as e:
            logger.warning(f"Could not fetch balance: {e}")
            logger.warning("   Continuing anyway...")
            logger.info("")
    
    # =========================================================================
    # RUN BOT
    # =========================================================================
    logger.info("🚀 Starting bot execution...")
    logger.info("   Press Ctrl+C to stop gracefully")
    logger.info("")
    
    return bot.run()


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print()
        print("⛔ Stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)