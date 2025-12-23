#!/usr/bin/env python3
"""
Opinion Farming Bot - Stage 3: Fill Monitor + Notify
====================================================

PURPOSE:
    Passively monitor an order until it fills, then notify and update state.

WHAT IT DOES:
    1. Loads state from state.json
    2. Validates state (must have active BUY order)
    3. Enters monitoring loop (every 9 seconds):
       - Check order status
       - If filled: log details, update state, exit
       - If cancelled/expired: log error, exit
       - If pending: continue monitoring
    4. Updates state to BUY_FILLED when order fills

USAGE:
    python mvp_stage3.py

PREREQUISITES:
    - Stage 2 must have been run (order placed)
    - state.json must exist with stage="BUY_PLACED"

OUTPUT:
    - Continuous status updates every 9 seconds
    - Fill notification with details when order fills
    - Updated state.json with filled_amount and avg_fill_price

NEXT STEPS:
    After BUY fills, run Stage 4 to flip position:
    python mvp_stage4.py
"""

import sys
import time
from datetime import datetime

# Local imports
from config import (
    validate_config,
    FILL_CHECK_INTERVAL_SECONDS
)
from logger_config import setup_logger, log_startup_banner
from api_client import create_client
from order_manager import update_state_for_fill
from utils import (
    load_state,
    save_state,
    format_price,
    format_usdt,
    safe_float,
    get_timestamp
)


# Initialize logger
logger = setup_logger(__name__)


def main():
    """
    Main function for Stage 3: Fill Monitor + Notify.
    
    Returns:
        0 on success, 1 on failure
    """
    # =========================================================================
    # STARTUP
    # =========================================================================
    log_startup_banner(logger, "Stage 3: Fill Monitor")
    
    # Validate configuration
    logger.info("🔧 Validating configuration...")
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
    
    # =========================================================================
    # LOAD STATE
    # =========================================================================
    logger.info("📂 Loading state from state.json...")
    
    state = load_state()
    
    if not state:
        logger.error("No state file found!")
        logger.error("Run Stage 2 first to place an order:")
        logger.error("   python mvp_stage2.py")
        return 1
    
    # Validate state
    stage = state.get('stage', '')
    
    if stage != 'BUY_PLACED':
        logger.error(f"Invalid stage: '{stage}'")
        logger.error("Expected 'BUY_PLACED'")
        
        if stage == 'BUY_FILLED':
            logger.info("BUY already filled! Run Stage 4:")
            logger.info("   python mvp_stage4.py")
        return 1
    
    # Extract state details
    order_id = state.get('order_id', '')
    market_id = state.get('market_id')
    token_id = state.get('token_id', '')
    amount_usdt = safe_float(state.get('amount_usdt', 0))
    current_price = safe_float(state.get('current_price', 0))
    market_title = state.get('market_title', 'Unknown')
    
    if not order_id:
        logger.error("Missing order_id in state!")
        return 1
    
    logger.info(f"✅ Active BUY order found:")
    logger.info(f"   Order ID: {order_id}")
    logger.info(f"   Market: #{market_id} - {market_title}")
    logger.info(f"   Price: {format_price(current_price)}")
    logger.info(f"   Amount: {format_usdt(amount_usdt)}")
    logger.info("")
    
    # =========================================================================
    # INITIALIZE CLIENT
    # =========================================================================
    try:
        logger.info("🔌 Connecting to Opinion.trade...")
        client = create_client()
        logger.info("   Connected ✓")
    except Exception as e:
        logger.error(f"Failed to initialize client: {e}")
        return 1
    
    # =========================================================================
    # MONITORING LOOP
    # =========================================================================
    logger.info("")
    logger.info(f"⏳ Starting fill monitoring...")
    logger.info(f"   Check interval: {FILL_CHECK_INTERVAL_SECONDS}s")
    logger.info("   Press Ctrl+C to stop")
    logger.info("")
    
    try:
        check_count = 0
        last_liquidity_check = 0
        LIQUIDITY_CHECK_INTERVAL = 5  # Check every 5 iterations
        initial_best_bid = current_price  # From state
        
        while True:
            check_count += 1
            check_time = datetime.now().strftime("%H:%M:%S")
            
            # =================================================================
            # PERIODIC LIQUIDITY CHECK
            # =================================================================
            if check_count - last_liquidity_check >= LIQUIDITY_CHECK_INTERVAL:
                try:
                    logger.debug(f"[{check_time}] 🔍 Checking market liquidity...")
                    
                    from market_scanner import MarketScanner
                    scanner = MarketScanner(client)
                    fresh_orderbook = scanner.get_fresh_orderbook(market_id, token_id)
                    
                    if fresh_orderbook:
                        current_best_bid = fresh_orderbook['best_bid']
                        current_spread_pct = fresh_orderbook['spread_pct']
                        
                        # Check if best bid dropped significantly
                        bid_drop_pct = ((initial_best_bid - current_best_bid) / initial_best_bid * 100) if initial_best_bid > 0 else 0
                        
                        # Alert thresholds
                        BID_DROP_ALERT = 20.0  # Alert if bid drops >20%
                        SPREAD_ALERT = 10.0    # Alert if spread >10%
                        
                        if bid_drop_pct > BID_DROP_ALERT:
                            logger.warning("")
                            logger.warning("=" * 50)
                            logger.warning("⚠️  LIQUIDITY WARNING - BID DROPPED")
                            logger.warning("=" * 50)
                            logger.warning(f"   Initial bid: {format_price(initial_best_bid)}")
                            logger.warning(f"   Current bid: {format_price(current_best_bid)}")
                            logger.warning(f"   Drop: {bid_drop_pct:.1f}%")
                            logger.warning("")
                            logger.warning("Market conditions deteriorated significantly.")
                            logger.warning("Your BUY order may not fill at good price.")
                            logger.warning("")
                            logger.warning("Options:")
                            logger.warning("   1. Continue monitoring (press Enter)")
                            logger.warning("   2. Cancel order and exit (Ctrl+C)")
                            logger.warning("")
                            
                            try:
                                input("Press Enter to continue monitoring... ")
                            except KeyboardInterrupt:
                                logger.info("")
                                logger.info("Exiting monitoring...")
                                raise
                        
                        elif current_spread_pct > SPREAD_ALERT:
                            logger.warning(f"[{check_time}] ⚠️  Wide spread detected: {format_percent(current_spread_pct)}")
                        
                        else:
                            logger.debug(f"[{check_time}] ✓ Liquidity OK - Bid: {format_price(current_best_bid)}, Spread: {format_percent(current_spread_pct)}")
                    
                    last_liquidity_check = check_count
                    
                except Exception as e:
                    logger.debug(f"[{check_time}] Liquidity check failed: {e}")
                    # Don't stop monitoring if liquidity check fails
            
            # =================================================================
            # GET ORDER STATUS
            # =================================================================
            # Get order status
            order = client.get_order(order_id)
            
            if not order:
                logger.warning(f"[{check_time}] Failed to fetch order status")
                time.sleep(FILL_CHECK_INTERVAL_SECONDS)
                continue
            
            status = order.get('status')  # int: 0=pending, 1=partial, 2=finished, 3=cancelled, 4=expired
            status_enum = order.get('status_enum', 'unknown')  # string: "Pending", "Finished", etc.
            
            # =================================================================
            # CHECK: ORDER FILLED
            # =================================================================
            # Check using status_enum (readable) or status code (2 = Finished)
            if status_enum == 'Finished' or status == 2:
                logger.info("")
                logger.info("=" * 50)
                logger.info(f"✅ BUY ORDER FILLED!")
                logger.info("=" * 50)
                
                # Extract fill data from order
                # API fields: filled_shares (tokens), price (per token), filled_amount (USDT)
                filled_shares = safe_float(order.get('filled_shares', 0))
                fill_price = safe_float(order.get('price', 0))
                filled_usdt = safe_float(order.get('filled_amount', 0))
                
                # Validation: if data is missing, try to extract from trades
                if filled_shares == 0 or fill_price == 0:
                    logger.warning("⚠️  Missing fill data in order, extracting from trades...")
                    trades = order.get('trades', [])
                    if trades:
                        total_shares = 0.0
                        total_cost = 0.0
                        for trade in trades:
                            # trades array has shares and amount in wei format
                            shares_wei = safe_float(trade.get('shares', 0))
                            amount_wei = safe_float(trade.get('amount', 0))
                            # Convert from wei (18 decimals)
                            shares = shares_wei / (10 ** 18)
                            cost = amount_wei / (10 ** 18)
                            total_shares += shares
                            total_cost += cost
                        
                        filled_shares = total_shares
                        fill_price = (total_cost / total_shares) if total_shares > 0 else 0
                        filled_usdt = total_cost
                        logger.info(f"   Extracted from {len(trades)} trade(s)")
                
                logger.info(f"   Filled: {filled_shares:.4f} YES tokens")
                logger.info(f"   Avg price: {format_price(fill_price)}")
                logger.info(f"   Total cost: {format_usdt(filled_usdt)}")
                logger.info("")
                
                # Update state manually (don't use update_state_for_fill which might have old logic)
                state['stage'] = 'BUY_FILLED'
                state['filled_amount'] = filled_shares  # CRITICAL: Store token count, not USDT!
                state['avg_fill_price'] = fill_price
                state['fill_timestamp'] = get_timestamp()
                save_state(state)
                
                logger.info("💾 State updated (stage: BUY_FILLED)")
                logger.info("")
                logger.info("Next step - Run Stage 4 to flip position:")
                logger.info("   python mvp_stage4.py")
                logger.info("")
                
                return 0
            
            # =================================================================
            # CHECK: ORDER CANCELLED/EXPIRED
            # =================================================================
            # Check cancelled (status=3, enum="Cancelled") or expired (status=4, enum="Expired")
            if status_enum in ['Cancelled', 'Expired'] or status in [3, 4]:
                logger.error(f"[{check_time}] ❌ Order {status_enum}!")
                logger.info("The order was cancelled or expired.")
                logger.info("Possible causes:")
                logger.info("   - Market was resolved")
                logger.info("   - Order was cancelled manually")
                logger.info("   - Insufficient balance")
                logger.info("")
                logger.info("Run Stage 2 to place a new order:")
                logger.info("   python mvp_stage2.py")
                return 1
            
            # =================================================================
            # ORDER STILL PENDING
            # =================================================================
            # Log every check (or every Nth check to reduce verbosity)
            if check_count % 1 == 0:  # Change to % 5 for less verbose
                logger.info(f"[{check_time}] ⏳ Order {status_enum}... (check #{check_count})")
            
            time.sleep(FILL_CHECK_INTERVAL_SECONDS)
    
    except KeyboardInterrupt:
        logger.info("")
        logger.info("⛔ Monitoring stopped by user")
        logger.info("")
        logger.info("Order is still active. Options:")
        logger.info("   - Resume monitoring: python mvp_stage3.py")
        logger.info("   - Competitive monitoring: python mvp_stage5.py")
        logger.info("   - Cancel manually on Opinion.trade")
        logger.info("")
        return 0
    
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
