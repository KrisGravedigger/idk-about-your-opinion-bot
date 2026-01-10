#!/usr/bin/env python3
"""
Market Analyzer - Liquidity Farming Strategy Scout
==================================================

Scans Opinion.trade markets for optimal liquidity farming opportunities.

Liquidity Farming Strategy:
    1. PROBABILITY EDGE (main): Target 66-85% biased markets where you have statistical advantage
    2. MARKET MAKING (secondary): Provide liquidity and earn from volume over time
    3. SPREAD (bonus): Nice to have, but NOT the primary goal (even 1% is OK!)

Usage:
    # 🚀 FAST MODE (recommended) - Use top markets by volume24h
    python market_analyzer.py --top-volume 40        # 3.5× faster! (~10 min)
    python market_analyzer.py --top-volume 20        # Quick test (~5 min)

    # SLOW MODE (comprehensive) - Scan all markets from SDK
    python market_analyzer.py                        # Default: scan all 140+ markets (~40 min)
    python market_analyzer.py --limit 50             # Test: scan only first 50 markets (~12 min)

    # Custom filters
    python market_analyzer.py --top-volume 40 --min-prob 0.60
    python market_analyzer.py --top-volume 40 --top 50

Scoring (how opportunities are ranked):
    - Bias score: 50% weight (MAIN edge - orderbook imbalance 60-85% sweet spot)
    - Volume: 35% weight (liquidity for market making)
    - Spread: 15% weight (bonus only - NOT a requirement!)

Important:
    - Spread is NOT a hard filter anymore (defaults to 0%)
    - Focus is on PROBABILITY EDGE (66-85% biased markets)
    - Even 1-2% spread is profitable with probability edge + market making

Performance Options:

    🚀 --top-volume N (RECOMMENDED):
        Fetches top N markets sorted by volume24h from raw API.
        Then fetches orderbooks only for those N markets.

        Example: --top-volume 40
        - Fetches: 40 markets + 80 orderbooks = 81 API calls
        - Time: ~10 minutes (vs 40 minutes for all markets)
        - Result: 3.5× faster with BEST opportunities!

    --limit N (slower, unsorted):
        Fetches ALL 140 markets from SDK, then limits to first N.
        Still fetches orderbooks for N markets, but NOT sorted by volume.

        Example: --limit 50
        - Fetches: 140 markets + 100 orderbooks = 241 calls
        - Time: ~12 minutes (slower than --top-volume 50)

Hybrid Optimization (--refine-top-n) [DEPRECATED]:
    NOTE: --top-volume is better! It gets volume24h upfront, no refinement needed.

    --refine-top-n is only useful for SLOW mode (no --top-volume):
        - Rank by lifetime volume → fetch volume24h for top N → re-rank
        - Example: --refine-top-n 20 (adds 20 API calls)
        - Better: Use --top-volume instead!

Output:
    - Console table with top N opportunities
    - CSV export with all filtered results
    - Summary statistics with rejection reasons
"""

import argparse
import csv
import math
import os
import requests
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, replace

# Local imports
from api_client import OpinionClient, create_client
from config import SPREAD_FARMING_CONFIG, API_KEY
from scoring import calculate_bid_volume_percentage, calculate_bias_score
from utils import calculate_spread, format_price, format_percent
from logger_config import setup_logger

# Initialize logger
logger = setup_logger(__name__)

# Disable SSL warnings for raw API calls (Opinion.trade uses self-signed cert)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# =============================================================================
# RAW API HELPERS - For accessing volume24h field not available in SDK
# =============================================================================

def fetch_top_markets_by_volume24h(limit: int = 50) -> List[Dict]:
    """
    Fetch top N markets sorted by volume24h using raw API with pagination.

    PERFORMANCE OPTIMIZATION:
    Instead of fetching ALL 140 markets and filtering later, this directly
    fetches the top N most active markets by 24h volume. This dramatically
    reduces the number of orderbook fetches needed.

    Example:
        - OLD: Fetch 140 markets, get orderbooks for 280 outcomes, filter → 40 min
        - NEW: Fetch top 40, get orderbooks for 80 outcomes, filter → 10 min
        Result: 3.5× faster!

    Args:
        limit: Number of top markets to fetch (default: 50)

    Returns:
        List of market dicts with volume24h field included
    """
    try:
        url = "https://proxy.opinion.trade:8443/openapi/market"
        headers = {"apikey": API_KEY}

        logger.info(f"🚀 FAST MODE: Fetching top {limit} markets by volume24h from raw API...")

        all_markets = []
        page = 1
        per_page = 10  # API max limit seems to be ~10 per page

        while len(all_markets) < limit:
            params = {
                "status": "activated",
                "sortBy": 5,  # Sort by volume24h
                "order": "desc",
                "limit": per_page,
                "page": page
            }

            logger.debug(f"   Fetching page {page} (requesting {per_page} markets)...")

            response = requests.get(url, headers=headers, params=params, verify=False, timeout=30)
            data = response.json()

            if data.get("errno") != 0 or not data.get("result"):
                logger.error(f"❌ Raw API error on page {page}: {data.get('errmsg')}")
                break

            markets = data["result"].get("list", [])
            total_available = data["result"].get("total", 0)

            # If no markets returned, we've reached the end
            if not markets:
                logger.debug(f"   No more markets on page {page}")
                break

            logger.debug(f"   Page {page}: got {len(markets)} markets")

            # Add markets to our collection
            all_markets.extend(markets)

            # Stop if we've fetched all available markets
            if len(all_markets) >= total_available:
                logger.debug(f"   Reached total available markets ({total_available})")
                break

            # Continue to next page
            page += 1

            # Safety: max 20 pages to prevent infinite loop
            if page > 20:
                logger.warning(f"⚠️  Reached max page limit (20), stopping at {len(all_markets)} markets")
                break

        # Trim to exact limit
        all_markets = all_markets[:limit]

        # Convert raw API format to SDK-compatible format
        sdk_format_markets = []
        for m in all_markets:
            sdk_market = {
                'market_id': m.get('marketId'),
                'market_title': m.get('marketTitle'),
                'yes_token_id': m.get('yesTokenId'),
                'no_token_id': m.get('noTokenId'),
                'cutoff_at': m.get('cutoffAt'),
                'volume': m.get('volume'),  # Lifetime
                'volume24h': m.get('volume24h'),  # 24h - this is why we use raw API!
                'volume7d': m.get('volume7d'),  # Bonus: 7d volume
                'status': m.get('status'),
                'quote_token': m.get('quoteToken'),
                'chain_id': m.get('chainId'),
            }
            sdk_format_markets.append(sdk_market)

        logger.info(f"✅ Fetched {len(sdk_format_markets)} top markets (sorted by volume24h) across {page} page(s)")
        return sdk_format_markets

    except Exception as e:
        logger.error(f"❌ Failed to fetch top markets: {e}")
        return []


def fetch_market_volume24h(market_id: int) -> Optional[float]:
    """
    Fetch precise 24h volume for a specific market using raw API.

    The SDK doesn't return volume24h, but the raw OpenAPI endpoint does.
    This function makes a direct HTTP call to get the accurate 24h volume.

    Args:
        market_id: Market ID to fetch

    Returns:
        24h volume in USDT, or None if fetch failed
    """
    try:
        url = "https://proxy.opinion.trade:8443/openapi/market"
        headers = {"apikey": API_KEY}
        params = {
            "status": "activated",
            "marketId": market_id,
            "limit": 1
        }

        response = requests.get(url, headers=headers, params=params, verify=False, timeout=10)
        data = response.json()

        if data.get("errno") == 0 and data.get("result"):
            markets = data["result"].get("list", [])
            if markets:
                volume24h_str = markets[0].get("volume24h", "0")
                return float(volume24h_str)

        return None

    except Exception as e:
        logger.warning(f"Failed to fetch volume24h for market {market_id}: {e}")
        return None


def refine_opportunities_with_volume24h(
    opportunities: List['OutcomeOpportunity'],
    top_n: int = 20
) -> List['OutcomeOpportunity']:
    """
    Refine top N opportunities by fetching precise 24h volume and recalculating scores.

    Hybrid Optimization Strategy:
    1. Initial ranking uses lifetime volume from SDK (fast, 1 API call for all markets)
    2. For top N results, fetch precise volume24h from raw API (N additional calls)
    3. Recalculate scores with accurate 24h volume
    4. Re-rank the top N opportunities

    This approach is 85% faster than fetching volume24h for all 140+ markets upfront.

    Args:
        opportunities: List of opportunities sorted by score (lifetime volume)
        top_n: Number of top opportunities to refine (default: 20)

    Returns:
        Updated list with top N re-ranked by volume24h, rest unchanged
    """
    if not opportunities or top_n <= 0:
        return opportunities

    logger.info(f"🔄 Refining top {top_n} opportunities with precise volume24h...")

    # Split into top N and rest
    top_opportunities = opportunities[:top_n]
    rest_opportunities = opportunities[top_n:]

    # Fetch volume24h for each top opportunity and recalculate score
    refined = []
    volume24h_cache = {}  # Cache: {market_id: volume24h} (avoid duplicate fetches for YES/NO)

    for opp in top_opportunities:
        # Fetch volume24h if not already fetched for this market
        if opp.market_id not in volume24h_cache:
            volume24h = fetch_market_volume24h(opp.market_id)
            volume24h_cache[opp.market_id] = volume24h
        else:
            volume24h = volume24h_cache[opp.market_id]  # Use cached value

        if volume24h is not None:
            # Recalculate score with accurate 24h volume
            # Scoring weights: bias_score 50%, volume 35%, spread 15%
            bias_score = calculate_bias_score(opp.bid_volume_pct)
            volume_score = min(math.log10(max(volume24h, 1)) / 5.0, 1.0)
            spread_score = min(opp.spread_pct / 20.0, 1.0)

            new_score = (bias_score * 0.50) + (volume_score * 0.35) + (spread_score * 0.15)
            new_score *= 100  # Scale to 0-100

            # Create updated opportunity with new volume and score
            updated_opp = replace(opp, volume_24h=volume24h, score=new_score)
            refined.append(updated_opp)

            # Log changes
            volume_change_pct = ((volume24h - opp.volume_24h) / opp.volume_24h * 100) if opp.volume_24h > 0 else 0
            logger.debug(
                f"  Market {opp.market_id}: "
                f"volume ${opp.volume_24h:,.0f} → ${volume24h:,.0f} ({volume_change_pct:+.1f}%), "
                f"score {opp.score:.1f} → {new_score:.1f}"
            )
        else:
            # Keep original if fetch failed
            refined.append(opp)

    # Re-rank the refined top N by new scores
    refined.sort(key=lambda x: x.score, reverse=True)

    logger.info(f"✅ Refined {len(refined)} opportunities with precise volume24h")

    # Return refined top N + unchanged rest
    return refined + rest_opportunities


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class OutcomeOpportunity:
    """Data class for a single outcome opportunity."""
    market_id: int
    title: str
    outcome: str  # "YES" or "NO"
    best_bid: float
    best_ask: float
    spread_usd: float
    spread_pct: float
    probability: float
    bid_volume_pct: float
    volume_24h: float  # Actually lifetime volume (API doesn't provide 24h)
    orders_bid: int
    orders_ask: int
    hours_to_close: Optional[float]
    score: float


class MarketAnalyzer:
    """Analyzes markets for spread farming opportunities."""

    def __init__(self, client: OpinionClient):
        """
        Initialize analyzer.

        Args:
            client: OpinionClient instance
        """
        self.client = client

    def calculate_hours_until_close(self, cutoff_at: Optional[int]) -> Optional[float]:
        """
        Calculate hours until market closes.

        Args:
            cutoff_at: Unix timestamp of market close

        Returns:
            Hours until close, or None if no cutoff
        """
        if not cutoff_at:
            return None

        try:
            from datetime import datetime, timezone
            end_time = datetime.fromtimestamp(cutoff_at, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            hours = (end_time - now).total_seconds() / 3600
            return max(0.0, hours)  # Don't return negative
        except Exception:
            return None

    def analyze_outcome(
        self,
        market: dict,
        outcome: str,
        token_id: str,
        orderbook: dict
    ) -> Optional[OutcomeOpportunity]:
        """
        Analyze a single outcome (YES or NO).

        Args:
            market: Market data dict
            outcome: "YES" or "NO"
            token_id: Token ID for this outcome
            orderbook: Orderbook data

        Returns:
            OutcomeOpportunity or None if doesn't qualify
        """
        if not orderbook:
            return None

        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])

        if not bids or not asks:
            return None

        # Extract best prices
        try:
            best_bid = float(bids[0].get('price', 0))
            best_ask = float(asks[0].get('price', 0))
        except (ValueError, TypeError, IndexError):
            return None

        if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
            return None

        # Calculate metrics
        spread_usd, spread_pct = calculate_spread(best_bid, best_ask)
        probability = (best_bid + best_ask) / 2  # Mid-price method
        bid_volume_pct = calculate_bid_volume_percentage(orderbook)

        if bid_volume_pct is None:
            bid_volume_pct = 50.0  # Default to balanced

        # Calculate score using liquidity farming weights
        # bias_score: 50% (MAIN edge), volume: 35%, spread: 15%

        # Volume: prefer volume24h if available (from raw API), fallback to lifetime volume
        volume_24h_str = market.get('volume24h')  # From raw API (--top-volume mode)
        if volume_24h_str:
            try:
                volume_24h = float(volume_24h_str)
            except (ValueError, TypeError):
                volume_24h = 0.0
        else:
            # Fallback: use lifetime volume from SDK
            volume_str = market.get('volume', '0')
            try:
                volume_24h = float(volume_str)
            except (ValueError, TypeError):
                volume_24h = 0.0

        # Calculate bias_score (60-85% sweet spot)
        from scoring import calculate_bias_score
        bias_score = calculate_bias_score(bid_volume_pct)

        # Normalize volume (log scale to handle wide range)
        import math
        volume_score = min(math.log10(max(volume_24h, 1)) / 5.0, 1.0)  # log scale, max at $100k

        # Spread score (normalized to 0-1, 20% = 1.0)
        spread_score = min(spread_pct / 20.0, 1.0)

        # Weighted combination (matches liquidity_farming profile)
        score = (bias_score * 0.50) + (volume_score * 0.35) + (spread_score * 0.15)
        score *= 100  # Scale to 0-100 for easier reading

        # Hours until close
        hours_to_close = self.calculate_hours_until_close(market.get('cutoff_at'))

        return OutcomeOpportunity(
            market_id=market.get('market_id'),
            title=market.get('market_title', 'Unknown'),
            outcome=outcome,
            best_bid=best_bid,
            best_ask=best_ask,
            spread_usd=spread_usd,
            spread_pct=spread_pct,
            probability=probability,
            bid_volume_pct=bid_volume_pct,
            volume_24h=volume_24h,
            orders_bid=len(bids),
            orders_ask=len(asks),
            hours_to_close=hours_to_close,
            score=score
        )

    def scan_markets(
        self,
        min_spread_pct: float = 0.0,
        min_prob: float = 0.66,
        max_prob: float = 0.85,
        limit: Optional[int] = None,
        top_volume: Optional[int] = None
    ) -> List[OutcomeOpportunity]:
        """
        Scan all markets and return filtered opportunities.

        Args:
            min_spread_pct: Minimum spread % (default: 0.0 - no filter!)
            min_prob: Minimum outcome probability (default: 0.66 - biased markets only)
            max_prob: Maximum outcome probability (default: 0.85 - sweet spot 66-85%)
            limit: Limit scan to first N markets from SDK (default: None - scan all)
            top_volume: FAST MODE - Fetch top N markets by volume24h from raw API (default: None)

        Returns:
            List of OutcomeOpportunity objects
        """
        logger.info("🔍 Scanning Opinion.trade markets for liquidity farming opportunities...")
        logger.info("")
        logger.info("📊 STRATEGY:")
        logger.info(f"   1. PROBABILITY EDGE (50% weight): Target {min_prob*100:.0f}-{max_prob*100:.0f}% biased markets")
        logger.info(f"   2. MARKET MAKING (35% weight): Orderbook imbalance 60-85% sweet spot")
        logger.info(f"   3. SPREAD BONUS (15% weight): Any spread is OK (min: {min_spread_pct}%)")
        logger.info("")
        logger.info("📊 FILTERS:")
        logger.info(f"   - Probability: {min_prob*100:.0f}-{max_prob*100:.0f}% (main filter)")
        logger.info(f"   - Min spread: {min_spread_pct}% (0% = no filter)")
        logger.info("")

        # Fetch markets (FAST MODE: top by volume24h, or SLOW MODE: all from SDK)
        if top_volume and top_volume > 0:
            # FAST MODE: Fetch top N markets sorted by volume24h from raw API
            markets = fetch_top_markets_by_volume24h(limit=top_volume)
            if not markets:
                logger.error("❌ Failed to fetch markets from raw API, falling back to SDK...")
                markets = self.client.get_all_active_markets()[:top_volume]
        else:
            # SLOW MODE: Fetch all markets from SDK (unsorted)
            markets = self.client.get_all_active_markets()

        if not markets:
            logger.warning("No active markets found!")
            return []

        # Apply limit if specified (only for SDK mode)
        total_available = len(markets)
        if limit and limit > 0 and not top_volume:
            markets = markets[:limit]
            logger.info(f"   Found {total_available} active markets (limiting scan to first {len(markets)})")
        else:
            if top_volume:
                logger.info(f"   Using top {len(markets)} markets by volume24h (sorted)")
            else:
                logger.info(f"   Found {len(markets)} active markets")

        logger.info("")

        opportunities = []
        total_outcomes = 0
        rejected_spread = 0
        rejected_probability = 0

        # Analyze each market with improved progress tracking
        from datetime import datetime
        start_time = datetime.now()

        for i, market in enumerate(markets):
            # Progress every 10 markets
            if (i + 1) % 10 == 0 or i == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                remaining = (len(markets) - i - 1) / rate if rate > 0 else 0
                logger.info(
                    f"   📊 Progress: {i + 1}/{len(markets)} markets "
                    f"({(i+1)/len(markets)*100:.0f}%) | "
                    f"⏱️  {elapsed:.0f}s elapsed, ~{remaining:.0f}s remaining"
                )

            market_id = market.get('market_id')
            yes_token_id = market.get('yes_token_id')
            no_token_id = market.get('no_token_id')

            if not yes_token_id or not no_token_id:
                continue

            # Fetch both orderbooks
            yes_orderbook = self.client.get_market_orderbook(yes_token_id)
            no_orderbook = self.client.get_market_orderbook(no_token_id)

            # Analyze YES outcome
            if yes_orderbook:
                total_outcomes += 1
                opp = self.analyze_outcome(market, "YES", yes_token_id, yes_orderbook)
                if opp:
                    # Apply filters with tracking
                    if opp.spread_pct < min_spread_pct:
                        rejected_spread += 1
                    elif not (min_prob <= opp.probability <= max_prob):
                        rejected_probability += 1
                    else:
                        opportunities.append(opp)

            # Analyze NO outcome
            if no_orderbook:
                total_outcomes += 1
                opp = self.analyze_outcome(market, "NO", no_token_id, no_orderbook)
                if opp:
                    # Apply filters with tracking
                    if opp.spread_pct < min_spread_pct:
                        rejected_spread += 1
                    elif not (min_prob <= opp.probability <= max_prob):
                        rejected_probability += 1
                    else:
                        opportunities.append(opp)

        logger.info("")
        logger.info(f"✅ Found {total_outcomes} total outcomes")
        logger.info(f"   ❌ Rejected (spread < {min_spread_pct}%): {rejected_spread}")
        logger.info(f"   ❌ Rejected (probability outside {min_prob*100:.0f}-{max_prob*100:.0f}%): {rejected_probability}")
        logger.info(f"🎯 After filters: {len(opportunities)} outcomes ({len(opportunities)/total_outcomes*100:.1f}%)")
        logger.info("")

        return opportunities

    def display_opportunities(self, opportunities: List[OutcomeOpportunity], limit: int = 20):
        """
        Display opportunities in a formatted table.

        Args:
            opportunities: List of opportunities
            limit: Maximum number to display
        """
        if not opportunities:
            print("No opportunities found.")
            return

        # Sort by score (descending)
        sorted_opps = sorted(opportunities, key=lambda x: x.score, reverse=True)
        top_opps = sorted_opps[:limit]

        print()
        print(f"📈 TOP {len(top_opps)} OPPORTUNITIES:")
        print()
        print("┌──────┬────────┬────────┬────────┬─────────┬────────┬──────────┬────────┐")
        print("│ Rank │ Mkt ID │ Outcme │ Spread │  Prob   │  Bias  │  Volume  │  Score │")
        print("├──────┼────────┼────────┼────────┼─────────┼────────┼──────────┼────────┤")

        for i, opp in enumerate(top_opps, 1):
            # Format volume with K/M suffix for readability
            vol = opp.volume_24h
            if vol >= 1_000_000:
                vol_str = f"${vol/1_000_000:.1f}M"
            elif vol >= 1_000:
                vol_str = f"${vol/1_000:.0f}K"
            else:
                vol_str = f"${vol:.0f}"

            print(f"│ {i:4} │ {opp.market_id:6} │ {opp.outcome:6} │ {opp.spread_pct:5.1f}% │ {opp.probability*100:6.1f}% │ {opp.bid_volume_pct:5.1f}% │ {vol_str:>8} │ {opp.score:6.1f} │")

        print("└──────┴────────┴────────┴────────┴─────────┴────────┴──────────┴────────┘")
        print()

        # Show first opportunity details
        if top_opps:
            best = top_opps[0]
            print(f"🏆 BEST OPPORTUNITY:")
            print(f"   Market: #{best.market_id}")
            print(f"   Title: {best.title}")
            print(f"   Outcome: {best.outcome}")
            print(f"   Spread: {best.spread_pct:.2f}% (${best.spread_usd:.4f})")
            print(f"   Probability: {best.probability*100:.1f}%")
            print(f"   Bias: {best.bid_volume_pct:.1f}% bid volume")
            print(f"   Volume (lifetime): ${best.volume_24h:,.0f}")
            if best.hours_to_close:
                print(f"   Closes in: {best.hours_to_close:.1f} hours")
            print()

    def export_to_csv(self, opportunities: List[OutcomeOpportunity], filename: Optional[str] = None):
        """
        Export opportunities to CSV file.

        Args:
            opportunities: List of opportunities
            filename: Output filename (default: auto-generated with timestamp)
        """
        if not opportunities:
            logger.info("No opportunities to export")
            return

        if not filename:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"market_analysis_{timestamp}.csv"

        # Sort by score
        sorted_opps = sorted(opportunities, key=lambda x: x.score, reverse=True)

        with open(filename, 'w', newline='') as csvfile:
            fieldnames = [
                'market_id', 'title', 'outcome',
                'best_bid', 'best_ask', 'spread_usd', 'spread_pct',
                'probability', 'bid_volume_pct',
                'volume_lifetime', 'orders_bid', 'orders_ask',
                'hours_to_close', 'score'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for opp in sorted_opps:
                writer.writerow({
                    'market_id': opp.market_id,
                    'title': opp.title,
                    'outcome': opp.outcome,
                    'best_bid': f"{opp.best_bid:.4f}",
                    'best_ask': f"{opp.best_ask:.4f}",
                    'spread_usd': f"{opp.spread_usd:.4f}",
                    'spread_pct': f"{opp.spread_pct:.2f}",
                    'probability': f"{opp.probability:.4f}",
                    'bid_volume_pct': f"{opp.bid_volume_pct:.2f}",
                    'volume_lifetime': f"{opp.volume_24h:.2f}",  # Note: field name is volume_24h but contains lifetime
                    'orders_bid': opp.orders_bid,
                    'orders_ask': opp.orders_ask,
                    'hours_to_close': f"{opp.hours_to_close:.1f}" if opp.hours_to_close else "",
                    'score': f"{opp.score:.2f}"
                })

        logger.info(f"📁 Results exported to: {filename}")
        logger.info("")

    def display_statistics(self, opportunities: List[OutcomeOpportunity], total_markets: int, total_outcomes: int):
        """
        Display summary statistics.

        Args:
            opportunities: List of filtered opportunities
            total_markets: Total number of markets scanned
            total_outcomes: Total number of outcomes generated
        """
        if not opportunities:
            return

        avg_spread = sum(o.spread_pct for o in opportunities) / len(opportunities)
        avg_volume = sum(o.volume_24h for o in opportunities) / len(opportunities)
        avg_bias = sum(o.bid_volume_pct for o in opportunities) / len(opportunities)

        print("📊 STATISTICS:")
        print(f"   Markets scanned: {total_markets}")
        print(f"   Outcomes generated: {total_outcomes}")
        print(f"   After filters: {len(opportunities)} ({len(opportunities)/total_outcomes*100:.1f}%)")
        print(f"   Average spread: {avg_spread:.1f}%")
        print(f"   Average volume (lifetime): ${avg_volume:,.0f}")
        print(f"   Average bias: {avg_bias:.1f}%")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Analyze markets for spread farming opportunities',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--min-spread',
        type=float,
        default=0.0,
        help='Minimum spread %% (default: 0.0 - no filter)'
    )

    parser.add_argument(
        '--min-prob',
        type=float,
        default=0.66,
        help='Minimum outcome probability (default: 0.66 - biased markets)'
    )

    parser.add_argument(
        '--max-prob',
        type=float,
        default=0.85,
        help='Maximum outcome probability (default: 0.85 - sweet spot 66-85%%)'
    )

    parser.add_argument(
        '--top-volume',
        type=int,
        default=None,
        metavar='N',
        help='🚀 FAST MODE: Fetch only top N markets by volume24h (3.5× faster!). '
             'Uses raw API sorted by volume24h, then fetches orderbooks only for top N. '
             'Example: --top-volume 40 → fetches 80 orderbooks instead of 280 (10 min vs 40 min). '
             'Recommended: 40-50 for production, 20 for testing.'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        metavar='N',
        help='SLOWER: Limit scan to first N markets from SDK (unsorted). '
             'Use --top-volume instead for better performance. '
             'Example: --limit 50 scans only first 50 markets (but not sorted by volume)'
    )

    parser.add_argument(
        '--top',
        type=int,
        default=20,
        help='Show top N results (default: 20)'
    )

    parser.add_argument(
        '--refine-top-n',
        type=int,
        default=None,
        metavar='N',
        help='HYBRID OPTIMIZATION: Refine top N results with precise volume24h from raw API. '
             'Fetches accurate 24h volume for top N opportunities and re-ranks them. '
             'Example: --refine-top-n 20 (85%% faster than fetching all markets)'
    )

    parser.add_argument(
        '--no-csv',
        action='store_true',
        help='Skip CSV export'
    )

    args = parser.parse_args()

    # Create client
    try:
        client = create_client()
    except Exception as e:
        print(f"❌ Failed to create client: {e}")
        print("   Check your .env file and API credentials")
        return 1

    # Create analyzer
    analyzer = MarketAnalyzer(client)

    # Scan markets
    try:
        opportunities = analyzer.scan_markets(
            min_spread_pct=args.min_spread,
            min_prob=args.min_prob,
            max_prob=args.max_prob,
            limit=args.limit,
            top_volume=args.top_volume
        )
    except Exception as e:
        logger.error(f"❌ Error scanning markets: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # HYBRID OPTIMIZATION: Refine top N with precise volume24h
    if args.refine_top_n and args.refine_top_n > 0:
        logger.info("")
        logger.info("=" * 80)
        logger.info("🚀 HYBRID OPTIMIZATION ENABLED")
        logger.info(f"   Initial ranking: lifetime volume (SDK - fast)")
        logger.info(f"   Refinement: top {args.refine_top_n} with precise volume24h (raw API)")
        logger.info("=" * 80)
        logger.info("")

        try:
            opportunities = refine_opportunities_with_volume24h(
                opportunities,
                top_n=args.refine_top_n
            )
        except Exception as e:
            logger.warning(f"⚠️ Volume24h refinement failed: {e}")
            logger.info("   Continuing with lifetime volume rankings...")

    # Get total counts for statistics
    markets = client.get_all_active_markets()
    total_markets = len(markets)
    total_outcomes = total_markets * 2  # Approximate (YES + NO)

    # Display results
    analyzer.display_opportunities(opportunities, limit=args.top)

    # Export CSV
    if not args.no_csv:
        analyzer.export_to_csv(opportunities)

    # Display statistics
    analyzer.display_statistics(opportunities, total_markets, total_outcomes)

    logger.info("✅ Analysis complete!")
    return 0


if __name__ == '__main__':
    import sys
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print()
        print("⛔ Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
