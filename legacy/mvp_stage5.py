#!/usr/bin/env python3
"""
Opinion Farming Bot - Stage 5: Competitive Re-Pricing
=====================================================

PURPOSE:
    Actively monitor orderbook and re-price order when outbid by competitors.
    This is the "gradual capitulation" strategy.

WHAT IT DOES:
    1. Loads state from state.json (active BUY order)
    2. Monitors orderbook every 9 seconds
    3. Detects when we're outbid (someone places higher bid)
    4. If improvement >= 0.5%, triggers re-pricing:
       - Cancel current order
       - Calculate new competitive price using BUY_MULTIPLIER
       - Apply capitulation limit (never go below 55-75% of initial)
       - Place new order
    5. After MAX_REPRICING_ATTEMPTS (5), abandon market and search for new one
    6. If order fills during monitoring, transition to Stage 4

RE-PRICING LOGIC (Market Making):
    1. Check: current_best_bid > my_price?
    2. Check: improvement >= MIN_IMPROVEMENT_PERCENT (0.5%)?
    3. Calculate new price: best_bid × BUY_MULTIPLIER
    4. Apply capitulation limit: price >= initial_price × capitulation%
    5. Cancel old order, place new order
    6. Increment repricing_count

CAPITULATION STRATEGY:
    - Randomly select capitulation between 55-75%
    - Never drop below this percentage of initial price
    - Prevents "race to bottom" in competitive markets

PREREQUISITES:
    - Stage 2 must have been run (state.json with BUY order)

USAGE:
    python mvp_stage5.py

STATE UPDATED:
    - repricing_count: incremented on each re-price
    - order_id: updated with new order
    - current_price: updated with new price

MAX REPRICING:
    After 5 re-pricings, bot will:
    - Cancel order
    - Clear state
    - Suggest running Stage 1 to find new market
"""

import sys
import time
import random
from datetime import datetime

# Local imports
from config import (
    validate_config,
    BONUS_MARKETS_FILE,
    ORDER_MONITOR_INTERVAL_SECONDS,
    MAX_REPRICING_ATTEMPTS,
    REPRICING_MIN_CAPITULATION_PERCENT,
    REPRICING_MAX_CAPITULATION_PERCENT,
    MIN_IMPROVEMENT_PERCENT,
    BUY_MULTIPLIER,
    SAFETY_MARGIN_CENTS
)
from logger_config import setup_logger, log_startup_banner
from api_client import create_client
from market_scanner import MarketScanner
from order_manager import OrderManager, update_state_for_fill, update_state_for_reprice
from utils import (
    load_state,
    save_state,
    clear_state,
    format_price,
    format_usdt,
    format_percent,
    safe_float,
    round_price,
    get_timestamp
)


# Initialize logger
logger = setup_logger(__name__)


def main():
    """
    Main function for Stage 5: Competitive Re-Pricing.
    
    Returns:
        0 on success, 1 on failure
    """
    # =========================================================================
    # STARTUP
    # =========================================================================
    log_startup_banner(logger, "Stage 5: Competitive Re-Pricing")
    
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
    initial_price = safe_float(state.get('initial_price', 0))
    current_price = safe_float(state.get('current_price', initial_price))
    amount_usdt = safe_float(state.get('amount_usdt', 0))
    repricing_count = state.get('repricing_count', 0)
    market_title = state.get('market_title', 'Unknown')
    
    if not order_id or not token_id:
        logger.error("Missing order_id or token_id in state!")
        return 1
    
    logger.info(f"✅ Active BUY order found:")
    logger.info(f"   Order ID: {order_id}")
    logger.info(f"   Market: #{market_id} - {market_title}")
    logger.info(f"   Initial price: {format_price(initial_price)}")
    logger.info(f"   Current price: {format_price(current_price)}")
    logger.info(f"   Amount: {format_usdt(amount_usdt)}")
    logger.info(f"   Repricing count: {repricing_count}/{MAX_REPRICING_ATTEMPTS}")
    logger.info("")
    
    # =========================================================================
    # INITIALIZE CLIENT & SCANNER
    # =========================================================================
    try:
        logger.info("🔌 Connecting to Opinion.trade...")
        client = create_client()
        scanner = MarketScanner(client)
        order_manager = OrderManager(client)
        logger.info("   Connected ✓")
    except Exception as e:
        logger.error(f"Failed to initialize client: {e}")
        return 1
    
    # =========================================================================
    # COMPETITIVE MONITORING LOOP
    # =========================================================================
    logger.info("")
    logger.info(f"🔍 Starting competitive monitoring...")
    logger.info(f"   Check interval: {ORDER_MONITOR_INTERVAL_SECONDS}s")
    logger.info(f"   Min improvement threshold: {MIN_IMPROVEMENT_PERCENT}%")
    logger.info(f"   Max repricing attempts: {MAX_REPRICING_ATTEMPTS}")
    logger.info("   Press Ctrl+C to stop")
    logger.info("")
    
    try:
        while True:
            check_time = datetime.now().strftime("%H:%M:%S")
            
            # =================================================================
            # GET CURRENT ORDER STATUS
            # =================================================================
            my_order = client.get_order(order_id)
            
            if not my_order:
                logger.warning(f"[{check_time}] Failed to fetch order status")
                time.sleep(ORDER_MONITOR_INTERVAL_SECONDS)
                continue
            
            status = my_order.get('status', 'unknown')
            my_price = safe_float(my_order.get('price', current_price))
            
            # =================================================================
            # CHECK: ORDER FILLED
            # =================================================================
            if status == 'filled':
                logger.info("")
                logger.info("=" * 50)
                logger.info(f"✅ ORDER FILLED during monitoring!")
                logger.info("=" * 50)
                
                filled_amount = safe_float(my_order.get('filled_amount', 0))
                avg_price = safe_float(my_order.get('average_price', 0))
                
                logger.info(f"   Filled: {filled_amount:.4f} tokens")
                logger.info(f"   Avg price: {format_price(avg_price)}")
                logger.info("")
                
                # Update state
                state = update_state_for_fill(state, my_order)
                save_state(state)
                
                logger.info("💾 State updated (stage: BUY_FILLED)")
                logger.info("")
                logger.info("Next step - Run Stage 4 to flip position:")
                logger.info("   python mvp_stage4.py")
                logger.info("")
                
                return 0
            
            # =================================================================
            # CHECK: ORDER CANCELLED
            # =================================================================
            if status in ['cancelled', 'expired']:
                logger.warning(f"[{check_time}] Order {status}!")
                logger.info("Run Stage 2 to place new order.")
                return 1
            
            # =================================================================
            # GET FRESH ORDERBOOK
            # =================================================================
            fresh_orderbook = scanner.get_fresh_orderbook(market_id, token_id)
            
            if not fresh_orderbook:
                logger.warning(f"[{check_time}] Failed to fetch orderbook")
                time.sleep(ORDER_MONITOR_INTERVAL_SECONDS)
                continue
            
            current_best_bid = fresh_orderbook['best_bid']
            current_best_ask = fresh_orderbook['best_ask']
            
            # =================================================================
            # CHECK: ARE WE OUTBID?
            # =================================================================
            if current_best_bid <= my_price:
                # We're still the best (or tied)
                logger.info(f"[{check_time}] Best bid: {format_price(current_best_bid)} (my order: {format_price(my_price)}) ✅")
                time.sleep(ORDER_MONITOR_INTERVAL_SECONDS)
                continue
            
            # We've been outbid!
            improvement_pct = ((current_best_bid - my_price) / my_price) * 100
            
            logger.info("")
            logger.warning(f"⚠️ [{check_time}] OUTBID DETECTED!")
            logger.info(f"   Their bid: {format_price(current_best_bid)}")
            logger.info(f"   My order: {format_price(my_price)}")
            logger.info(f"   Improvement: {format_percent(improvement_pct)}")
            
            # =================================================================
            # CHECK: IS IMPROVEMENT SIGNIFICANT?
            # =================================================================
            if improvement_pct < MIN_IMPROVEMENT_PERCENT:
                logger.info(f"   Improvement too small (< {MIN_IMPROVEMENT_PERCENT}%), skipping re-price")
                time.sleep(ORDER_MONITOR_INTERVAL_SECONDS)
                continue
            
            # =================================================================
            # CHECK: MAX REPRICING REACHED?
            # =================================================================
            if repricing_count >= MAX_REPRICING_ATTEMPTS:
                logger.warning("")
                logger.warning(f"⚠️ MAX REPRICING ATTEMPTS ({MAX_REPRICING_ATTEMPTS}) REACHED!")
                logger.info("   Abandoning market, cancelling order...")
                
                # Cancel order
                client.cancel_order(order_id)
                logger.info("   ❌ Order cancelled")
                
                # Clear state
                clear_state()
                logger.info("   💾 State cleared")
                
                logger.info("")
                logger.info("🔄 Search for new market:")
                logger.info("   python mvp_stage1.py")
                logger.info("   python mvp_stage2.py")
                logger.info("")
                
                return 0
            
            # =================================================================
            # RE-PRICING LOGIC (Market Making Strategy)
            # =================================================================
            logger.info("")
            logger.info(f"🔄 Initiating re-price #{repricing_count + 1}/{MAX_REPRICING_ATTEMPTS}...")
            
            # Calculate capitulation limit
            capitulation_pct = random.uniform(
                REPRICING_MIN_CAPITULATION_PERCENT,
                REPRICING_MAX_CAPITULATION_PERCENT
            )
            min_acceptable_price = initial_price * (capitulation_pct / 100)
            
            logger.info(f"   Capitulation: {capitulation_pct:.1f}% (min: {format_price(min_acceptable_price)})")
            
            # Calculate new competitive price using Market Making strategy
            competitive_price = current_best_bid * BUY_MULTIPLIER
            
            # Safety check: don't cross the spread
            max_safe_price = current_best_ask - SAFETY_MARGIN_CENTS
            if competitive_price >= max_safe_price:
                competitive_price = max_safe_price
            
            # Apply capitulation limit
            new_price = max(competitive_price, min_acceptable_price)
            new_price = round_price(new_price)
            
            logger.info(f"   New spread: {format_price(current_best_bid)} - {format_price(current_best_ask)}")
            logger.info(f"   Competitive: {format_price(competitive_price)} (bid × {BUY_MULTIPLIER})")
            logger.info(f"   Final price: {format_price(new_price)}")
            
            # Cancel old order
            logger.info(f"   Cancelling old order...")
            if not client.cancel_order(order_id):
                logger.error("   Failed to cancel order!")
                time.sleep(ORDER_MONITOR_INTERVAL_SECONDS)
                continue
            
            logger.info(f"   ❌ Old order cancelled")
            
            # Small delay for order book to update
            time.sleep(1)
            
            # Place new order
            logger.info(f"   Placing new order @ {format_price(new_price)}...")
            
            result = order_manager.place_buy(
                market_id=market_id,
                token_id=token_id,
                price=new_price,
                amount_usdt=amount_usdt
            )
            
            if not result:
                logger.error("   Failed to place new order!")
                logger.error("   State may be inconsistent. Check Opinion.trade UI.")
                return 1
            
            # Update tracking
            new_order_id = result.get('order_id', result.get('orderId', ''))
            repricing_count += 1
            
            # Update state
            state = update_state_for_reprice(state, new_order_id, new_price)
            state['repricing_count'] = repricing_count
            save_state(state)
            
            # Update local variables
            order_id = new_order_id
            current_price = new_price
            
            logger.info(f"   ✅ New order: {new_order_id}")
            logger.info(f"   Re-price #{repricing_count} complete: {format_price(my_price)} → {format_price(new_price)}")
            logger.info("")
            
            time.sleep(ORDER_MONITOR_INTERVAL_SECONDS)
    
    except KeyboardInterrupt:
        logger.info("")
        logger.info("⛔ Monitoring stopped by user")
        logger.info("")
        logger.info("Order is still active. Options:")
        logger.info("   - Resume competitive monitoring: python mvp_stage5.py")
        logger.info("   - Passive monitoring: python mvp_stage3.py")
        logger.info("   - Cancel manually on Opinion.trade")
        logger.info("")
        return 0
    
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
