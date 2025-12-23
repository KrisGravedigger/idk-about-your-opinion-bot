"""
Opinion Farming Bot - Market Scanner Module
===========================================

Handles market discovery, scoring, and ranking logic.
This is the core intelligence for finding the best liquidity opportunities.

Scoring formula:
    score = spread_percentage × bonus_multiplier
    
Where:
    - spread_percentage = (ask - bid) / bid × 100
    - bonus_multiplier = 2.0 for bonus markets, 1.0 otherwise

Higher score = more attractive market (wider spread, potential bonus points)
"""

from typing import Optional, Union
from dataclasses import dataclass

from config import (
    BONUS_MARKETS_FILE,
    BONUS_MULTIPLIER,
    MIN_ORDERBOOK_ORDERS,
    MIN_HOURS_UNTIL_CLOSE,
    MAX_HOURS_UNTIL_CLOSE,
    ORDERBOOK_BALANCE_RANGE,
    get_scoring_profile,
    DEFAULT_SCORING_PROFILE
)
from logger_config import setup_logger, log_section_header
from utils import (
    safe_float,
    format_price,
    format_percent,
    load_bonus_markets,
    calculate_spread
)
from api_client import OpinionClient
from scoring import calculate_market_score

# Initialize logger
logger = setup_logger(__name__)

# Initialize logger
logger = setup_logger(__name__)


def calculate_orderbook_balance(bids: list, asks: list) -> Optional[float]:
    """
    Calculate market position based on best bid/ask prices (midpoint).
    
    This measures how close the market is to resolution (0% or 100%).
    For prediction markets with prices 0-100¢:
    - 50% = balanced (spread around 50¢)
    - 20% = market thinks outcome unlikely (low prices)
    - 80% = market thinks outcome likely (high prices)
    
    Args:
        bids: List of bid orders with 'price' field
        asks: List of ask orders with 'price' field
    
    Returns:
        Float 0-100 representing market position (midpoint %), or None if invalid
    
    Example:
        Best bid=89¢, best ask=89.1¢ → midpoint=89.05% (UNBALANCED - too high)
        Best bid=45¢, best ask=55¢ → midpoint=50% (BALANCED)
        Best bid=10¢, best ask=15¢ → midpoint=12.5% (UNBALANCED - too low)
    """
    # EMERGENCY DEBUG
    logger.info("🚨 calculate_orderbook_balance() CALLED!")
    logger.info(f"   Bids: {len(bids)} orders")
    logger.info(f"   Asks: {len(asks)} orders")
    if len(bids) > 0:
        logger.info(f"   First bid: {bids[0]}")
    if len(asks) > 0:
        logger.info(f"   First ask: {asks[0]}")
    
    try:
        # Extract best prices
        bid_prices = []
        for bid in bids:
            try:
                price_str = bid.get('price', '0')
                bid_prices.append(float(price_str))
            except (ValueError, TypeError) as e:
                logger.warning(f"   ⚠️  Could not parse bid price '{price_str}': {e}")
                continue
        
        ask_prices = []
        for ask in asks:
            try:
                price_str = ask.get('price', '0')
                ask_prices.append(float(price_str))
            except (ValueError, TypeError) as e:
                logger.warning(f"   ⚠️  Could not parse ask price '{price_str}': {e}")
                continue
        
        if not bid_prices or not ask_prices:
            logger.info("   ❌ No valid bid/ask prices found")
            return None
        
        # Best bid = highest bid price
        # Best ask = lowest ask price
        best_bid = max(bid_prices)
        best_ask = min(ask_prices)
        
        logger.info(f"   💰 Best bid: ${best_bid:.4f}")
        logger.info(f"   💰 Best ask: ${best_ask:.4f}")
        
        # Validate prices
        if best_bid <= 0 or best_ask <= 0:
            logger.info(f"   ❌ Invalid prices (must be > 0)")
            return None
        
        if best_bid >= best_ask:
            logger.info(f"   ❌ Crossed book (bid >= ask)")
            return None
        
        # Calculate midpoint as percentage
        # For prices in range 0-1.00, midpoint × 100 gives position in %
        midpoint = (best_bid + best_ask) / 2.0
        position_percentage = midpoint * 100.0
        
        logger.info(f"   ✅ Market position (midpoint): {position_percentage:.1f}%")
        return position_percentage
    
    except Exception as e:
        logger.error(f"   ❌ Exception in calculate_orderbook_balance: {e}")
        import traceback
        traceback.print_exc()
        return None


@dataclass
class MarketScore:
    """
    Data class holding market analysis results.
    
    Attributes:
        market_id: Unique market identifier
        title: Market title/question
        yes_token_id: Token ID for YES outcome
        best_bid: Best bid price
        best_ask: Best ask price
        spread_abs: Absolute spread (ask - bid)
        spread_pct: Spread as percentage
        is_bonus: Whether this is a bonus market
        score: Final score (spread × multiplier)
    """
    market_id: int
    title: str
    yes_token_id: str
    best_bid: float
    best_ask: float
    spread_abs: float
    spread_pct: float
    is_bonus: bool
    score: float
    
    def __repr__(self):
        bonus_indicator = " 🌟" if self.is_bonus else ""
        return f"Market #{self.market_id}: {self.title[:30]}...{bonus_indicator} (Score: {self.score:.2f})"


class MarketScanner:
    """
    Scans and ranks Opinion.trade markets for liquidity opportunities.
    
    Usage:
        scanner = MarketScanner(client)
        top_markets = scanner.scan_and_rank(limit=10)
        best_market = top_markets[0]
    """
    
    def __init__(self, client: OpinionClient):
        """
        Initialize the scanner with an Opinion client.
        
        Args:
            client: Configured OpinionClient instance
        """
        self.client = client
        self.bonus_markets = set()
        
    def load_bonus_markets(self, filepath: str = BONUS_MARKETS_FILE) -> set[int]:
        """
        Load bonus market IDs from configuration file.
        
        Args:
            filepath: Path to bonus markets file
            
        Returns:
            Set of bonus market IDs
        """
        self.bonus_markets = load_bonus_markets(filepath)
        logger.info(f"Loaded {len(self.bonus_markets)} bonus markets from {filepath}")
        return self.bonus_markets
    
    def analyze_market(self, market: dict, scoring_profile: dict) -> Optional[MarketScore]:
        """
        Analyze a single market and calculate its score.
        
        Args:
            market: Market data dictionary from API
            scoring_profile: Scoring profile dict with weights and settings
            
        Returns:
            MarketScore object or None if market doesn't qualify
        """
        market_id = market.get('market_id')
        title = market.get('market_title', 'Unknown')
        yes_token_id = market.get('yes_token_id')
        # TEMPORARY DEBUG for market #2178
        if market_id == 2178:
            logger.info(f"🎯 ANALYZING MARKET #2178 - Blackpink")
            logger.info(f"   Title: {title}")
        
        # ========================================================================
        # DEBUG: Market entry logging
        # ========================================================================
        logger.debug("")
        logger.debug("="*70)
        logger.debug(f"🔍 ANALYZING Market #{market_id}")
        logger.debug(f"   Title: {title[:60]}")
        logger.debug("="*70)
               
        if not yes_token_id:
            logger.debug(f"❌ REJECTED: No yes_token_id field")
            logger.debug("")
            return None
        
        # Fetch orderbook
        logger.debug(f"📡 Fetching orderbook for token: {yes_token_id[:20]}...")
        orderbook = self.client.get_market_orderbook(yes_token_id)
        
        if not orderbook:
            logger.debug(f"❌ REJECTED: No orderbook data from API")
            logger.debug(f"   Token ID: {yes_token_id}")
            logger.debug("")
            return None
        
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        # ========================================================================
        # DEBUG: Orderbook structure logging
        # ========================================================================
        logger.debug(f"📊 Orderbook received:")
        logger.debug(f"   Bids: {len(bids)} orders")
        logger.debug(f"   Asks: {len(asks)} orders")
        
        # Check minimum orders requirement
        if len(bids) < MIN_ORDERBOOK_ORDERS:
            logger.debug(f"❌ REJECTED: Insufficient bids")
            logger.debug(f"   Found: {len(bids)} bids")
            logger.debug(f"   Need: {MIN_ORDERBOOK_ORDERS} minimum")
            logger.debug("")
            return None
        
        if len(asks) < MIN_ORDERBOOK_ORDERS:
            logger.debug(f"Market {market_id} has insufficient asks ({len(asks)}), skipping")
            return None
        
        # ========================================================================
        # NEW FILTERS: Time-based and orderbook balance
        # ========================================================================
        
        # Filter 1: Check market end time (if enabled)
        if MIN_HOURS_UNTIL_CLOSE is not None or MAX_HOURS_UNTIL_CLOSE is not None:
            # Extract end time from market data
            # Opinion.trade API uses 'end_at' (Unix timestamp in seconds)
            end_at = market.get('end_at')  # Unix timestamp in seconds
            
            logger.debug(f"⏰ Time filter check:")
            logger.debug(f"   end_at field: {end_at}")
            
            if end_at:
                try:
                    from datetime import datetime, timezone
                    
                    # Parse end_at as Unix timestamp (in seconds)
                    end_time = datetime.fromtimestamp(end_at, tz=timezone.utc)
                    logger.debug(f"   Parsed end time: {end_time}")
                    
                    now = datetime.now(timezone.utc)
                    hours_until_close = (end_time - now).total_seconds() / 3600
                    
                    # Check minimum hours
                    if MIN_HOURS_UNTIL_CLOSE is not None and hours_until_close < MIN_HOURS_UNTIL_CLOSE:
                        logger.debug(
                            f"Market {market_id} closes too soon "
                            f"({hours_until_close:.1f}h < {MIN_HOURS_UNTIL_CLOSE}h), skipping"
                        )
                        return None
                    
                    # Check maximum hours
                    if MAX_HOURS_UNTIL_CLOSE is not None and hours_until_close > MAX_HOURS_UNTIL_CLOSE:
                        logger.debug(
                            f"Market {market_id} closes too late "
                            f"({hours_until_close:.1f}h > {MAX_HOURS_UNTIL_CLOSE}h), skipping"
                        )
                        return None
                
                except Exception as e:
                    logger.debug(f"❌ REJECTED: Market {market_id}: Could not parse end_at timestamp: {e}")
                    logger.debug("")
                    # If we can't parse end_at and filters are enabled, skip for safety
                    return None
            else:
                # No end_at field in market data
                logger.debug(f"⚠️  Market {market_id}: No end_at field (skipping time filter)")
        
        # Filter 2: Check orderbook balance (if enabled)
        logger.debug(f"⚖️  Balance filter check:")
        logger.debug(f"   Config: ORDERBOOK_BALANCE_RANGE = {ORDERBOOK_BALANCE_RANGE}")
        
        if ORDERBOOK_BALANCE_RANGE is not None:
            # Show sample data for debugging
            if len(bids) > 0:
                logger.debug(f"   First bid: {bids[0]}")
            if len(asks) > 0:
                logger.debug(f"   First ask: {asks[0]}")
            
            bid_percentage = calculate_orderbook_balance(bids, asks)
            logger.debug(f"   Calculated balance: {bid_percentage:.1f}% bids" if bid_percentage else "   Could not calculate balance")
            
            if bid_percentage is not None:
                min_bid_pct, max_bid_pct = ORDERBOOK_BALANCE_RANGE
                logger.debug(f"   Acceptable range: {min_bid_pct}-{max_bid_pct}%")
                
                if bid_percentage < min_bid_pct or bid_percentage > max_bid_pct:
                    logger.info(
                        f"❌ REJECTED: Orderbook unbalanced "
                        f"({bid_percentage:.1f}% bids, range: {min_bid_pct}-{max_bid_pct}%)"
                    )
                    logger.info("")
                    return None
                
                logger.info(f"✅ Balance OK ({bid_percentage:.1f}% bids within {min_bid_pct}-{max_bid_pct}%)")
            else:
                # Could not calculate balance → skip for safety
                logger.info(f"❌ REJECTED: Could not calculate orderbook balance")
                logger.info("")
                return None
        else:
            logger.debug(f"   Balance filter DISABLED (ORDERBOOK_BALANCE_RANGE = None)")
        
        # Extract best prices
        # API may not return sorted orderbook, so find actual best prices
        # Best bid = highest bid price
        # Best ask = lowest ask price
        bid_prices = [safe_float(bid.get('price', 0)) for bid in bids]
        ask_prices = [safe_float(ask.get('price', 0)) for ask in asks]
        
        best_bid = max(bid_prices) if bid_prices else 0
        best_ask = min(ask_prices) if ask_prices else 0
        
        # ========================================================================
        # DEBUG: Price logging
        # ========================================================================
        logger.debug(f"💰 Extracted prices:")
        logger.debug(f"   Best bid: ${best_bid:.4f}")
        logger.debug(f"   Best ask: ${best_ask:.4f}")
        
        # Validate prices
        if best_bid <= 0 or best_ask <= 0:
            logger.debug(f"❌ REJECTED: Invalid prices")
            logger.debug(f"   Best bid: ${best_bid:.4f} (must be > 0)")
            logger.debug(f"   Best ask: ${best_ask:.4f} (must be > 0)")
            logger.debug("")
            return None
        
        if best_bid >= best_ask:
            logger.debug(f"❌ REJECTED: Crossed book (bid >= ask)")
            logger.debug(f"   Best bid: ${best_bid:.4f}")
            logger.debug(f"   Best ask: ${best_ask:.4f}")
            logger.debug(f"   Problem: Bid should be < Ask")
            logger.debug("")
            return None
        
        # Calculate spread
        spread_abs, spread_pct = calculate_spread(best_bid, best_ask)
        
        # ========================================================================
        # DEBUG: Spread logging
        # ========================================================================
        logger.debug(f"📏 Spread calculated:")
        logger.debug(f"   Absolute: ${spread_abs:.4f}")
        logger.debug(f"   Percentage: {spread_pct:.2f}%")
        
        # Determine if bonus market
        is_bonus = market_id in self.bonus_markets
        
        # Get full orderbook if needed for advanced metrics
        full_orderbook = None
        needs_orderbook = any(
            metric in scoring_profile.get('weights', {})
            for metric in ['hourglass_advanced', 'hourglass_simple', 'liquidity_depth']
        )
        if needs_orderbook:
            full_orderbook = {
                'bids': bids,
                'asks': asks
            }
        
        # Create market object for scoring
        market_obj = type('Market', (), {
            'best_bid': best_bid,
            'best_ask': best_ask,
            'spread_pct': spread_pct,
            'volume_24h': market.get('volume24h', 0),  # From API if available
            'is_bonus': is_bonus,
        })()
        
        # ========================================================================
        # DEBUG: Success - about to score
        # ========================================================================
        logger.debug("✅ PASSED all filters! Calculating score...")
        logger.debug(f"   Bonus market: {'Yes 🌟' if is_bonus else 'No'}")
        logger.debug(f"   24h volume: ${market.get('volume24h', 0):.2f}")
        
        # Calculate score using new scoring system
        score = calculate_market_score(
            market=market_obj,
            orderbook=full_orderbook,
            weights=scoring_profile.get('weights', {}),
            bonus_multiplier=scoring_profile.get('bonus_multiplier', 1.0),
            invert_spread=scoring_profile.get('invert_spread', False)
        )
        
        # ========================================================================
        # DEBUG: Final score
        # ========================================================================
        logger.debug(f"🎯 Final score: {score:.4f}")
        logger.debug("")
        
        return MarketScore(
            market_id=market_id,
            title=title,
            yes_token_id=yes_token_id,
            best_bid=best_bid,
            best_ask=best_ask,
            spread_abs=spread_abs,
            spread_pct=spread_pct,
            is_bonus=is_bonus,
            score=score
        )
         
    def scan_and_rank(self, limit: int = 10, scoring_profile: Optional[Union[str, dict]] = None) -> list[MarketScore]:
        """
        Scan all active markets and return top ranked ones.
        
        Args:
            limit: Maximum number of markets to return
            scoring_profile: Either:
                - String: name of profile from config (e.g., 'production_farming')
                - Dict: custom profile with weights
                - None: use DEFAULT_SCORING_PROFILE from config
            
        Returns:
            List of MarketScore objects, sorted by score (descending)
            
        Examples:
            # Use default profile
            markets = scanner.scan_and_rank(limit=10)
            
            # Use named profile
            markets = scanner.scan_and_rank(limit=10, scoring_profile='test_quick_fill')
            
            # Use custom profile
            custom = {'weights': {'spread': 1.0}, 'bonus_multiplier': 1.5}
            markets = scanner.scan_and_rank(limit=10, scoring_profile=custom)
            
        Raises:
            ValueError: If scoring_profile is not None, str, or dict
        """
        log_section_header(logger, "MARKET SCANNER")
        
        # Load scoring profile
        if scoring_profile is None:
            profile = get_scoring_profile(DEFAULT_SCORING_PROFILE)
            logger.info(f"📊 Using default scoring profile: {DEFAULT_SCORING_PROFILE}")
        elif isinstance(scoring_profile, str):
            profile = get_scoring_profile(scoring_profile)
            logger.info(f"📊 Using scoring profile: {scoring_profile}")
        elif isinstance(scoring_profile, dict):
            profile = scoring_profile
            logger.info(f"📊 Using custom scoring profile")
        else:
            raise ValueError("scoring_profile must be string, dict, or None")
        
        logger.debug(f"   Profile: {profile.get('description', 'Custom')}")
        logger.debug(f"   Weights: {profile.get('weights', {})}")
        
        # Validate profile structure
        assert profile is not None, "Profile loading failed"
        assert isinstance(profile, dict), f"Profile must be dict, got {type(profile)}"
        assert 'weights' in profile, "Profile must contain 'weights' key"
        
        # Load bonus markets if not already loaded
        if not self.bonus_markets:
            self.load_bonus_markets()
        
        # Fetch all active markets
        logger.info("📊 Fetching active markets...")
        markets = self.client.get_all_active_markets()
        
        if not markets:
            logger.warning("No active markets found!")
            return []
        
        logger.info(f"   Found {len(markets)} active markets")
        
        # Analyze each market
        logger.info("🔍 Analyzing orderbooks...")
        scored_markets = []
        analyzed_count = 0
        
        for i, market in enumerate(markets):
            # Progress indicator (every 10 markets)
            if (i + 1) % 10 == 0:
                logger.debug(f"   Progress: {i + 1}/{len(markets)}")
            
            score = self.analyze_market(market, profile)
            if score:
                scored_markets.append(score)
                analyzed_count += 1
        
        logger.info(f"   Analyzed {analyzed_count} markets with valid orderbooks")
        
        # Sort by score (descending)
        scored_markets.sort(key=lambda x: x.score, reverse=True)
        
        # Return top N
        top_markets = scored_markets[:limit]
        
        logger.info(f"✅ Top {len(top_markets)} markets identified")
        
        return top_markets
    
    def display_top_markets(self, markets: list[MarketScore]):
        """
        Display top markets in a formatted table.
        
        Args:
            markets: List of MarketScore objects to display
        """
        if not markets:
            logger.info("No markets to display")
            return
        
        # Print header
        print()
        print("┌──────┬────────────────────────────────────┬────────┬──────────┬──────────┬────────┐")
        print("│ Rank │ Market ID & Title                  │ Spread │ Best Bid │ Best Ask │ Score  │")
        print("├──────┼────────────────────────────────────┼────────┼──────────┼──────────┼────────┤")
        
        for i, m in enumerate(markets, 1):
            # Truncate title if too long
            title = m.title[:22] + "..." if len(m.title) > 25 else m.title
            bonus = " 🌟" if m.is_bonus else "   "
            market_str = f"{m.market_id}: {title}{bonus}"
            
            print(f"│ {i:4} │ {market_str:<34} │ {m.spread_pct:5.1f}% │ {format_price(m.best_bid):>8} │ {format_price(m.best_ask):>8} │ {m.score:6.2f} │")
        
        print("└──────┴────────────────────────────────────┴────────┴──────────┴──────────┴────────┘")
        print()
        print("🌟 = Bonus market (2x multiplier)")
        print()
    
    def get_best_market(self) -> Optional[MarketScore]:
        """
        Get the single best market for trading.
        
        Returns:
            Best MarketScore or None if no markets available
        """
        top = self.scan_and_rank(limit=1)
        return top[0] if top else None
    
    def get_fresh_orderbook(self, market_id: int, token_id: str) -> Optional[dict]:
        """
        Get fresh orderbook data for a specific market.
        Use this when you need current prices before placing orders.
        
        Args:
            market_id: Market ID (for logging)
            token_id: Token ID to fetch orderbook for
            
        Returns:
            Dict with 'best_bid', 'best_ask', 'spread_abs', 'spread_pct' or None
        """
        orderbook = self.client.get_market_orderbook(token_id)
        
        if not orderbook:
            return None
        
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        if not bids or not asks:
            return None
        
        # Extract all prices and find actual best prices
        # API does NOT return sorted data, so we must find min/max ourselves
        bid_prices = [safe_float(bid.get('price', 0)) for bid in bids]
        ask_prices = [safe_float(ask.get('price', 0)) for ask in asks]
        
        best_bid = max(bid_prices) if bid_prices else 0  # Highest bid
        best_ask = min(ask_prices) if ask_prices else 0  # Lowest ask
        
        if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
            return None
        
        spread_abs, spread_pct = calculate_spread(best_bid, best_ask)
        
        return {
            'best_bid': best_bid,
            'best_ask': best_ask,
            'spread_abs': spread_abs,
            'spread_pct': spread_pct,
            'bids': bids,
            'asks': asks
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def scan_markets(client: OpinionClient, limit: int = 10, scoring_profile=None) -> list[MarketScore]:
    """
    Convenience function to scan and rank markets.
    
    Args:
        client: OpinionClient instance
        limit: Number of markets to return
        scoring_profile: Scoring profile (string name, dict, or None)
        
    Returns:
        List of top MarketScore objects
    """
    scanner = MarketScanner(client)
    return scanner.scan_and_rank(limit=limit, scoring_profile=scoring_profile)


def find_best_market(client: OpinionClient) -> Optional[MarketScore]:
    """
    Convenience function to find the single best market.
    
    Args:
        client: OpinionClient instance
        
    Returns:
        Best MarketScore or None
    """
    scanner = MarketScanner(client)
    return scanner.get_best_market()


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    from api_client import create_client
    
    print("=== Market Scanner Module Test ===")
    print("Note: This requires valid credentials in .env file")
    print()
    
    try:
        # Create client
        client = create_client()
        print("✅ Client created")
        
        # Create scanner
        scanner = MarketScanner(client)
        print("✅ Scanner created")
        
        # Scan markets
        print("\nScanning markets...")
        top_markets = scanner.scan_and_rank(limit=10)
        
        # Display results
        scanner.display_top_markets(top_markets)
        
        if top_markets:
            best = top_markets[0]
            print(f"\n💡 Recommendation: Market #{best.market_id}")
            print(f"   Title: {best.title}")
            print(f"   Score: {best.score:.2f}")
            print(f"   Spread: {format_percent(best.spread_pct)}")
            print(f"   Bonus: {'Yes 🌟' if best.is_bonus else 'No'}")
        
        print("\n✅ Market scanner test complete!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
