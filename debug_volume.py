#!/usr/bin/env python3
"""
Debug script to check volume24h field in API response
"""

from api_client import create_client

client = create_client()
markets = client.get_all_active_markets()

print(f"Total markets: {len(markets)}\n")

# Show first 5 markets
for i, market in enumerate(markets[:5]):
    print(f"=== Market {i+1} ===")
    print(f"ID: {market.get('market_id')}")
    print(f"Title: {market.get('market_title', 'Unknown')[:50]}...")

    # Check ALL possible volume fields
    print(f"\nVolume fields:")
    print(f"  volume24h: {market.get('volume24h')} (type: {type(market.get('volume24h'))})")
    print(f"  volume_24h: {market.get('volume_24h')} (type: {type(market.get('volume_24h'))})")
    print(f"  volume: {market.get('volume')} (type: {type(market.get('volume'))})")
    print(f"  total_volume: {market.get('total_volume')} (type: {type(market.get('total_volume'))})")

    # Show all keys
    print(f"\nAll keys in market dict:")
    print(f"  {list(market.keys())}")
    print()

print("\n=== Summary ===")
# Count how many have non-zero volume24h
non_zero = [m for m in markets if m.get('volume24h') not in [None, 0, '0', '0.0', '0.00']]
print(f"Markets with non-zero volume24h: {len(non_zero)} / {len(markets)}")

if non_zero:
    print("\nExample market WITH volume:")
    m = non_zero[0]
    print(f"  ID: {m.get('market_id')}")
    print(f"  Title: {m.get('market_title', 'Unknown')[:50]}...")
    print(f"  volume24h: {m.get('volume24h')}")
