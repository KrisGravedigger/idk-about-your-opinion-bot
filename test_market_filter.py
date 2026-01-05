"""
Temporary test script to verify market time filtering works correctly.

Tests:
1. Scan markets
2. Check which markets are filtered out due to MIN_HOURS_UNTIL_CLOSE
3. Log detailed diagnostics for each market (end_time, hours remaining, etc.)
"""

import os
import sys
from datetime import datetime, timezone

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env manually if dotenv not available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Load .env manually
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

from api_client import OpinionClient
from market_scanner import MarketScanner
from config import MIN_HOURS_UNTIL_CLOSE, MAX_HOURS_UNTIL_CLOSE
from logger_config import setup_logger

logger = setup_logger(__name__)


def test_market_time_filtering():
    """Test if MIN_HOURS_UNTIL_CLOSE filter works correctly."""

    print("=" * 80)
    print("MARKET TIME FILTER TEST")
    print("=" * 80)
    print()
    print(f"📊 Configuration:")
    print(f"   MIN_HOURS_UNTIL_CLOSE: {MIN_HOURS_UNTIL_CLOSE}")
    print(f"   MAX_HOURS_UNTIL_CLOSE: {MAX_HOURS_UNTIL_CLOSE}")
    print()

    # Initialize client
    client = OpinionClient()

    # Get all markets (raw, unfiltered)
    print("🔍 Fetching all active markets from API...")
    all_markets = client.get_all_active_markets()

    if not all_markets:
        print("❌ Failed to fetch markets")
        return

    print(f"✅ Found {len(all_markets)} total markets")
    print()

    # Analyze each market's end_time
    print("=" * 80)
    print("ANALYZING MARKET END TIMES")
    print("=" * 80)
    print()

    now = datetime.now(timezone.utc)
    markets_with_time = 0
    markets_without_time = 0
    markets_filtered_min = 0
    markets_filtered_max = 0
    markets_passed = 0

    for i, market in enumerate(all_markets[:20], 1):  # Analyze first 20 markets
        market_id = market.get('market_id', 'unknown')
        title = market.get('title', 'No title')[:60]
        end_at = market.get('end_at')

        print(f"\n📌 Market #{i}: {market_id}")
        print(f"   Title: {title}")

        # Check all possible time-related fields
        time_fields = ['end_at', 'cutoff_at', 'end_time', 'close_time', 'closing_time', 'expiry', 'expires_at']
        found_time_field = None
        for field in time_fields:
            if field in market and market[field] is not None:
                print(f"   ✅ Found time field '{field}': {market[field]}")
                found_time_field = field
                end_at = market[field]
                break

        if not found_time_field:
            print(f"   ⚠️  No time fields found")
            # Print first few fields to see structure
            print(f"   Available fields: {list(market.keys())[:10]}")

        if end_at:
            markets_with_time += 1
            try:
                # Parse end_at as Unix timestamp
                end_time = datetime.fromtimestamp(end_at, tz=timezone.utc)
                hours_until_close = (end_time - now).total_seconds() / 3600

                print(f"   End time: {end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                print(f"   Hours until close: {hours_until_close:.1f}h")

                # Check against filters
                if MIN_HOURS_UNTIL_CLOSE is not None and hours_until_close < MIN_HOURS_UNTIL_CLOSE:
                    print(f"   ❌ FILTERED: Too soon (< {MIN_HOURS_UNTIL_CLOSE}h)")
                    markets_filtered_min += 1
                elif MAX_HOURS_UNTIL_CLOSE is not None and hours_until_close > MAX_HOURS_UNTIL_CLOSE:
                    print(f"   ❌ FILTERED: Too far (> {MAX_HOURS_UNTIL_CLOSE}h)")
                    markets_filtered_max += 1
                else:
                    print(f"   ✅ PASSED time filter")
                    markets_passed += 1

            except Exception as e:
                print(f"   ⚠️  Error parsing end_at: {e}")
        else:
            markets_without_time += 1
            print(f"   ⚠️  No end_at field")

    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total markets analyzed: {min(20, len(all_markets))}")
    print(f"Markets with end_at: {markets_with_time}")
    print(f"Markets without end_at: {markets_without_time}")
    print()
    print(f"✅ Passed filter: {markets_passed}")
    print(f"❌ Filtered (< {MIN_HOURS_UNTIL_CLOSE}h): {markets_filtered_min}")
    if MAX_HOURS_UNTIL_CLOSE:
        print(f"❌ Filtered (> {MAX_HOURS_UNTIL_CLOSE}h): {markets_filtered_max}")
    print()

    # Test with MarketScanner
    print("=" * 80)
    print("TESTING WITH MarketScanner.find_best_market()")
    print("=" * 80)
    print()

    scanner = MarketScanner(client)

    print("🔍 Scanning for best market (this will apply all filters)...")
    best_market = scanner.get_best_market()

    if best_market:
        print(f"✅ Found best market:")
        print(f"   Market ID: {best_market.market_id}")
        print(f"   Title: {best_market.title[:60]}")
        print(f"   Score: {best_market.score:.2f}")
        print(f"   Spread: {best_market.spread_pct:.2f}%")

        # Check its end time
        market_data = next((m for m in all_markets if m.get('market_id') == best_market.market_id), None)
        if market_data and market_data.get('cutoff_at'):
            end_time = datetime.fromtimestamp(market_data['cutoff_at'], tz=timezone.utc)
            hours_until_close = (end_time - now).total_seconds() / 3600
            print(f"   Cutoff time: {end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"   Hours until close: {hours_until_close:.1f}h")

            if hours_until_close < MIN_HOURS_UNTIL_CLOSE:
                print(f"   ⚠️  WARNING: Market closes in < {MIN_HOURS_UNTIL_CLOSE}h but was NOT filtered!")
                print(f"   🐛 BUG DETECTED: Time filter is NOT working!")
            else:
                print(f"   ✅ VERIFIED: Market closes in > {MIN_HOURS_UNTIL_CLOSE}h")
                print(f"   ✅ Time filter is WORKING correctly!")
        else:
            print(f"   ⚠️  No cutoff_at field for this market")
    else:
        print("❌ No market found (all filtered or no suitable markets)")

    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    test_market_time_filtering()
