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
    python market_analyzer.py                    # Default: 66-85% probability
    python market_analyzer.py --min-prob 0.60    # Custom probability range
    python market_analyzer.py --no-csv           # Skip CSV export
    python market_analyzer.py --top 50           # Show top 50 results

Scoring (how opportunities are ranked):
    - Bias score: 50% weight (MAIN edge - orderbook imbalance 60-85% sweet spot)
    - Volume: 35% weight (liquidity for market making)
    - Spread: 15% weight (bonus only - NOT a requirement!)

Important:
    - Spread is NOT a hard filter anymore (defaults to 0%)
    - Focus is on PROBABILITY EDGE (66-85% biased markets)
    - Even 1-2% spread is profitable with probability edge + market making

Output:
    - Console table with top N opportunities
    - CSV export with all filtered results
    - Summary statistics with rejection reasons
"""

import argparse
import csv
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass

# Local imports
from api_client import OpinionClient, create_client
from config import SPREAD_FARMING_CONFIG
from scoring import calculate_bid_volume_percentage, calculate_bias_score
from utils import calculate_spread, format_price, format_percent
from logger_config import setup_logger

# Initialize logger
logger = setup_logger(__name__)


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
    volume_24h: float
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
        volume_24h = float(market.get('volume24h', 0))

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
        max_prob: float = 0.85
    ) -> List[OutcomeOpportunity]:
        """
        Scan all markets and return filtered opportunities.

        Args:
            min_spread_pct: Minimum spread % (default: 0.0 - no filter!)
            min_prob: Minimum outcome probability (default: 0.66 - biased markets only)
            max_prob: Maximum outcome probability (default: 0.85 - sweet spot 66-85%)

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

        # Fetch all active markets
        markets = self.client.get_all_active_markets()

        if not markets:
            logger.warning("No active markets found!")
            return []

        logger.info(f"   Found {len(markets)} active markets")
        logger.info("")

        opportunities = []
        total_outcomes = 0
        rejected_spread = 0
        rejected_probability = 0

        # Analyze each market
        for i, market in enumerate(markets):
            if (i + 1) % 50 == 0:
                logger.info(f"   Progress: {i + 1}/{len(markets)} markets...")

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
        print("│ Rank │ Mkt ID │ Outcme │ Spread │  Prob   │  Bias  │ Vol 24h  │  Score │")
        print("├──────┼────────┼────────┼────────┼─────────┼────────┼──────────┼────────┤")

        for i, opp in enumerate(top_opps, 1):
            print(f"│ {i:4} │ {opp.market_id:6} │ {opp.outcome:6} │ {opp.spread_pct:5.1f}% │ {opp.probability*100:6.1f}% │ {opp.bid_volume_pct:5.1f}% │ ${opp.volume_24h:7.0f} │ {opp.score:6.1f} │")

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
            print(f"   Volume 24h: ${best.volume_24h:.2f}")
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
                'volume_24h', 'orders_bid', 'orders_ask',
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
                    'volume_24h': f"{opp.volume_24h:.2f}",
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
        print(f"   Average volume: ${avg_volume:.2f}")
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
        '--top',
        type=int,
        default=20,
        help='Show top N results (default: 20)'
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
            max_prob=args.max_prob
        )
    except Exception as e:
        logger.error(f"❌ Error scanning markets: {e}")
        import traceback
        traceback.print_exc()
        return 1

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
