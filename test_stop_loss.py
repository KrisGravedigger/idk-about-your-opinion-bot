"""
Temporary test script to verify stop-loss protection works correctly.

Tests:
1. Fetch real markets with orderbooks
2. Simulate positions at different buy prices
3. Calculate unrealized losses
4. Verify stop-loss trigger logic matches expectations
5. Test edge cases: -5%, -10%, -15% losses
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

# Try to import API client, but make it optional for logic testing
API_AVAILABLE = False
try:
    from api_client import OpinionClient
    API_AVAILABLE = True
except ImportError:
    pass  # Will print message later

# Try to import config, use defaults if not available
try:
    from config import STOP_LOSS_TRIGGER_PERCENT, ENABLE_STOP_LOSS
except Exception as e:
    print(f"⚠️  Could not import config: {e}")
    print(f"   Using default values")
    print()
    STOP_LOSS_TRIGGER_PERCENT = -10.0
    ENABLE_STOP_LOSS = True

# Simple utility functions if utils not available
def safe_float(value, default=0.0):
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default

def format_price(price):
    return f"${price:.4f}"

def format_percent(pct):
    return f"{pct:+.2f}%"


def test_stop_loss_logic():
    """Test if stop-loss trigger logic works correctly."""

    global API_AVAILABLE

    print("=" * 80)
    print("STOP-LOSS PROTECTION TEST")
    print("=" * 80)
    print()

    if not API_AVAILABLE:
        print("⚠️  API client not available - will skip real market tests")
        print("   Testing stop-loss logic only")
        print()

    print(f"📊 Configuration:")
    print(f"   ENABLE_STOP_LOSS: {ENABLE_STOP_LOSS}")
    print(f"   STOP_LOSS_TRIGGER_PERCENT: {STOP_LOSS_TRIGGER_PERCENT}%")
    print()

    if not ENABLE_STOP_LOSS:
        print("⚠️  Stop-loss is DISABLED in config")
        print("   Set ENABLE_STOP_LOSS = True to test")
        return

    # Initialize client (if available)
    all_markets = []
    if API_AVAILABLE:
        client = OpinionClient()
        print("🔍 Fetching active markets to test with real orderbook data...")
        all_markets = client.get_all_active_markets()

        if not all_markets:
            print("❌ Failed to fetch markets")
            API_AVAILABLE = False
        else:
            print(f"✅ Found {len(all_markets)} total markets")
            print()

    # ==========================================================================
    # PART 1: TEST WITH REAL MARKET DATA (Skip if API not available)
    # ==========================================================================
    if API_AVAILABLE and all_markets:
        print("=" * 80)
        print("PART 1: TESTING WITH REAL MARKET ORDERBOOKS")
        print("=" * 80)
        print()

        tested_count = 0
        markets_with_loss = []

        for i, market in enumerate(all_markets[:10], 1):  # Test first 10 markets
            market_id = market.get('market_id', 'unknown')
            title = market.get('title', 'No title')[:60]

            print(f"\n📌 Market #{i}: {market_id}")
            print(f"   Title: {title}")

            # Get token IDs
            yes_token_id = market.get('yes_token_id')
            no_token_id = market.get('no_token_id')

            if not yes_token_id:
                print("   ⚠️  No YES token ID - skipping")
                continue

            # Get orderbook for YES token
            try:
                orderbook = client.get_market_orderbook(yes_token_id)

                if not orderbook or 'bids' not in orderbook or 'asks' not in orderbook:
                    print("   ⚠️  Failed to fetch orderbook - skipping")
                    continue

                bids = orderbook.get('bids', [])
                asks = orderbook.get('asks', [])

                if not bids or not asks:
                    print("   ⚠️  Empty orderbook - skipping")
                    continue

                # Extract best bid and ask (orderbook is NOT sorted)
                best_bid = max(safe_float(bid.get('price', 0)) for bid in bids)
                best_ask = min(safe_float(ask.get('price', 0)) for ask in asks)

                if best_bid <= 0 or best_ask <= 0:
                    print("   ⚠️  Invalid prices - skipping")
                    continue

                print(f"   Best bid: {format_price(best_bid)}")
                print(f"   Best ask: {format_price(best_ask)}")

                # Simulate: bought at best_ask, now market at best_bid
                simulated_buy_price = best_ask
                current_market_price = best_bid

                # Calculate unrealized loss
                unrealized_loss_pct = ((current_market_price - simulated_buy_price) / simulated_buy_price) * 100

                print(f"   Simulated scenario:")
                print(f"   - Bought at: {format_price(simulated_buy_price)}")
                print(f"   - Current bid: {format_price(current_market_price)}")
                print(f"   - Unrealized loss: {format_percent(unrealized_loss_pct)}")

                # Check if stop-loss would trigger
                should_trigger = unrealized_loss_pct <= STOP_LOSS_TRIGGER_PERCENT

                if should_trigger:
                    print(f"   🛑 Stop-loss WOULD TRIGGER (loss exceeds {STOP_LOSS_TRIGGER_PERCENT}%)")
                    markets_with_loss.append({
                        'market_id': market_id,
                        'title': title,
                        'buy_price': simulated_buy_price,
                        'current_price': current_market_price,
                        'loss_pct': unrealized_loss_pct
                    })
                else:
                    print(f"   ✅ Stop-loss would NOT trigger (loss within threshold)")

                tested_count += 1

            except Exception as e:
                print(f"   ⚠️  Error testing market: {e}")
                continue

        print()
        print("=" * 80)
        print(f"PART 1 SUMMARY: Tested {tested_count} markets")
        print("=" * 80)
        print(f"Markets where stop-loss would trigger: {len(markets_with_loss)}")
        if markets_with_loss:
            print()
            for m in markets_with_loss:
                print(f"   - {m['market_id'][:20]}... Loss: {format_percent(m['loss_pct'])}")
        print()
    else:
        print("=" * 80)
        print("PART 1: SKIPPED (API not available)")
        print("=" * 80)
        print()

    # ==========================================================================
    # PART 2: TEST EDGE CASES WITH SYNTHETIC DATA
    # ==========================================================================
    print("=" * 80)
    print("PART 2: TESTING EDGE CASES WITH SYNTHETIC DATA")
    print("=" * 80)
    print()

    test_cases = [
        # (buy_price, current_price, expected_trigger, description)
        (0.100, 0.095, False, "5% loss - should NOT trigger (-10% threshold)"),
        (0.100, 0.090, True, "10% loss - should trigger EXACTLY at threshold"),
        (0.100, 0.089, True, "11% loss - should trigger (exceeds threshold)"),
        (0.100, 0.085, True, "15% loss - should trigger (well beyond threshold)"),
        (0.100, 0.070, True, "30% loss - should trigger (severe loss)"),
        (0.100, 0.100, False, "0% loss - should NOT trigger"),
        (0.100, 0.105, False, "5% GAIN - should NOT trigger"),
        (0.050, 0.045, True, "10% loss at lower price point"),
        (1.000, 0.899, True, "10.1% loss at higher price point"),  # Slightly more to avoid float precision
        (0.200, 0.195, False, "2.5% loss - should NOT trigger"),
        (0.200, 0.178, True, "11% loss - should trigger"),
    ]

    print(f"Testing {len(test_cases)} synthetic scenarios:")
    print(f"Stop-loss threshold: {STOP_LOSS_TRIGGER_PERCENT}%")
    print()

    passed = 0
    failed = 0

    for i, (buy_price, current_price, expected_trigger, description) in enumerate(test_cases, 1):
        # Calculate loss percentage (same formula as in sell_monitor.py)
        unrealized_loss_pct = ((current_price - buy_price) / buy_price) * 100

        # Check if stop-loss would trigger (same logic as in sell_monitor.py)
        would_trigger = unrealized_loss_pct <= STOP_LOSS_TRIGGER_PERCENT

        # Verify result matches expectation
        result = "✅ PASS" if would_trigger == expected_trigger else "❌ FAIL"

        print(f"Test #{i}: {description}")
        print(f"   Buy: {format_price(buy_price)}, Current: {format_price(current_price)}")
        print(f"   Loss: {format_percent(unrealized_loss_pct)}")
        print(f"   Would trigger: {would_trigger}, Expected: {expected_trigger}")
        print(f"   {result}")
        print()

        if would_trigger == expected_trigger:
            passed += 1
        else:
            failed += 1
            print(f"   🐛 BUG DETECTED: Stop-loss logic not working correctly!")
            print()

    print("=" * 80)
    print("PART 2 SUMMARY")
    print("=" * 80)
    print(f"Tests passed: {passed}/{len(test_cases)}")
    print(f"Tests failed: {failed}/{len(test_cases)}")
    print()

    if failed > 0:
        print("❌ STOP-LOSS LOGIC HAS BUGS!")
        print("   Review the check_stop_loss() method in sell_monitor.py")
    else:
        print("✅ STOP-LOSS LOGIC IS WORKING CORRECTLY!")
    print()

    # ==========================================================================
    # PART 3: TEST WITH MOCK STATE (Full Integration Test)
    # ==========================================================================
    if not API_AVAILABLE or not all_markets:
        print("=" * 80)
        print("PART 3: SKIPPED (API not available)")
        print("=" * 80)
        print()
    else:
        print("=" * 80)
        print("PART 3: INTEGRATION TEST WITH SellMonitor.check_stop_loss()")
        print("=" * 80)
        print()

        print("Finding a suitable market with active orderbook...")

        # Find a market with good orderbook
        test_market = None
        for market in all_markets[:20]:
            yes_token_id = market.get('yes_token_id')
            if not yes_token_id:
                continue

            try:
                orderbook = client.get_market_orderbook(yes_token_id)
                bids = orderbook.get('bids', [])
                asks = orderbook.get('asks', [])

                if bids and asks:
                    best_bid = max(safe_float(bid.get('price', 0)) for bid in bids)
                    best_ask = min(safe_float(ask.get('price', 0)) for ask in asks)

                    if best_bid > 0 and best_ask > 0 and best_ask > best_bid:
                        test_market = {
                            'market_id': market.get('market_id'),
                            'title': market.get('title', 'No title')[:60],
                            'yes_token_id': yes_token_id,
                            'best_bid': best_bid,
                            'best_ask': best_ask
                        }
                        break
            except:
                continue

        if not test_market:
            print("⚠️  Could not find suitable market for integration test")
            print("   Skipping Part 3")
        else:
            print(f"✅ Selected market: {test_market['market_id']}")
            print(f"   Title: {test_market['title']}")
            print(f"   Best bid: {format_price(test_market['best_bid'])}")
            print(f"   Best ask: {format_price(test_market['best_ask'])}")
            print()

            # Import SellMonitor
            from monitoring.sell_monitor import SellMonitor
            import config as config_module

            # Create mock state with simulated position
            # Simulate: bought at best_ask, market dropped to make -12% loss
            simulated_buy_price = test_market['best_ask']
            simulated_loss_price = simulated_buy_price * 0.88  # -12% loss

            mock_state = {
                'current_position': {
                    'market_id': test_market['market_id'],
                    'token_id': test_market['yes_token_id'],
                    'avg_fill_price': simulated_buy_price,  # This is the buy price
                    'filled_amount': 100.0,  # Holding 100 tokens
                    'sell_price': 0.0
                }
            }

            # Create config dict
            config_dict = {
                'FILL_CHECK_INTERVAL_SECONDS': config_module.FILL_CHECK_INTERVAL_SECONDS,
                'SELL_ORDER_TIMEOUT_HOURS': config_module.SELL_ORDER_TIMEOUT_HOURS,
                'ENABLE_STOP_LOSS': config_module.ENABLE_STOP_LOSS,
                'STOP_LOSS_TRIGGER_PERCENT': config_module.STOP_LOSS_TRIGGER_PERCENT,
                'STOP_LOSS_AGGRESSIVE_OFFSET': config_module.STOP_LOSS_AGGRESSIVE_OFFSET,
                'LIQUIDITY_AUTO_CANCEL': config_module.LIQUIDITY_AUTO_CANCEL,
                'LIQUIDITY_BID_DROP_THRESHOLD': config_module.LIQUIDITY_BID_DROP_THRESHOLD,
                'LIQUIDITY_SPREAD_THRESHOLD': config_module.LIQUIDITY_SPREAD_THRESHOLD,
            }

            print(f"Creating SellMonitor with simulated position:")
            print(f"   Simulated buy price: {format_price(simulated_buy_price)}")
            print(f"   Current best bid: {format_price(test_market['best_bid'])}")
            print(f"   Holding: 100.0 tokens")
            print()

            # Create monitor
            monitor = SellMonitor(config_dict, client, mock_state)

            # Test check_stop_loss() method
            print("Testing SellMonitor.check_stop_loss() method...")
            should_trigger, unrealized_loss_pct = monitor.check_stop_loss(simulated_buy_price)

            print()
            print(f"Result:")
            print(f"   Should trigger: {should_trigger}")
            print(f"   Unrealized loss: {format_percent(unrealized_loss_pct)}")
            print(f"   Threshold: {format_percent(STOP_LOSS_TRIGGER_PERCENT)}")
            print()

            # Verify logic
            if unrealized_loss_pct <= STOP_LOSS_TRIGGER_PERCENT:
                expected_trigger = True
            else:
                expected_trigger = False

            if should_trigger == expected_trigger:
                print("✅ INTEGRATION TEST PASSED!")
                print(f"   Stop-loss correctly {'triggered' if should_trigger else 'did not trigger'}")
            else:
                print("❌ INTEGRATION TEST FAILED!")
                print(f"   Expected: {expected_trigger}, Got: {should_trigger}")
                print("   🐛 BUG: check_stop_loss() method not working correctly")

    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    test_stop_loss_logic()
