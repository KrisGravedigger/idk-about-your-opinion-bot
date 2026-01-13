#!/usr/bin/env python3
"""
Place Order Response Inspector
===============================

Shows the exact structure of V2AddOrderResp from place_order() call.
This will help us extract order_id correctly.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from opinion_clob_sdk import Client
    from opinion_clob_sdk.api_models import PlaceOrderDataInput, OrderSide, LIMIT_ORDER
except ImportError:
    print("ERROR: opinion_clob_sdk not installed!")
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv()

def inspect_object(obj, name="object", indent=0):
    """Recursively inspect an object's structure."""
    prefix = "  " * indent
    
    print(f"{prefix}{name}:")
    print(f"{prefix}  Type: {type(obj).__name__}")
    
    # Show all attributes
    if hasattr(obj, '__dict__'):
        print(f"{prefix}  Attributes via __dict__:")
        for key, value in obj.__dict__.items():
            if not key.startswith('_'):
                print(f"{prefix}    - {key}: {type(value).__name__} = {repr(value)[:80]}")
    
    # Try Pydantic model_dump
    if hasattr(obj, 'model_dump'):
        print(f"{prefix}  Pydantic v2 model_dump():")
        try:
            dumped = obj.model_dump()
            print(f"{prefix}    {dumped}")
        except Exception as e:
            print(f"{prefix}    Error: {e}")
    
    # Try Pydantic dict
    elif hasattr(obj, 'dict'):
        print(f"{prefix}  Pydantic v1 dict():")
        try:
            dumped = obj.dict()
            print(f"{prefix}    {dumped}")
        except Exception as e:
            print(f"{prefix}    Error: {e}")
    
    print()


def main():
    """Inspect place_order response."""
    print("=" * 70)
    print("  PLACE ORDER RESPONSE INSPECTOR")
    print("=" * 70)
    
    # Get config
    API_KEY = os.getenv('API_KEY', '')
    PRIVATE_KEY = os.getenv('PRIVATE_KEY', '')
    CHAIN_ID = int(os.getenv('CHAIN_ID', '56'))
    RPC_URL = os.getenv('RPC_URL', 'https://bsc-dataseed.binance.org/')
    MULTI_SIG_RAW = os.getenv('MULTI_SIG_ADDRESS', '').strip()
    MULTI_SIG_ADDRESS = MULTI_SIG_RAW if MULTI_SIG_RAW else None
    
    if not API_KEY or not PRIVATE_KEY:
        print("ERROR: API_KEY or PRIVATE_KEY not set in .env")
        return 1
    
    print("\nConfiguration:")
    print(f"  API_KEY: {API_KEY[:20]}...")
    print(f"  MULTI_SIG_ADDRESS: {MULTI_SIG_ADDRESS}")
    print()
    
    # Create client
    print("Creating Opinion SDK client...")
    try:
        client_params = {
            'host': 'https://proxy.opinion.trade:8443',
            'apikey': API_KEY,
            'chain_id': CHAIN_ID,
            'private_key': PRIVATE_KEY,
            'rpc_url': RPC_URL
        }
        
        if MULTI_SIG_ADDRESS:
            client_params['multi_sig_addr'] = MULTI_SIG_ADDRESS
        
        client = Client(**client_params)
        print("✓ Client created successfully\n")
    except Exception as e:
        print(f"✗ Failed to create client: {e}\n")
        return 1
    
    # Get balance first
    print("Checking USDT balance...")
    try:
        balance_response = client.get_my_balances()
        if balance_response.result and hasattr(balance_response.result, 'balances'):
            balances = balance_response.result.balances
            if balances and len(balances) > 0:
                available = balances[0].available_balance
                print(f"✓ Available: {available} USDT\n")
                
                if float(available) < 1:
                    print("⚠️ WARNING: Less than 1 USDT available!")
                    print("This test will place a 0.5 USDT order.\n")
            else:
                print("⚠️ No USDT balance found\n")
        else:
            print("⚠️ Could not check balance\n")
    except Exception as e:
        print(f"⚠️ Error checking balance: {e}\n")
    
    # Ask for confirmation
    print("=" * 70)
    print("  TEST ORDER DETAILS")
    print("=" * 70)
    print("\nThis will place a SMALL test order:")
    print("  Market: #2362 (Cloudflare incident)")
    print("  Side: BUY")
    print("  Price: $0.001 (very low - unlikely to fill)")
    print("  Amount: 0.5 USDT")
    print()
    print("This is a REAL order that will be placed on Opinion.trade!")
    print("You can cancel it manually after inspection.")
    print()
    
    proceed = input("Proceed with test order? (yes/no): ").strip().lower()
    if proceed not in ['yes', 'y']:
        print("\nTest cancelled.")
        return 0
    
    # Place test order
    print("\n" + "=" * 70)
    print("  PLACING TEST ORDER")
    print("=" * 70)
    
    try:
        order_input = PlaceOrderDataInput(
            marketId=2362,  # Cloudflare market
            tokenId="0",    # YES token
            side=OrderSide.BUY,
            orderType=LIMIT_ORDER,
            price="0.001",  # Very low price
            makerAmountInQuoteToken=0.5  # 0.5 USDT
        )
        
        print("\nCalling client.place_order()...")
        response = client.place_order(order_input, check_approval=False)
        
        print("\n✓ Response received!")
        print()
        
        # Inspect top-level response
        inspect_object(response, "response", indent=0)
        
        # Inspect response.result if exists
        if hasattr(response, 'result') and response.result is not None:
            print("-" * 70)
            inspect_object(response.result, "response.result", indent=0)
            
            # Try to access different possible attributes
            result = response.result
            
            print("=" * 70)
            print("  ATTEMPTING TO EXTRACT ORDER_ID")
            print("=" * 70)
            
            # Try different attribute names
            possible_attrs = [
                'order_id', 'orderId', 'order_ID', 'OrderId',
                'id', 'Id', 'ID',
                'data', 'Data'
            ]
            
            found_order_id = False
            
            for attr in possible_attrs:
                if hasattr(result, attr):
                    value = getattr(result, attr)
                    print(f"\n✓ Found attribute '{attr}': {value}")
                    found_order_id = True
                    
                    # If it's 'data', inspect it further
                    if attr == 'data' and value is not None:
                        print("\n  Inspecting 'data' object:")
                        inspect_object(value, "data", indent=1)
            
            if not found_order_id:
                print("\n✗ No obvious order_id attribute found")
                print("\nAll available attributes:")
                for attr in dir(result):
                    if not attr.startswith('_'):
                        try:
                            val = getattr(result, attr)
                            if not callable(val):
                                print(f"  - {attr}: {type(val).__name__}")
                        except:
                            pass
        
        print()
        print("=" * 70)
        print("  API RESPONSE STATUS")
        print("=" * 70)
        if hasattr(response, 'errno'):
            print(f"errno: {response.errno}")
        if hasattr(response, 'errmsg'):
            print(f"errmsg: {response.errmsg}")
        
        print()
        print("=" * 70)
        print("  NEXT STEPS")
        print("=" * 70)
        print("\n1. Go to https://opinion.trade")
        print("2. Check your active orders")
        print("3. You should see a 0.5 USDT BUY order at $0.001")
        print("4. Cancel it manually if you want")
        print()
        print("Share the output above and I'll write the exact fix for order_id extraction!")
        
    except Exception as e:
        print(f"\n✗ Error placing order: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
