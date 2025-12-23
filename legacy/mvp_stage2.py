#!/usr/bin/env python3
"""
Opinion Farming Bot - Stage 2: Auto Order Placement
===================================================

PURPOSE:
    Automatically place a BUY order on the best market found by the scanner.

WHAT IT DOES:
    1. Runs Stage 1 logic to find best market
    2. Selects the #1 ranked market
    3. Gets fresh orderbook prices
    4. Calculates order price with randomized positioning (93-97% of spread)
    5. Places limit BUY order
    6. Saves state to state.json
    7. Exits (order placed, ready for monitoring)

PRICE CALCULATION:
    position_percent = random(93%, 97%)
    price = best_bid + (spread × position_percent / 100)

USAGE:
    python mvp_stage2.py

STATE SAVED:
    state.json with:
    - market_id, token_id
    - order_id, price
    - amount, side
    - repricing_count = 0

NEXT STEPS:
    After order is placed, choose monitoring mode:
    - Stage 3: Passive monitoring (wait for fill)
      python mvp_stage3.py
    - Stage 5: Competitive monitoring (re-price if outbid)
      python mvp_stage5.py
"""

import sys
import random

# Local imports
from config import (
    validate_config,
    BONUS_MARKETS_FILE,
    TOTAL_CAPITAL_USDT,
    CAPITAL_ALLOCATION_PERCENT
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


# Initialize logger
logger = setup_logger(__name__)


def main():
    """
    Main function for Stage 2: Auto Order Placement.
    
    Returns:
        0 on success, 1 on failure
    """
    # =========================================================================
    # STARTUP
    # =========================================================================
    log_startup_banner(logger, "Stage 2: Auto Order Placement")
    
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
    # FIND BEST MARKET (Run Stage 1 logic)
    # =========================================================================
    try:
        logger.info("📊 Running market scanner...")
        
        scanner = MarketScanner(client)
        scanner.load_bonus_markets(BONUS_MARKETS_FILE)
        
        top_markets = scanner.scan_and_rank(limit=5)
        
        if not top_markets:
            logger.error("No suitable markets found!")
            return 1
        
        # Select best market
        selected = top_markets[0]
        
        logger.info(f"✅ Selected market: #{selected.market_id} (Score: {selected.score:.2f})")
        logger.info("")
        
        # =====================================================================
        # GET FRESH ORDERBOOK
        # =====================================================================
        logger.info("📈 Market Details:")
        
        # Get fresh prices (they may have changed since scan)
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
        # CALCULATE ORDER PRICE
        # =====================================================================
        logger.info("🎲 Calculating order price...")
        
        # Import new config parameters
        from config import BUY_MULTIPLIER, SAFETY_MARGIN_CENTS
        
        # Calculate price: simple multiplier (market making strategy)
        gap = best_ask - best_bid
        price = best_bid * BUY_MULTIPLIER
        
        # Safety check
        max_safe_price = best_ask - SAFETY_MARGIN_CENTS
        if price >= max_safe_price:
            logger.warning(f"⚠️ Calculated price {format_price(price)} would cross ask {format_price(best_ask)}")
            price = max_safe_price
            logger.warning(f"⚠️ Adjusted to safe price: {format_price(price)}")
        
        price = round_price(price)
        
        # For state tracking - what % above bid we went
        improvement_pct = ((BUY_MULTIPLIER - 1.0) * 100)
        position_percent = improvement_pct
        
        logger.info(f"   Market Making Strategy:")
        logger.info(f"   Best bid: {format_price(best_bid)}")
        logger.info(f"   Best ask: {format_price(best_ask)}")
        logger.info(f"   Spread: {format_price(gap)}")
        logger.info(f"   Multiplier: {BUY_MULTIPLIER}x (bid × {improvement_pct:.0f}% higher)")
        logger.info(f"   Final price: {format_price(price)}")
        
        # =====================================================================
        # CALCULATE ORDER AMOUNT
        # =====================================================================
        amount_usdt = TOTAL_CAPITAL_USDT * (CAPITAL_ALLOCATION_PERCENT / 100)
        expected_tokens = amount_usdt / price if price > 0 else 0
        
        logger.info("💰 Order Parameters:")
        logger.info(f"   Side: BUY")
        logger.info(f"   Type: LIMIT")
        logger.info(f"   Price: {format_price(price)}")
        logger.info(f"   Amount: {format_usdt(amount_usdt)}")
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
        logger.info("✅ Order placed successfully!")
        logger.info(f"   Order ID: {order_id}")
        logger.info(f"   Market: #{selected.market_id}")
        logger.info(f"   Status: Pending")
        logger.info("")
        
        # =====================================================================
        # SAVE STATE
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
        
        if save_state(state):
            logger.info("💾 State saved to state.json")
        else:
            logger.warning("⚠️ Failed to save state!")
        
        # =====================================================================
        # NEXT STEPS
        # =====================================================================
        logger.info("")
        logger.info("Next steps:")
        logger.info("   - Order is now live on Opinion.trade")
        logger.info("   - Choose monitoring mode:")
        logger.info("")
        logger.info("   Option A: Passive monitoring (just wait for fill)")
        logger.info("   python mvp_stage3.py")
        logger.info("")
        logger.info("   Option B: Competitive monitoring (re-price if outbid)")
        logger.info("   python mvp_stage5.py")
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
