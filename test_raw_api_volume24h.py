#!/usr/bin/env python3
"""
Test script to verify volume24h field from raw API
"""

import requests
import json

# Your API key from .env
API_KEY = "your_api_key_here"  # Replace with actual key

url = "https://proxy.opinion.trade:8443/openapi/market"
headers = {
    "apikey": API_KEY
}
params = {
    "status": 2,  # ACTIVATED
    "sortBy": 5,  # Sort by volume24h (based on docs)
    "limit": 5,
    "page": 1
}

print("🔍 Testing raw API endpoint for volume24h...\n")

response = requests.get(url, headers=headers, params=params, verify=False)
data = response.json()

if data.get("code") == 0:
    markets = data["result"]["list"]
    print(f"✅ Found {len(markets)} markets\n")

    for i, market in enumerate(markets, 1):
        print(f"=== Market {i} ===")
        print(f"ID: {market.get('marketId')}")
        print(f"Title: {market.get('marketTitle', 'Unknown')[:50]}...")
        print(f"volume24h: {market.get('volume24h')} ← SHOULD EXIST!")
        print(f"volume (lifetime): {market.get('volume')}")
        print(f"All keys: {list(market.keys())}")
        print()
else:
    print(f"❌ API error: {data.get('msg')}")
