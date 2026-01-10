#!/usr/bin/env python3
"""
Test script to verify volume24h field from raw API
"""

import requests
import json
import os
import sys

# Try to load API key from .env file manually (without python-dotenv dependency)
def load_env_file():
    """Manually parse .env file if it exists"""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key.strip() == 'API_KEY':
                        return value.strip().strip('"').strip("'")
    return None

# Load API key from .env file or environment
API_KEY = load_env_file() or os.getenv("API_KEY")

if not API_KEY:
    print("❌ Error: API_KEY not found!")
    print("Please either:")
    print("  1. Create a .env file with API_KEY=your_key")
    print("  2. Export API_KEY environment variable")
    print("  3. Edit this script and set API_KEY directly")
    sys.exit(1)

url = "https://proxy.opinion.trade:8443/openapi/market"
headers = {
    "apikey": API_KEY
}
params = {
    "status": "activated",  # Must be string: 'activated' or 'resolved'
    "sortBy": 5,  # Sort by volume24h (based on docs)
    "limit": 5,
    "page": 1
}

print("🔍 Testing raw API endpoint for volume24h...\n")
print(f"🌐 URL: {url}")
print(f"📝 Params: {params}")
print(f"🔑 API Key: {API_KEY[:10]}..." if len(API_KEY) > 10 else f"🔑 API Key: {API_KEY}")
print()

response = requests.get(url, headers=headers, params=params, verify=False)

print(f"📡 HTTP Status: {response.status_code}")
print()

# Try to parse JSON
try:
    data = response.json()
    print("📦 Raw Response:")
    print(json.dumps(data, indent=2)[:500])  # First 500 chars
    print()
except Exception as e:
    print(f"❌ Failed to parse JSON: {e}")
    print(f"📄 Raw text response:")
    print(response.text[:500])
    import sys
    sys.exit(1)

# Check response structure
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
    print(f"❌ API Error")
    print(f"   Code: {data.get('code')}")
    print(f"   Message: {data.get('msg')}")
    print(f"   Full response: {json.dumps(data, indent=2)}")
