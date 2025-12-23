#!/usr/bin/env python3
"""
Opinion.trade Balance Diagnostic Tool
======================================

Tests API connectivity and balance retrieval with different configurations.

USAGE:
    python diagnose_balance.py

This script will:
1. Test API connection
2. Check balances with different address configurations
3. Verify which address actually holds your USDT
4. Show detailed API responses for debugging
"""

import os
import sys
from typing import Optional

# Add parent directory to path to import bot modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from opinion_clob_sdk import Client
except ImportError:
    print("ERROR: opinion_clob_sdk not installed!")
    print("Install with: pip install opinion-clob-sdk")
    sys.exit(1)


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(label: str, value: str, success: bool = True):
    """Print a formatted result line."""
    symbol = "✓" if success else "✗"
    print(f"  {symbol} {label}: {value}")


def wei_to_usdt(wei_value) -> float:
    """Convert wei (1e6 for USDT) to float."""
    try:
        if isinstance(wei_value, (int, float)):
            return float(wei_value) / 1_000_000
        return 0.0
    except:
        return 0.0


def test_configuration(
    api_key: str,
    private_key: str,
    chain_id: int,
    rpc_url: str,
    multi_sig_addr: Optional[str] = None,
    description: str = ""
) -> dict:
    """
    Test a specific configuration.
    
    Returns:
        dict with test results
    """
    print_section(f"TEST: {description}")
    
    results = {
        'description': description,
        'success': False,
        'client_created': False,
        'balance_retrieved': False,
        'usdt_balance': 0.0,
        'raw_balance_data': None,
        'error': None
    }
    
    try:
        # Build client parameters
        client_params = {
            'host': 'https://proxy.opinion.trade:8443',  # FIXED: use correct API host
            'apikey': api_key,
            'chain_id': chain_id,
            'private_key': private_key,
            'rpc_url': rpc_url
        }
        
        # Add multi_sig only if provided
        if multi_sig_addr:
            client_params['multi_sig_addr'] = multi_sig_addr
            print_result("Multi-sig address", multi_sig_addr)
        else:
            print_result("Mode", "EOA (address derived from private_key)")
        
        # Create client
        print("  Creating client...")
        client = Client(**client_params)
        results['client_created'] = True
        print_result("Client created", "SUCCESS")
        
        # Get balances
        print("  Fetching balances...")
        response = client.get_my_balances()
        
        print(f"  Response errno: {response.errno}")
        print(f"  Response errmsg: {response.errmsg}")
        
        if response.errno != 0:
            results['error'] = f"API error: {response.errmsg}"
            print_result("Balance fetch", f"FAILED: {response.errmsg}", False)
            return results
        
        results['balance_retrieved'] = True
        
        # Try to extract balance data
        if hasattr(response, 'result') and response.result:
            balance_data = response.result.data if hasattr(response.result, 'data') else response.result
            results['raw_balance_data'] = str(balance_data)
            
            print("\n  Raw balance data:")
            print(f"    Type: {type(balance_data)}")
            print(f"    Data: {balance_data}")
            
            # Try different ways to extract USDT balance
            usdt_balance = 0.0
            
            if isinstance(balance_data, dict):
                # Try direct key access
                if 'usdt' in balance_data:
                    usdt_balance = wei_to_usdt(balance_data['usdt'])
                elif 'USDT' in balance_data:
                    usdt_balance = wei_to_usdt(balance_data['USDT'])
                
                # Print all available keys
                print("\n  Available balance keys:")
                for key in balance_data.keys():
                    value = balance_data[key]
                    converted = wei_to_usdt(value) if isinstance(value, (int, float)) else value
                    print(f"    - {key}: {value} (= {converted:.6f} if USDT)")
            
            elif hasattr(balance_data, '__dict__'):
                # Try attribute access
                print("\n  Balance object attributes:")
                for attr in dir(balance_data):
                    if not attr.startswith('_'):
                        value = getattr(balance_data, attr, None)
                        print(f"    - {attr}: {value}")
                        
                        if attr.lower() == 'usdt' and isinstance(value, (int, float)):
                            usdt_balance = wei_to_usdt(value)
            
            results['usdt_balance'] = usdt_balance
            print_result("\nUSDT Balance", f"{usdt_balance:.6f} USDT", usdt_balance > 0)
            
        else:
            print_result("Balance data", "NO DATA RETURNED", False)
            results['error'] = "No balance data in response"
        
        results['success'] = True
        
    except Exception as e:
        results['error'] = str(e)
        print_result("Error", str(e), False)
    
    return results


def main():
    """Main diagnostic routine."""
    print("\n" + "=" * 70)
    print("  OPINION.TRADE BALANCE DIAGNOSTIC TOOL")
    print("=" * 70)
    
    # Get configuration from environment
    print("\nReading configuration from .env file...")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    # Try both API_KEY and OPINION_API_KEY (different projects use different names)
    API_KEY = os.getenv('API_KEY') or os.getenv('OPINION_API_KEY', '')
    PRIVATE_KEY = os.getenv('PRIVATE_KEY', '')
    CHAIN_ID = int(os.getenv('CHAIN_ID', '56'))
    RPC_URL = os.getenv('RPC_URL', 'https://bsc-dataseed.binance.org/')
    MULTI_SIG_ADDRESS_RAW = os.getenv('MULTI_SIG_ADDRESS', '').strip()
    MULTI_SIG_ADDRESS = MULTI_SIG_ADDRESS_RAW if MULTI_SIG_ADDRESS_RAW else None
    
    # Validate required fields
    if not API_KEY:
        print("ERROR: Neither API_KEY nor OPINION_API_KEY is set in .env")
        print("\nYour .env file should have:")
        print("API_KEY=your_key_here")
        return 1
    
    if not PRIVATE_KEY:
        print("ERROR: PRIVATE_KEY not set in .env")
        return 1
    
    # Your addresses
    MAIN_WALLET = "0x707fE8Fa60365e3CA57C9c70Fca42c2829387D9A"
    SUB_WALLET = "0x756ac564686531dc82789c022f4216d2f553dca0"
    
    print_result("API Key", API_KEY[:20] + "..." if len(API_KEY) > 20 else API_KEY)
    print_result("Private Key", "***" + PRIVATE_KEY[-10:] if PRIVATE_KEY else "NOT SET")
    print_result("Chain ID", str(CHAIN_ID))
    print_result("RPC URL", RPC_URL)
    print_result("Multi-sig (current)", MULTI_SIG_ADDRESS if MULTI_SIG_ADDRESS else "NOT SET")
    
    # Store all test results
    all_results = []
    
    # =========================================================================
    # TEST 1: EOA mode (no multi-sig) - RECOMMENDED FOR NORMAL WALLETS
    # =========================================================================
    all_results.append(
        test_configuration(
            api_key=API_KEY,
            private_key=PRIVATE_KEY,
            chain_id=CHAIN_ID,
            rpc_url=RPC_URL,
            multi_sig_addr=None,
            description="EOA Mode (Address from Private Key) - RECOMMENDED"
        )
    )
    
    # =========================================================================
    # TEST 2: With main wallet as multi-sig (probably wrong but let's check)
    # =========================================================================
    all_results.append(
        test_configuration(
            api_key=API_KEY,
            private_key=PRIVATE_KEY,
            chain_id=CHAIN_ID,
            rpc_url=RPC_URL,
            multi_sig_addr=MAIN_WALLET,
            description=f"Multi-sig Mode with Main Wallet ({MAIN_WALLET})"
        )
    )
    
    # =========================================================================
    # TEST 3: With sub-wallet as multi-sig
    # =========================================================================
    all_results.append(
        test_configuration(
            api_key=API_KEY,
            private_key=PRIVATE_KEY,
            chain_id=CHAIN_ID,
            rpc_url=RPC_URL,
            multi_sig_addr=SUB_WALLET,
            description=f"Multi-sig Mode with Sub-wallet ({SUB_WALLET})"
        )
    )
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    print_section("TEST SUMMARY")
    
    successful_tests = [r for r in all_results if r['success']]
    tests_with_balance = [r for r in all_results if r['usdt_balance'] > 0]
    
    print(f"\n  Total tests: {len(all_results)}")
    print(f"  Successful API calls: {len(successful_tests)}")
    print(f"  Tests with USDT balance > 0: {len(tests_with_balance)}")
    
    print("\n  Results by test:")
    for i, result in enumerate(all_results, 1):
        status = "✓ SUCCESS" if result['success'] else "✗ FAILED"
        balance = f"{result['usdt_balance']:.6f} USDT" if result['usdt_balance'] > 0 else "0 USDT"
        error = f" - {result['error']}" if result['error'] else ""
        print(f"\n  Test {i}: {result['description']}")
        print(f"    Status: {status}{error}")
        print(f"    Balance: {balance}")
    
    # =========================================================================
    # RECOMMENDATIONS
    # =========================================================================
    print_section("RECOMMENDATIONS")
    
    if tests_with_balance:
        print("\n  ✓ Found USDT balance in following configuration(s):")
        for result in tests_with_balance:
            print(f"\n    • {result['description']}")
            print(f"      Balance: {result['usdt_balance']:.6f} USDT")
            
            # Provide specific .env configuration
            if 'Multi-sig Mode with Main Wallet' in result['description']:
                print(f"\n      .env configuration:")
                print(f"      MULTI_SIG_ADDRESS={MAIN_WALLET}")
            elif 'Multi-sig Mode with Sub-wallet' in result['description']:
                print(f"\n      .env configuration:")
                print(f"      MULTI_SIG_ADDRESS={SUB_WALLET}")
            else:  # EOA mode
                print(f"\n      .env configuration:")
                print(f"      MULTI_SIG_ADDRESS=")
                print(f"      (leave MULTI_SIG_ADDRESS empty or comment it out)")
    else:
        print("\n  ✗ No USDT balance found in any configuration!")
        print("\n  Possible issues:")
        print("    1. USDT not deposited to any of the tested addresses")
        print("    2. Wrong API key or private key")
        print("    3. USDT deposited to a different address entirely")
        print("    4. Need to wait for blockchain confirmation")
        
        print("\n  What to check:")
        print(f"    • Main wallet {MAIN_WALLET}")
        print(f"      Check on BscScan: https://bscscan.com/address/{MAIN_WALLET}")
        print(f"    • Sub-wallet {SUB_WALLET}")
        print(f"      Check on BscScan: https://bscscan.com/address/{SUB_WALLET}")
        print(f"    • Verify which address shows 11 USDT balance")
        print(f"    • If using Opinion.trade's deposit system, check deposit address in their UI")
    
    # Additional diagnostic info
    print_section("ADDITIONAL DIAGNOSTICS")
    
    print("\n  1. Check your USDT balance on BscScan:")
    print(f"     Main: https://bscscan.com/token/0x55d398326f99059fF775485246999027B3197955?a={MAIN_WALLET}")
    print(f"     Sub:  https://bscscan.com/token/0x55d398326f99059fF775485246999027B3197955?a={SUB_WALLET}")
    
    print("\n  2. Opinion.trade deposit address:")
    print("     Log into Opinion.trade and check 'Deposit' section")
    print("     The deposit address shown there is where you should send USDT")
    
    print("\n  3. API Key validation:")
    print(f"     Your API key was issued 'For EOA: {MAIN_WALLET.lower()}'")
    print("     This suggests you should use EOA mode (no MULTI_SIG_ADDRESS)")
    
    print("\n  4. Private key check:")
    print("     Verify your PRIVATE_KEY matches the wallet that has USDT")
    print("     (Never share your actual private key!)")
    
    print("\n" + "=" * 70)
    print()
    
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
