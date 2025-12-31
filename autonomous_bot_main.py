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

# Local imports
from config import validate_config
from logger_config import setup_logger, log_startup_banner
from api_client import create_client
from core.autonomous_bot import AutonomousBot
from utils import clear_state, get_timestamp

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
    
    # Import full config
    from config import (
        # Capital Management
        CAPITAL_MODE,
        CAPITAL_AMOUNT_USDT,
        CAPITAL_PERCENTAGE,
        MIN_BALANCE_TO_CONTINUE_USDT,
        MIN_POSITION_SIZE_USDT,
        MIN_POSITION_FOR_POINTS_USDT,
        WARN_IF_BELOW_POINTS_THRESHOLD,
        
        # Pricing
        SAFETY_MARGIN_CENTS,
        
        # Monitoring
        FILL_CHECK_INTERVAL_SECONDS,
        BUY_ORDER_TIMEOUT_HOURS,
        SELL_ORDER_TIMEOUT_HOURS,
        
        # Liquidity
        LIQUIDITY_AUTO_CANCEL,
        LIQUIDITY_BID_DROP_THRESHOLD,
        LIQUIDITY_SPREAD_THRESHOLD,
        
        # Stop-loss
        ENABLE_STOP_LOSS,
        STOP_LOSS_TRIGGER_PERCENT,
        STOP_LOSS_AGGRESSIVE_OFFSET,
        
        # Bot config
        BONUS_MARKETS_FILE
    )
    
    is_valid, errors, warnings = validate_config()
    
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
    
    # =========================================================================
    # BUILD CONFIG DICT
    # =========================================================================
    config = {
        # Capital Management
        'CAPITAL_MODE': CAPITAL_MODE,
        'CAPITAL_AMOUNT_USDT': CAPITAL_AMOUNT_USDT,
        'CAPITAL_PERCENTAGE': CAPITAL_PERCENTAGE,
        'MIN_BALANCE_TO_CONTINUE_USDT': MIN_BALANCE_TO_CONTINUE_USDT,
        'MIN_POSITION_SIZE_USDT': MIN_POSITION_SIZE_USDT,
        'MIN_POSITION_FOR_POINTS_USDT': MIN_POSITION_FOR_POINTS_USDT,
        'WARN_IF_BELOW_POINTS_THRESHOLD': WARN_IF_BELOW_POINTS_THRESHOLD,
        
        # Pricing
        'SAFETY_MARGIN_CENTS': SAFETY_MARGIN_CENTS,
        
        # Monitoring
        'FILL_CHECK_INTERVAL_SECONDS': FILL_CHECK_INTERVAL_SECONDS,
        'BUY_ORDER_TIMEOUT_HOURS': BUY_ORDER_TIMEOUT_HOURS,
        'SELL_ORDER_TIMEOUT_HOURS': SELL_ORDER_TIMEOUT_HOURS,
        
        # Liquidity
        'LIQUIDITY_AUTO_CANCEL': LIQUIDITY_AUTO_CANCEL,
        'LIQUIDITY_BID_DROP_THRESHOLD': LIQUIDITY_BID_DROP_THRESHOLD,
        'LIQUIDITY_SPREAD_THRESHOLD': LIQUIDITY_SPREAD_THRESHOLD,
        
        # Stop-loss
        'ENABLE_STOP_LOSS': ENABLE_STOP_LOSS,
        'STOP_LOSS_TRIGGER_PERCENT': STOP_LOSS_TRIGGER_PERCENT,
        'STOP_LOSS_AGGRESSIVE_OFFSET': STOP_LOSS_AGGRESSIVE_OFFSET,
        
        # Bot config
        'BONUS_MARKETS_FILE': BONUS_MARKETS_FILE,
        'CYCLE_DELAY_SECONDS': 10,
        'MAX_CYCLES': args.max_cycles
    }
    
    # Display config summary
    display_config_summary(config)
    
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
            positions = client.get_positions()
            
            if positions:
                logger.warning("=" * 70)
                logger.warning("⚠️  ORPHANED POSITION DETECTED!")
                logger.warning(f"   state.json says: {existing_state.get('stage', 'UNKNOWN')}")
                logger.warning(f"   But API shows: {len(positions)} active position(s)")
                logger.warning("=" * 70)
                logger.info("")
                
                # Find first position with significant shares
                for pos in positions:
                    market_id = pos.get('market_id')
                    shares = float(pos.get('shares_owned', 0))
                    
                    if shares >= 1.0:
                        logger.info(f"🔄 AUTO-RECOVERY:")
                        logger.info(f"   Market: #{market_id}")
                        logger.info(f"   Shares: {shares:.4f}")
                        logger.info(f"   Action: Will place SELL to close position")
                        logger.info("")
                        logger.info("💡 Bot will SKIP balance check and proceed to close position")
                        logger.info("")
                        
                        # Force state to BUY_FILLED so bot will place SELL
                        bot.state['stage'] = 'BUY_FILLED'
                        bot.state['current_position'] = {
                            'market_id': market_id,
                            'token_id': pos.get('token_id', ''),
                            'market_title': pos.get('title', f"Recovered market #{market_id}"),
                            'filled_amount': shares,
                            'avg_fill_price': pos.get('avg_price', 0.01),  # Fallback
                            'filled_usdt': shares * pos.get('avg_price', 0.01),
                            'fill_timestamp': get_timestamp()
                        }
                        bot.state_manager.save_state(bot.state)
                        
                        logger.info("✅ State recovered and saved")
                        logger.info(f"📍 Bot will start in BUY_FILLED → SELL_PLACED")
                        logger.info("")
                        
                        has_open_position = True
                        break
                
                if not has_open_position:
                    # None of the positions have significant shares
                    # But check if we have frozen balance (indicates pending order)
                    logger.info("⚠️  Positions exist but all have < 1.0 shares")
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
                                    # ...
                                    
                                    # CRITICAL FIX: Find the market with PENDING order, not just any position
                                    # Strategy: Query pending orders across ALL markets, find one matching frozen amount
                                    recovered_market = None
                                    
                                    try:
                                        logger.info("   🔍 Searching for pending order matching frozen balance...")
                                        
                                        # Get ALL pending orders (no market filter)
                                        all_pending_orders = client.get_my_orders(
                                            market_id=0,
                                            status='FILLED', #(SIC!)
                                            limit=20
                                        )
                                        
                                        logger.info(f"   Found {len(all_pending_orders)} pending orders across all markets")
                                        
                                        # Find order with amount close to frozen balance
                                        for order in all_pending_orders:
                                            order_market_id = order.get('market_id')
                                            order_amount = float(order.get('order_amount', 0) or 0)
                                            
                                            # Match if amounts are close (within $0.50)
                                            if abs(order_amount - frozen_balance) < 0.50:
                                                order_filled = float(order.get('filled_amount', 0) or 0)
                                                order_status = order.get('status_str', 'UNKNOWN')
                                                logger.info(f"   ✅ Found matching order:")
                                                logger.info(f"      Market: #{order_market_id}")
                                                logger.info(f"      Order amount: ${order_amount:.2f}")
                                                logger.info(f"      Frozen balance: ${frozen_balance:.2f}")
                                                
                                                # Find corresponding position (if exists)
                                                for pos in positions:
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
                                            if positions:
                                                recovered_market = positions[0]
                                                
                                    except Exception as e:
                                        logger.warning(f"   Error searching for pending order: {e}")
                                        logger.info("   Using first position as fallback")
                                        if positions:
                                            recovered_market = positions[0]
                                    
                                    if not recovered_market and positions:
                                        # Fallback: use first position
                                        recovered_market = positions[0]
                                    
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
            
            if balance < MIN_BALANCE_TO_CONTINUE_USDT:
                logger.error(f"⚠️  Balance (${balance:.2f}) is below minimum (${MIN_BALANCE_TO_CONTINUE_USDT:.2f})")
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