#!/usr/bin/env python3
"""
Opinion Farming Bot - Stage 4: Auto Flip (SELL side)
====================================================

PURPOSE:
    Automatically flip position by placing SELL order after BUY fills.

WHAT IT DOES:
    1. Loads state from state.json (must be BUY_FILLED)
    2. Gets fresh orderbook
    3. Calculates SELL price using SELL_MULTIPLIER (market making strategy)
    4. Places limit SELL order for ALL tokens bought
    5. Monitors until SELL fills
    6. Calculates and displays P&L
    7. If AUTO_REINVEST: runs Stage 1 again
    8. If not AUTO_REINVEST: exits

SELL PRICE CALCULATION (Market Making):
    price = best_ask × SELL_MULTIPLIER
    Example: best_ask = 9.0¢, SELL_MULTIPLIER = 0.90 → price = 8.1¢
    (With safety check to not cross the spread)

P&L CALCULATION:
    pnl = sell_proceeds - buy_cost
    pnl_percent = (pnl / buy_cost) × 100

USAGE:
    python mvp_stage4.py

PREREQUISITES:
    - Stage 3 must have completed (BUY filled)
    - state.json must have stage="BUY_FILLED" and filled_amount

STATE UPDATED:
    - stage: SELL_PLACED → SELL_FILLED → COMPLETED
    - sell_order_id, sell_price
    - P&L data

NEXT STEPS:
    If AUTO_REINVEST=True:
        Bot automatically runs Stage 1 to find new market
    If AUTO_REINVEST=False:
        Bot exits (position closed)
"""

import sys
import time
from datetime import datetime

# Local imports
from config import (
    validate_config,
    BONUS_MARKETS_FILE,
    FILL_CHECK_INTERVAL_SECONDS,
    SELL_MULTIPLIER,
    SAFETY_MARGIN_CENTS,
    AUTO_REINVEST
)
from logger_config import setup_logger, log_startup_banner
from api_client import create_client
from market_scanner import MarketScanner
from order_manager import OrderManager
from position_tracker import PositionTracker
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
    Main function for Stage 4: Auto Flip (SELL side).
    
    Returns:
        0 on success, 1 on failure
    """
    # =========================================================================
    # STARTUP
    # =========================================================================
    log_startup_banner(logger, "Stage 4: Auto Flip (SELL)")
    
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
        logger.error("Run Stage 2 and 3 first:")
        logger.error("   python mvp_stage2.py")
        logger.error("   python mvp_stage3.py")
        return 1
    
    # Validate state
    stage = state.get('stage', '')
    
    if stage == 'BUY_PLACED':
        logger.error("BUY order not yet filled!")
        logger.info("Run Stage 3 to monitor for fill:")
        logger.info("   python mvp_stage3.py")
        return 1
    
    if stage not in ['BUY_FILLED', 'SELL_PLACED']:
        logger.error(f"Invalid stage: '{stage}'")
        logger.error("Expected 'BUY_FILLED' or 'SELL_PLACED'")
        return 1
    
    # Extract state details
    market_id = state.get('market_id')
    token_id = state.get('token_id', '')
    filled_amount = safe_float(state.get('filled_amount', 0))
    buy_price = safe_float(state.get('avg_fill_price', 0))
    buy_cost = safe_float(state.get('amount_usdt', 0))
    market_title = state.get('market_title', 'Unknown')
    
    if filled_amount <= 0:
        logger.error("No filled_amount in state!")
        return 1
    
    logger.info(f"✅ Position found:")
    logger.info(f"   Market: #{market_id} - {market_title}")
    logger.info(f"   Tokens: {filled_amount:.4f} YES")
    logger.info(f"   Buy price: {format_price(buy_price)}")
    logger.info(f"   Buy cost: {format_usdt(buy_cost)}")
    logger.info("")
    
    # Quick check: verify we still have the tokens
    try:
        client_check = create_client()
        positions = client_check.get_positions(market_id=market_id)
        actual_tokens = 0.0
        
        if positions:
            for pos in positions:
                # Match by market_id only (outcome can be YES, UP, etc.)
                if pos.get('market_id') == market_id:
                    # API returns shares_owned and shares_frozen
                    shares_owned = pos.get('shares_owned', 0)
                    actual_tokens = safe_float(shares_owned)
                    logger.debug(f"Position for market {market_id}: {actual_tokens:.4f} tokens")
                    break
        
        if actual_tokens < 1.0 and stage == 'BUY_FILLED':
            logger.warning(f"⚠️  Position appears to be sold (only {actual_tokens:.4f} tokens left)")
            logger.info("Marking as completed...")
            state['stage'] = 'COMPLETED'
            state['manual_sell'] = True
            save_state(state)
            logger.info("Run Stage 1 or 2 to start new cycle.")
            return 0
    except:
        pass  # If check fails, continue normally
    
    logger.info("")
    
    # =========================================================================
    # INITIALIZE CLIENT & SCANNER
    # =========================================================================
    try:
        logger.info("🔌 Connecting to Opinion.trade...")
        client = create_client()
        scanner = MarketScanner(client)
        order_manager = OrderManager(client)
        tracker = PositionTracker()
        logger.info("   Connected ✓")
    except Exception as e:
        logger.error(f"Failed to initialize client: {e}")
        return 1
    
    # =========================================================================
    # SELL ORDER PLACEMENT (if not already placed)
    # =========================================================================
    sell_order_id = state.get('sell_order_id', '')
    
    if stage == 'BUY_FILLED':
        # Need to place SELL order
        logger.info("📈 Getting fresh orderbook...")
        
        fresh_orderbook = scanner.get_fresh_orderbook(market_id, token_id)
        
        if not fresh_orderbook:
            logger.error("Failed to get fresh orderbook!")
            return 1
        
        best_bid = fresh_orderbook['best_bid']
        best_ask = fresh_orderbook['best_ask']
        spread_pct = fresh_orderbook['spread_pct']
        
        logger.info(f"   Best Bid: {format_price(best_bid)}")
        logger.info(f"   Best Ask: {format_price(best_ask)}")
        logger.info(f"   Spread: {format_percent(spread_pct)}")
        logger.info("")
        
        # Calculate SELL price using Market Making strategy
        logger.info("🎲 Calculating SELL price (Market Making)...")
        
        spread = best_ask - best_bid
        UNDERCUT_AMOUNT = 0.001  # 10 centów (0.1¢)
        MIN_SPREAD_FOR_UNDERCUT = 0.001  # Tylko undercut jeśli spread > 10 centów
        
        if spread > MIN_SPREAD_FOR_UNDERCUT:
            # Spread jest szeroki - undercut o 10 centów
            sell_price = best_ask - UNDERCUT_AMOUNT
            strategy = f"undercut by {UNDERCUT_AMOUNT*100:.1f}¢"
        else:
            # Spread minimalny - dołącz do najlepszej oferty
            sell_price = best_ask
            strategy = "join best ask (tight spread)"
        
        # Safety check: upewnij się że nie przechodzimy przez bid
        if sell_price <= best_bid:
            logger.warning(f"⚠️ Calculated price {format_price(sell_price)} would cross bid {format_price(best_bid)}")
            sell_price = best_ask
            strategy = "join best ask (safety)"
            logger.warning(f"⚠️ Adjusted to safe price: {format_price(sell_price)}")
        
        sell_price = round_price(sell_price)
        
        logger.info(f"   Market Making Strategy:")
        logger.info(f"   Best bid: {format_price(best_bid)}")
        logger.info(f"   Best ask: {format_price(best_ask)}")
        logger.info(f"   Spread: {format_price(spread)} ({format_percent(spread_pct)})")
        logger.info(f"   Strategy: {strategy}")
        logger.info(f"   Final price: {format_price(sell_price)}")
        logger.info("")
        
        # Estimate proceeds
        estimated_proceeds = filled_amount * sell_price
        estimated_pnl = estimated_proceeds - buy_cost
        
        logger.info("💰 SELL Order Parameters:")
        logger.info(f"   Side: SELL")
        logger.info(f"   Type: LIMIT")
        logger.info(f"   Price: {format_price(sell_price)}")
        logger.info(f"   Amount: {filled_amount:.4f} tokens")
        logger.info(f"   Est. proceeds: {format_usdt(estimated_proceeds)}")
        logger.info(f"   Est. P&L: {format_usdt(estimated_pnl)} ({format_percent(estimated_pnl/buy_cost*100 if buy_cost > 0 else 0)})")
        logger.info("")
        
        # VALIDATION: Check actual token balance before placing SELL
        logger.info("🔍 Checking token balance...")
        
        # Get positions to see actual token balance
        positions = client.get_positions(market_id=market_id)
        actual_tokens = 0.0
        
        if positions:
            for pos in positions:
                # Match by market_id only (outcome can be YES, UP, etc.)
                if pos.get('market_id') == market_id:
                    # API returns shares_owned and shares_frozen
                    shares_owned = pos.get('shares_owned', 0)
                    actual_tokens = safe_float(shares_owned)
                    logger.debug(f"Position for market {market_id}: {actual_tokens:.4f} tokens")
                    break
        
        logger.info(f"   Expected: {filled_amount:.4f} tokens")
        logger.info(f"   Actual: {actual_tokens:.4f} tokens")
        
        # Check if position was sold manually
        if actual_tokens < 1.0:
            logger.warning("")
            logger.warning("=" * 50)
            logger.warning("⚠️  POSITION ALREADY SOLD")
            logger.warning("=" * 50)
            logger.warning(f"   Only {actual_tokens:.4f} tokens remaining (dust)")
            logger.warning("   It appears you sold the position manually.")
            logger.warning("")
            logger.info("💡 Marking cycle as completed...")
            
            # Try to find the manual sell transaction to calculate PnL
            # For now, just mark as completed with estimated values
            state['stage'] = 'COMPLETED'
            state['manual_sell'] = True
            state['sell_note'] = 'Position sold manually outside bot'
            state['completed_timestamp'] = get_timestamp()
            save_state(state)
            
            logger.info("💾 State updated (stage: COMPLETED)")
            logger.info("")
            logger.info("Cycle closed. Run Stage 1 or 2 to start new cycle.")
            logger.info("")
            return 0
        
        # Check if we have significantly less than expected
        shortage_pct = ((filled_amount - actual_tokens) / filled_amount * 100) if filled_amount > 0 else 0
        
        if shortage_pct > 10:  # More than 10% short
            logger.warning("")
            logger.warning(f"⚠️  Token balance mismatch!")
            logger.warning(f"   Expected: {filled_amount:.4f} tokens")
            logger.warning(f"   Actual: {actual_tokens:.4f} tokens")
            logger.warning(f"   Shortage: {shortage_pct:.1f}%")
            logger.warning("")
            logger.warning("Possible causes:")
            logger.warning("   - Partial manual sell")
            logger.warning("   - Tokens locked in another order")
            logger.warning("   - API sync issue")
            logger.warning("")
            
            # Adjust to actual balance
            logger.info(f"Adjusting SELL amount to actual balance: {actual_tokens:.4f} tokens")
            filled_amount = actual_tokens
            
            # Recalculate estimates
            estimated_proceeds = filled_amount * sell_price
            estimated_pnl = estimated_proceeds - buy_cost
            
            logger.info(f"   New est. proceeds: {format_usdt(estimated_proceeds)}")
            logger.info(f"   New est. P&L: {format_usdt(estimated_pnl)} ({format_percent(estimated_pnl/buy_cost*100 if buy_cost > 0 else 0)})")
            logger.info("")
        
        logger.info("")
        
        # Place SELL order
        logger.info("📤 Placing SELL order...")
        
        result = order_manager.place_sell(
            market_id=market_id,
            token_id=token_id,
            price=sell_price,
            amount_tokens=filled_amount
        )
        
        if not result:
            logger.error("❌ Failed to place SELL order!")
            return 1
        
        sell_order_id = result.get('order_id', result.get('orderId', 'unknown'))
        
        logger.info(f"✅ SELL order placed: {sell_order_id}")
        logger.info("")
        
        # Update state
        state['stage'] = 'SELL_PLACED'
        state['sell_order_id'] = sell_order_id
        state['sell_price'] = sell_price
        state['sell_timestamp'] = get_timestamp()
        save_state(state)
        
        logger.info("💾 State updated (stage: SELL_PLACED)")
    
    else:
        # SELL already placed, just need to monitor
        sell_order_id = state.get('sell_order_id', '')
        sell_price = safe_float(state.get('sell_price', 0))
        logger.info(f"📋 Resuming SELL order monitoring: {sell_order_id}")
    
    # =========================================================================
    # MONITOR SELL ORDER
    # =========================================================================
    logger.info("")
    logger.info(f"⏳ Monitoring SELL order for fill...")
    logger.info(f"   Check interval: {FILL_CHECK_INTERVAL_SECONDS}s")
    logger.info("   Press Ctrl+C to stop")
    logger.info("")
    
    try:
        check_count = 0
        last_liquidity_check = 0
        LIQUIDITY_CHECK_INTERVAL = 5  # Check every 5 iterations
        
        while True:
            check_count += 1
            check_time = datetime.now().strftime("%H:%M:%S")
            
            # =================================================================
            # GET ORDER STATUS
            # =================================================================
            # Get order status
            order = client.get_order(sell_order_id)
            
            if not order:
                logger.warning(f"[{check_time}] ⚠️  Failed to fetch order status")
                
                # Check if order was manually cancelled
                logger.warning(f"[{check_time}] 🔍 Checking if order was cancelled...")
                
                # Try one more time after a pause
                time.sleep(2)
                order_retry = client.get_order(sell_order_id)
                
                if not order_retry:
                    logger.error("")
                    logger.error("=" * 50)
                    logger.error("❌ ORDER NOT FOUND")
                    logger.error("=" * 50)
                    logger.error(f"   Order ID: {sell_order_id}")
                    logger.error("")
                    logger.error("Possible causes:")
                    logger.error("   - Order was manually cancelled on Opinion.trade")
                    logger.error("   - Order expired")
                    logger.error("   - API error")
                    logger.error("")
                    logger.info("💡 Resetting to BUY_FILLED state...")
                    
                    # Reset to BUY_FILLED so we can try again
                    state['stage'] = 'BUY_FILLED'
                    if 'sell_order_id' in state:
                        del state['sell_order_id']
                    save_state(state)
                    
                    logger.info("💾 State reset")
                    logger.info("")
                    logger.info("You still have tokens! Options:")
                    logger.info("   - Run Stage 4 again to place new SELL order")
                    logger.info("   - Sell manually on Opinion.trade")
                    logger.info("")
                    return 1
                else:
                    order = order_retry
            
            # =================================================================
            # PERIODIC LIQUIDITY CHECK
            # =================================================================
            if check_count - last_liquidity_check >= LIQUIDITY_CHECK_INTERVAL:
                try:
                    logger.debug(f"[{check_time}] 🔍 Checking market liquidity...")
                    
                    fresh_orderbook = scanner.get_fresh_orderbook(market_id, token_id)
                    
                    if fresh_orderbook:
                        current_best_bid = fresh_orderbook['best_bid']
                        current_best_ask = fresh_orderbook['best_ask']
                        current_spread_pct = fresh_orderbook['spread_pct']
                        
                        # Check if our SELL price is now above the best ask (we got outbid)
                        if sell_price > current_best_ask:
                            price_diff_pct = ((sell_price - current_best_ask) / current_best_ask * 100)
                            if price_diff_pct > 5:  # More than 5% above
                                logger.warning(f"[{check_time}] ⚠️  Our SELL at {format_price(sell_price)} is {price_diff_pct:.1f}% above best ask {format_price(current_best_ask)}")
                        
                        # Check if best bid dropped significantly (less demand)
                        if sell_price > 0:
                            bid_distance_pct = ((current_best_bid / sell_price) * 100)
                            if bid_distance_pct < 70:  # Bid is <70% of our ask
                                logger.warning(f"[{check_time}] ⚠️  Low demand - Best bid {format_price(current_best_bid)} is far below our ask {format_price(sell_price)}")
                        
                        # Wide spread warning
                        if current_spread_pct > 15.0:
                            logger.warning(f"[{check_time}] ⚠️  Wide spread: {format_percent(current_spread_pct)} - market may be illiquid")
                        else:
                            logger.debug(f"[{check_time}] ✓ Liquidity OK - Bid: {format_price(current_best_bid)}, Ask: {format_price(current_best_ask)}")
                    
                    last_liquidity_check = check_count
                    
                except Exception as e:
                    logger.debug(f"[{check_time}] Liquidity check failed: {e}")
            
            # =================================================================
            # CHECK ORDER STATUS
            # =================================================================
            
            status = order.get('status')  # int: 0=pending, 1=partial, 2=finished, 3=cancelled, 4=expired
            status_enum = order.get('status_enum', 'unknown')  # string: "Pending", "Finished", etc.
            
            # =================================================================
            # CHECK: SELL ORDER FILLED
            # =================================================================
            # Check using status_enum (readable) or status code (2 = Finished)
            if status_enum == 'Finished' or status == 2:
                logger.info("")
                logger.info("=" * 50)
                logger.info(f"✅ SELL ORDER FILLED!")
                logger.info("=" * 50)
                
                # Extract fill data from order
                # API fields: filled_shares (tokens), price (per token), filled_amount (USDT)
                sell_filled = safe_float(order.get('filled_shares', 0))
                avg_sell_price = safe_float(order.get('price', 0))
                sell_proceeds_usdt = safe_float(order.get('filled_amount', 0))
                
                # Validation: if data is missing, try to extract from trades
                if sell_filled == 0 or avg_sell_price == 0:
                    logger.warning("⚠️  Missing fill data in order, extracting from trades...")
                    trades = order.get('trades', [])
                    if trades:
                        total_shares = 0.0
                        total_proceeds = 0.0
                        for trade in trades:
                            # trades array has shares and amount in wei format
                            shares_wei = safe_float(trade.get('shares', 0))
                            amount_wei = safe_float(trade.get('amount', 0))
                            # Convert from wei (18 decimals)
                            shares = shares_wei / (10 ** 18)
                            proceeds = amount_wei / (10 ** 18)
                            total_shares += shares
                            total_proceeds += proceeds
                        
                        sell_filled = total_shares
                        avg_sell_price = (total_proceeds / total_shares) if total_shares > 0 else 0
                        sell_proceeds_usdt = total_proceeds
                        logger.info(f"   Extracted from {len(trades)} trade(s)")
                
                # Calculate proceeds if not extracted from trades
                if sell_proceeds_usdt == 0 and sell_filled > 0:
                    sell_proceeds_usdt = sell_filled * avg_sell_price
                
                logger.info(f"   Sold: {sell_filled:.4f} tokens")
                logger.info(f"   Avg price: {format_price(avg_sell_price)}")
                logger.info(f"   Proceeds: {format_usdt(sell_proceeds_usdt)}")
                logger.info("")
                
                # Calculate P&L
                pnl = tracker.calculate_pnl(
                    buy_cost_usdt=buy_cost,
                    buy_tokens=filled_amount,
                    buy_price=buy_price,
                    sell_tokens=sell_filled,
                    sell_price=avg_sell_price
                )
                
                # Display P&L
                tracker.display_pnl(pnl)
                
                # Update state
                state['stage'] = 'COMPLETED'
                state['sell_filled_amount'] = sell_filled
                state['avg_sell_price'] = avg_sell_price
                state['sell_proceeds'] = sell_proceeds_usdt
                state['pnl'] = float(pnl.pnl)
                state['pnl_percent'] = float(pnl.pnl_percent)
                state['completed_timestamp'] = get_timestamp()
                save_state(state)
                
                logger.info("💾 State saved")
                logger.info("")
                
                # =============================================================
                # AUTO REINVEST?
                # =============================================================
                if AUTO_REINVEST:
                    logger.info("🔄 AUTO_REINVEST = True")
                    logger.info("   Clearing state and searching for new market...")
                    
                    # Clear state for new cycle
                    clear_state()
                    
                    logger.info("")
                    logger.info("Run Stage 1 to find new market:")
                    logger.info("   python mvp_stage1.py")
                    logger.info("")
                    logger.info("Or run Stage 2 to auto-place on best market:")
                    logger.info("   python mvp_stage2.py")
                else:
                    logger.info("AUTO_REINVEST = False")
                    logger.info("Position closed. Bot exiting.")
                
                logger.info("")
                return 0
            
            # =================================================================
            # CHECK: SELL ORDER CANCELLED/EXPIRED
            # =================================================================
            # Check cancelled (status=3, enum="Cancelled") or expired (status=4, enum="Expired")
            if status_enum in ['Cancelled', 'Expired'] or status in [3, 4]:
                logger.error(f"[{check_time}] ❌ SELL order {status_enum}!")
                logger.info("You still have tokens! Options:")
                logger.info("   - Run Stage 4 again to place new SELL order")
                logger.info("   - Sell manually on Opinion.trade")
                
                # Reset to BUY_FILLED so we can try again
                state['stage'] = 'BUY_FILLED'
                if 'sell_order_id' in state:
                    del state['sell_order_id']
                save_state(state)
                
                return 1
            
            # =================================================================
            # PERIODIC TOKEN BALANCE CHECK
            # =================================================================
            # Every 10 checks, verify we still have the tokens
            if check_count % 10 == 0:
                try:
                    positions = client.get_positions(market_id=market_id)
                    actual_tokens = 0.0
                    
                    if positions:
                        for pos in positions:
                            # Match by market_id only (outcome can be YES, UP, etc.)
                            if pos.get('market_id') == market_id:
                                # API returns shares_owned and shares_frozen
                                shares_owned = pos.get('shares_owned', 0)
                                actual_tokens = safe_float(shares_owned)
                                break
                    
                    if actual_tokens < 1.0:
                        logger.error("")
                        logger.error("=" * 50)
                        logger.error("❌ TOKENS DISAPPEARED")
                        logger.error("=" * 50)
                        logger.error(f"   Expected: {filled_amount:.4f} tokens")
                        logger.error(f"   Actual: {actual_tokens:.4f} tokens")
                        logger.error("")
                        logger.error("Tokens were sold manually outside of this order!")
                        logger.error("")
                        logger.info("Cancelling pending order and marking as completed...")
                        
                        # Cancel the order
                        client.cancel_order(sell_order_id)
                        
                        # Mark as completed with manual sell
                        state['stage'] = 'COMPLETED'
                        state['manual_sell'] = True
                        state['completed_timestamp'] = get_timestamp()
                        save_state(state)
                        
                        logger.info("💾 State updated")
                        logger.info("Run Stage 1 or 2 to start new cycle.")
                        return 1
                    
                except Exception as e:
                    logger.debug(f"Token balance check failed: {e}")
            
            # =================================================================
            # ORDER STILL PENDING
            # =================================================================
            if check_count % 1 == 0:
                logger.info(f"[{check_time}] ⏳ SELL {status_enum}... (check #{check_count})")
            
            time.sleep(FILL_CHECK_INTERVAL_SECONDS)
    
    except KeyboardInterrupt:
        logger.info("")
        logger.info("⛔ Monitoring stopped by user")
        logger.info("")
        logger.info("SELL order is still active. Options:")
        logger.info("   - Resume monitoring: python mvp_stage4.py")
        logger.info("   - Cancel manually on Opinion.trade")
        logger.info("")
        return 0
    
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
