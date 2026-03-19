"""
Opinion Farming Bot - API Client Module (DEPRECATED)
=====================================================

BACKWARD COMPATIBILITY SHIM
---------------------------
This module exists for backward compatibility with existing bot code.
It now delegates all operations to the new OpinionAdapter class.

New code should use the adapter pattern instead:
    from adapters.opinion_adapter import OpinionAdapter
    client = OpinionAdapter()

This file will be removed in a future refactor once all bot code
migrates to the universal prediction market interface.

What moved:
-----------
- All Opinion.trade logic → adapters/opinion_adapter.py
- Universal interface → adapters/base.py (PredictionMarketClient ABC)
- SSL certificate fixes → Still here (global imports)

Migration Guide:
----------------
Old code:
    from api_client import OpinionClient
    client = OpinionClient()

New code (recommended):
    from adapters.opinion_adapter import OpinionAdapter
    client = OpinionAdapter()

Both work identically - this shim ensures no breaking changes.
"""

# === SSL CERTIFICATE FIX ===
# Opinion.trade proxy uses self-signed certificate
# Disable SSL verification to avoid connection errors
# (Keep this here for global effect across all imports)
import ssl
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Monkey patch to disable SSL verification globally
import certifi
import os
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['REQUESTS_CA_BUNDLE'] = ''
os.environ['CURL_CA_BUNDLE'] = ''

# Import the real implementation from adapter
from adapters.opinion_adapter import OpinionAdapter

# Alias for backward compatibility
# Existing bot code uses "OpinionClient", adapter uses "OpinionAdapter"
OpinionClient = OpinionAdapter

# Re-export for backward compatibility
__all__ = ['OpinionClient', 'create_client']


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_client() -> OpinionClient:
    """
    Factory function to create an OpinionClient instance.

    Returns:
        Configured OpinionClient (actually OpinionAdapter)

    Raises:
        ValueError: If credentials are missing
    """
    return OpinionClient()


# =============================================================================
# MODULE TEST
# =============================================================================
if __name__ == "__main__":
    print("=== API Client Module Test ===")
    print("Note: This requires valid credentials in .env file")
    print()

    try:
        client = create_client()
        print("✅ Client created successfully")

        # Test market fetching
        markets = client.get_all_active_markets()
        print(f"✅ Fetched {len(markets)} active markets")

        if markets:
            # Test orderbook for first market
            first_market = markets[0]
            market_id = first_market.get('market_id')
            token_id = first_market.get('yes_token_id')

            print(f"\nTesting orderbook for market {market_id}...")
            orderbook = client.get_market_orderbook(token_id)

            if orderbook:
                bids = orderbook.get('bids', [])
                asks = orderbook.get('asks', [])
                print(f"✅ Orderbook: {len(bids)} bids, {len(asks)} asks")
            else:
                print("⚠️ Empty orderbook")

        print("\n✅ All API client tests passed!")

    except ValueError as e:
        print(f"❌ Configuration error: {e}")
    except Exception as e:
        print(f"❌ Test failed: {e}")
