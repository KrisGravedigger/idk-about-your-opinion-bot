#!/usr/bin/env python3
"""
Opinion Farming Bot - TEST ORDER PLACER
========================================

⚠️  WARNING: THIS IS A TEST UTILITY - NOT FOR PRODUCTION USE ⚠️

PURPOSE:
    Place a small test order on a LIQUID market with TIGHT spread
    for testing Stage 4 sell functionality.

DIFFERENCE FROM STAGE 2:
    Stage 2: Selects best farming markets (low liquidity, wide spreads)
    THIS:    Selects most liquid markets (tight spreads, high volume)
             for easy order fulfillment

WHAT IT DOES:
    1. Scans markets with INVERTED ranking (tight spread = best)
    2. Selects the most liquid market (smallest spread)
    3. Places SMALL order (5-10 USDT) very close to ASK (98-99%)
    4. Saves state to state.json
    5. Someone quickly fills your order
    6. You can then test Stage 4 (sell)

USAGE:
    python place_test_order.py

STATE SAVED:
    state.json with:
    - market_id, token_id
    - order_id, price
    - amount, side
    - repricing_count = 0
    
    (Same format as Stage 2 - Stage 4 will work normally)

NEXT STEPS:
    After order is FILLED (check web UI or wait for notification):
    python mvp_stage4.py
"""

import sys
import random

# Local imports
from config import (
    validate_config,
    BONUS_MARKETS_FILE,
    BUY_MULTIPLIER,
    SAFETY_MARGIN_CENTS
)
from logger_config import setup_logger, log_startup_banner
from api_client import create_client
from market_scanner import MarketScanner
from order_manager import OrderManager, create_buy_state
from utils import (
    format_price,
    format_percent,
    format_usdt,
    save_state,
    round_price
)


# ============================================================================
# TEST CONFIGURATION
# ============================================================================
TEST_ORDER_AMOUNT_USDT = 15.0  # Small test amount
TEST_POSITION_MIN_PCT = 98    # Very close to ASK (98% of spread)
TEST_POSITION_MAX_PCT = 99    # Maximum 99% of spread


# Initialize logger
logger = setup_logger(__name__)


def main():
    """
    Main function for TEST ORDER PLACEMENT.
    
    Returns:
        0 on success, 1 on failure
    """
    # =========================================================================
    # STARTUP - WITH TEST MODE WARNING
    # =========================================================================
    logger.info("=" * 80)
    logger.info("⚠️  TEST MODE - NOT PRODUCTION ⚠️")
    logger.info("=" * 80)
    log_startup_banner(logger, "TEST ORDER PLACER")
    logger.info("")
    logger.info("🎯 Purpose: Place test order on LIQUID market for Stage 4 testing")
    logger.info(f"💰 Test amount: {TEST_ORDER_AMOUNT_USDT} USDT (small)")
    logger.info(f"📍 Position: {TEST_POSITION_MIN_PCT}-{TEST_POSITION_MAX_PCT}% of spread (close to ASK)")
    logger.info("")
    
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
    # FIND MOST LIQUID MARKET (INVERTED LOGIC)
    # =========================================================================
    try:
        logger.info("📊 Running market scanner (INVERTED for tight spread markets)...")
        
        scanner = MarketScanner(client)
        scanner.load_bonus_markets(BONUS_MARKETS_FILE)
        
        # Get markets (use same scan method)
        all_markets = scanner.scan_and_rank(limit=20)  # Get more candidates
        
        if not all_markets:
            logger.error("No suitable markets found!")
            return 1
        
        # =====================================================================
        # INVERT RANKING: Prefer LIQUID markets with TIGHT spreads
        # =====================================================================
        logger.info("")
        logger.info("🔄 Re-ranking markets for TEST (tightest spread = best)...")
        
        # Sort by smallest spread (best indicator of liquidity)
        # This is OPPOSITE of production logic
        liquid_markets = sorted(
            all_markets,
            key=lambda x: x.spread_pct  # Smallest spread = most liquid
        )
        
        # Select most liquid market
        selected = liquid_markets[0]
        
        logger.info("")
        logger.info(f"✅ Selected LIQUID market: #{selected.market_id}")
        logger.info(f"   Spread: {format_percent(selected.spread_pct)} (TIGHT)")
        logger.info(f"   Score: {selected.score:.2f} (ignored in test mode)")
        logger.info("")
        
        # Show why this is different from production
        production_pick = all_markets[0]
        if production_pick.market_id != selected.market_id:
            logger.info("ℹ️  Note: Production Stage 2 would pick a DIFFERENT market:")
            logger.info(f"   Production choice: #{production_pick.market_id} (score {production_pick.score:.2f})")
            logger.info(f"   Test choice: #{selected.market_id} (most liquid)")
        
        logger.info("")
        
        # =====================================================================
        # GET FRESH ORDERBOOK
        # =====================================================================
        logger.info("📈 Market Details:")
        
        # Get fresh prices
        fresh_orderbook = scanner.get_fresh_orderbook(selected.market_id, selected.yes_token_id)
        
        if not fresh_orderbook:
            logger.error("Failed to get fresh orderbook!")
            return 1
        
        best_bid = fresh_orderbook['best_bid']
        best_ask = fresh_orderbook['best_ask']
        spread_abs = fresh_orderbook['spread_abs']
        spread_pct = fresh_orderbook['spread_pct']
        
        logger.info(f"   Title: {selected.title}")
        logger.info(f"   Best Bid: {format_price(best_bid)}")
        logger.info(f"   Best Ask: {format_price(best_ask)}")
        logger.info(f"   Spread: {format_percent(spread_pct)} ({format_price(spread_abs)})")
        if selected.is_bonus:
            logger.info(f"   🌟 BONUS MARKET")
        logger.info("")
        
        # =====================================================================
        # CALCULATE ORDER PRICE (CLOSE TO ASK FOR QUICK FILL)
        # =====================================================================
        logger.info("🎲 Calculating test order price (close to ASK)...")
        
        # Random position between 98-99% of spread (very aggressive)
        position_percent = random.uniform(TEST_POSITION_MIN_PCT, TEST_POSITION_MAX_PCT)
        
        # Calculate price
        gap = best_ask - best_bid
        price = best_bid + (gap * position_percent / 100)
        
        # Safety check
        max_safe_price = best_ask - SAFETY_MARGIN_CENTS
        if price >= max_safe_price:
            logger.warning(f"⚠️ Calculated price {format_price(price)} would cross ask {format_price(best_ask)}")
            price = max_safe_price
            logger.warning(f"⚠️ Adjusted to safe price: {format_price(price)}")
        
        price = round_price(price)
        
        logger.info(f"   TEST Order Positioning (for quick fill):")
        logger.info(f"   Best bid: {format_price(best_bid)}")
        logger.info(f"   Best ask: {format_price(best_ask)}")
        logger.info(f"   Spread: {format_price(gap)}")
        logger.info(f"   Position: {position_percent:.1f}% of spread (CLOSE TO ASK)")
        logger.info(f"   Final price: {format_price(price)}")
        logger.info(f"   ⚠️  This is {TEST_POSITION_MIN_PCT}-{TEST_POSITION_MAX_PCT}% vs production's ~94-96%")
        
        # =====================================================================
        # CALCULATE ORDER AMOUNT (SMALL TEST AMOUNT)
        # =====================================================================
        amount_usdt = TEST_ORDER_AMOUNT_USDT
        expected_tokens = amount_usdt / price if price > 0 else 0
        
        logger.info("")
        logger.info("💰 Order Parameters (TEST AMOUNT):")
        logger.info(f"   Side: BUY")
        logger.info(f"   Type: LIMIT")
        logger.info(f"   Price: {format_price(price)}")
        logger.info(f"   Amount: {format_usdt(amount_usdt)} ⚠️  TEST AMOUNT")
        logger.info(f"   Expected tokens: ~{expected_tokens:.2f} YES")
        logger.info("")
        
        # =====================================================================
        # PLACE ORDER
        # =====================================================================
        logger.info("🔐 Checking approvals...")
        
        order_manager = OrderManager(client)
        
        result = order_manager.place_buy(
            market_id=selected.market_id,
            token_id=selected.yes_token_id,
            price=price,
            amount_usdt=amount_usdt
        )
        
        if not result:
            logger.error("❌ Failed to place order!")
            logger.error("Check logs for details. Possible causes:")
            logger.error("   - Insufficient USDT balance")
            logger.error("   - API error")
            logger.error("   - Network issue")
            logger.error("   - Bot in READ-ONLY mode (MULTI_SIG_ADDRESS not set)")
            return 1
        
        order_id = result.get('order_id', result.get('orderId', 'unknown'))
        
        logger.info("")
        logger.info("✅ TEST order placed successfully!")
        logger.info(f"   Order ID: {order_id}")
        logger.info(f"   Market: #{selected.market_id}")
        logger.info(f"   Status: Pending")
        logger.info("")
        
        # =====================================================================
        # SAVE STATE (Same format as Stage 2)
        # =====================================================================
        state = create_buy_state(
            market_id=selected.market_id,
            order_id=order_id,
            token_id=selected.yes_token_id,
            price=price,
            position_percent=position_percent,
            amount_usdt=amount_usdt
        )
        
        # Add extra info
        state['market_title'] = selected.title
        state['is_bonus'] = selected.is_bonus
        state['test_mode'] = True  # Flag for identification
        
        if save_state(state):
            logger.info("💾 State saved to state.json")
        else:
            logger.warning("⚠️ Failed to save state!")
        
        # =====================================================================
        # NEXT STEPS
        # =====================================================================
        logger.info("")
        logger.info("=" * 80)
        logger.info("Next steps for testing:")
        logger.info("=" * 80)
        logger.info("")
        logger.info("1. ⏳ Wait for order to be FILLED")
        logger.info("   - Check Opinion.trade web UI")
        logger.info("   - On liquid market with tight spread, should fill quickly")
        logger.info("   - Your order is close to ASK (someone will likely take it)")
        logger.info("")
        logger.info("2. ✅ Once FILLED, test Stage 4:")
        logger.info("   python mvp_stage4.py")
        logger.info("")
        logger.info("3. 🔍 Stage 4 will:")
        logger.info("   - Read state.json (your filled order)")
        logger.info("   - Calculate sell price")
        logger.info("   - Place SELL order to close position")
        logger.info("")
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("\n⛔ Interrupted by user")
        return 0
        
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)