#!/usr/bin/env python3
"""
Opinion Farming Bot - Stage 1: Market Scanner
=============================================

PURPOSE:
    Find and rank the best markets for liquidity provision based on
    spread size and bonus status.

WHAT IT DOES:
    1. Fetches all active markets from Opinion.trade
    2. Loads bonus market IDs from bonus_markets.txt
    3. Analyzes each market's orderbook
    4. Calculates score = spread_percentage × bonus_multiplier
    5. Displays top 10 markets in formatted table
    6. Exits (no state saved - this is just discovery)

USAGE:
    python mvp_stage1.py

OUTPUT:
    Formatted table showing top markets with:
    - Rank
    - Market ID & Title
    - Spread %
    - Best Bid/Ask prices
    - Score (higher = more attractive)

NEXT STEPS:
    After reviewing results, run Stage 2 to auto-place order on best market:
    python mvp_stage2.py
"""

import sys

# Local imports
from config import validate_config, BONUS_MARKETS_FILE
from logger_config import setup_logger, log_startup_banner
from api_client import create_client
from market_scanner import MarketScanner
from utils import format_price, format_percent


# Initialize logger
logger = setup_logger(__name__)


def main():
    """
    Main function for Stage 1: Market Scanner.
    
    Returns:
        0 on success, 1 on failure
    """
    # =========================================================================
    # STARTUP
    # =========================================================================
    log_startup_banner(logger, "Stage 1: Market Scanner")
    
    # Validate configuration
    logger.info("🔧 Validating configuration...")
    is_valid, errors, warnings = validate_config()
    
    if not is_valid:
        logger.error("Configuration errors found:")
        for error in errors:
            logger.error(f"   - {error}")
        logger.error("Please fix configuration and try again.")
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
    # SCAN MARKETS
    # =========================================================================
    try:
        # Create scanner
        scanner = MarketScanner(client)
        
        # Load bonus markets
        scanner.load_bonus_markets(BONUS_MARKETS_FILE)
        
        # Scan and rank markets
        top_markets = scanner.scan_and_rank(limit=10)
        
        if not top_markets:
            logger.warning("No markets found that meet criteria!")
            logger.info("Check that:")
            logger.info("   - There are active markets on Opinion.trade")
            logger.info("   - Markets have valid orderbooks (bids AND asks)")
            return 1
        
        # =====================================================================
        # DISPLAY RESULTS
        # =====================================================================
        logger.info("")
        logger.info("✅ Analysis complete!")
        
        # Display formatted table
        scanner.display_top_markets(top_markets)
        
        # Show recommendation
        best = top_markets[0]
        logger.info("💡 Recommendation:")
        logger.info(f"   Market #{best.market_id} (Score: {best.score:.2f})")
        logger.info(f"   Title: {best.title}")
        logger.info(f"   Spread: {format_percent(best.spread_pct)} ({format_price(best.spread_abs)})")
        logger.info(f"   Best Bid: {format_price(best.best_bid)}")
        logger.info(f"   Best Ask: {format_price(best.best_ask)}")
        
        if best.is_bonus:
            logger.info(f"   🌟 BONUS MARKET - 2x airdrop points!")
        
        logger.info("")
        logger.info("Next steps:")
        logger.info("   - Review top markets manually if desired")
        logger.info("   - Run Stage 2 to auto-place order on best market:")
        logger.info("     python mvp_stage2.py")
        logger.info("")
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("\n⛔ Interrupted by user")
        return 0
        
    except Exception as e:
        logger.exception(f"Unexpected error during market scan: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
