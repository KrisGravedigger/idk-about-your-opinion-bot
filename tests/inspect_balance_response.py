#!/usr/bin/env python3
"""
Balance API Response Inspector
===============================

Shows the EXACT structure of response from get_my_balances() API call.
This will help us understand what structure the SDK actually returns.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from opinion_clob_sdk import Client
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
    print(f"{prefix}  Value: {repr(obj)[:100]}...")
    
    # Show all attributes
    if hasattr(obj, '__dict__'):
        print(f"{prefix}  Attributes via __dict__:")
        for key, value in obj.__dict__.items():
            if not key.startswith('_'):
                print(f"{prefix}    - {key}: {type(value).__name__} = {repr(value)[:60]}")
    
    # Show dir() for public methods/attributes
    print(f"{prefix}  Public attributes via dir():")
    public_attrs = [attr for attr in dir(obj) if not attr.startswith('_')]
    for attr in public_attrs[:20]:  # Limit to first 20
        try:
            value = getattr(obj, attr)
            if not callable(value):
                print(f"{prefix}    - {attr}: {type(value).__name__}")
        except:
            pass
    
    # Try Pydantic model_dump
    if hasattr(obj, 'model_dump'):
        print(f"{prefix}  Pydantic v2 model_dump():")
        try:
            dumped = obj.model_dump()
            print(f"{prefix}    {dumped}")
        except Exception as e:
            print(f"{prefix}    Error: {e}")
    
    # Try Pydantic dict
    if hasattr(obj, 'dict'):
        print(f"{prefix}  Pydantic v1 dict():")
        try:
            dumped = obj.dict()
            print(f"{prefix}    {dumped}")
        except Exception as e:
            print(f"{prefix}    Error: {e}")
    
    print()


def main():
    """Inspect balance API response."""
    print("=" * 70)
    print("  BALANCE API RESPONSE INSPECTOR")
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
    print(f"  PRIVATE_KEY: ***{PRIVATE_KEY[-10:]}")
    print(f"  MULTI_SIG_ADDRESS: {MULTI_SIG_ADDRESS}")
    print(f"  CHAIN_ID: {CHAIN_ID}")
    print()
    
    # Create client
    print("Creating Opinion SDK client...")
    try:
        client_params = {
            'host': 'https://proxy.opinion.trade:8443',  # FIXED: use correct API host
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
    
    # Call get_my_balances()
    print("=" * 70)
    print("  CALLING get_my_balances()")
    print("=" * 70)
    print()
    
    try:
        response = client.get_my_balances()
        
        print("RESPONSE RECEIVED!")
        print()
        
        # Inspect top-level response
        inspect_object(response, "response", indent=0)
        
        # Inspect response.result if exists
        if hasattr(response, 'result') and response.result is not None:
            print("-" * 70)
            inspect_object(response.result, "response.result", indent=0)
            
            # Try to access .data
            if hasattr(response.result, 'data'):
                print("-" * 70)
                inspect_object(response.result.data, "response.result.data", indent=0)
        
        # Show errno and errmsg
        print("=" * 70)
        print("  API RESPONSE STATUS")
        print("=" * 70)
        if hasattr(response, 'errno'):
            print(f"errno: {response.errno}")
        if hasattr(response, 'errmsg'):
            print(f"errmsg: {response.errmsg}")
        
        # Try to extract USDT balance
        print()
        print("=" * 70)
        print("  ATTEMPTING TO EXTRACT USDT BALANCE")
        print("=" * 70)
        
        # Method 1: response.result.data
        print("\nMethod 1: response.result.data")
        try:
            if hasattr(response, 'result') and response.result:
                if hasattr(response.result, 'data'):
                    data = response.result.data
                    print(f"  ✓ Found: {type(data)}")
                    print(f"  Content: {data}")
                    
                    if isinstance(data, dict):
                        if 'usdt' in data:
                            print(f"  ✓ USDT key exists: {data['usdt']}")
                        elif 'USDT' in data:
                            print(f"  ✓ USDT key exists: {data['USDT']}")
                        else:
                            print(f"  ✗ No 'usdt' or 'USDT' key. Available keys: {list(data.keys())}")
                else:
                    print("  ✗ No 'data' attribute on result")
            else:
                print("  ✗ No result")
        except Exception as e:
            print(f"  ✗ Error: {e}")
        
        # Method 2: response.result as balance directly
        print("\nMethod 2: response.result (Pydantic model)")
        try:
            if hasattr(response, 'result') and response.result:
                result = response.result
                
                # Try model_dump
                if hasattr(result, 'model_dump'):
                    dumped = result.model_dump()
                    print(f"  ✓ model_dump() returned: {type(dumped)}")
                    print(f"  Content: {dumped}")
                    
                    if isinstance(dumped, dict) and 'usdt' in dumped:
                        print(f"  ✓ USDT in dumped data: {dumped['usdt']}")
                
                # Try dict
                elif hasattr(result, 'dict'):
                    dumped = result.dict()
                    print(f"  ✓ dict() returned: {type(dumped)}")
                    print(f"  Content: {dumped}")
                    
                    if isinstance(dumped, dict) and 'usdt' in dumped:
                        print(f"  ✓ USDT in dumped data: {dumped['usdt']}")
                
                else:
                    print("  ✗ Not a Pydantic model")
        except Exception as e:
            print(f"  ✗ Error: {e}")
        
        print()
        print("=" * 70)
        print("  DIAGNOSIS COMPLETE")
        print("=" * 70)
        print()
        print("If you see your USDT balance above, note:")
        print("  1. Which method successfully extracted it")
        print("  2. The key name used ('usdt', 'USDT', or other)")
        print("  3. The format (integer wei or float)")
        print()
        print("Share this output and I'll write the exact fix needed!")
        
    except Exception as e:
        print(f"✗ Error calling get_my_balances(): {e}")
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
