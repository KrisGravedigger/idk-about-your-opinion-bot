#!/usr/bin/env python3
"""
Quick config test - shows what values are actually loaded
"""

import sys
import os

# Import your config
try:
    from config import (
        API_KEY,
        PRIVATE_KEY,
        MULTI_SIG_ADDRESS,
        CHAIN_ID,
        RPC_URL
    )
except ImportError as e:
    print(f"ERROR importing config: {e}")
    sys.exit(1)

print("=" * 70)
print("  CONFIG VALUES TEST")
print("=" * 70)

def show_value(name, value):
    """Display a config value safely."""
    if value is None:
        display = "None (not set)"
        type_info = "NoneType"
    elif value == "":
        display = '""  (EMPTY STRING - THIS IS PROBLEM!)'
        type_info = "str"
    elif isinstance(value, str):
        # Show first/last few chars for keys
        if len(value) > 20:
            display = f'"{value[:10]}...{value[-6:]}"'
        else:
            display = f'"{value}"'
        type_info = "str"
    else:
        display = str(value)
        type_info = type(value).__name__
    
    print(f"\n{name}:")
    print(f"  Value: {display}")
    print(f"  Type: {type_info}")
    print(f"  Length: {len(str(value)) if value else 0}")
    print(f"  Boolean: {bool(value)}")

# Test each variable
show_value("API_KEY", API_KEY)
show_value("PRIVATE_KEY", PRIVATE_KEY)
show_value("MULTI_SIG_ADDRESS", MULTI_SIG_ADDRESS)
show_value("CHAIN_ID", CHAIN_ID)
show_value("RPC_URL", RPC_URL)

print("\n" + "=" * 70)
print("  DIAGNOSIS")
print("=" * 70)

# Check for common issues
issues = []

if API_KEY is None or API_KEY == "":
    issues.append("❌ API_KEY is empty or None")
elif not API_KEY.startswith("sdk-"):
    issues.append(f"⚠️ API_KEY doesn't start with 'sdk-' (starts with: {API_KEY[:4]})")

if PRIVATE_KEY is None or PRIVATE_KEY == "":
    issues.append("❌ PRIVATE_KEY is empty or None")
elif not PRIVATE_KEY.startswith("0x"):
    issues.append("⚠️ PRIVATE_KEY doesn't start with '0x'")

if MULTI_SIG_ADDRESS == "":
    issues.append("❌ MULTI_SIG_ADDRESS is EMPTY STRING - should be None or valid address!")
    print("\n⚠️⚠️⚠️ FOUND THE PROBLEM! ⚠️⚠️⚠️")
    print("MULTI_SIG_ADDRESS is empty string '' instead of None")
    print("This causes SDK to fail with 'Unknown format' error")
    print("\nFIX: In config.py, change:")
    print("  MULTI_SIG_ADDRESS = os.getenv('MULTI_SIG_ADDRESS', '')")
    print("To:")
    print("  MULTI_SIG_ADDRESS = os.getenv('MULTI_SIG_ADDRESS') or None")
elif MULTI_SIG_ADDRESS is None:
    issues.append("⚠️ MULTI_SIG_ADDRESS is None - bot will run in READ-ONLY mode")
elif MULTI_SIG_ADDRESS and not MULTI_SIG_ADDRESS.startswith("0x"):
    issues.append(f"❌ MULTI_SIG_ADDRESS doesn't start with '0x': {MULTI_SIG_ADDRESS}")
elif MULTI_SIG_ADDRESS:
    print(f"\n✅ MULTI_SIG_ADDRESS looks OK: {MULTI_SIG_ADDRESS}")

if not RPC_URL or not RPC_URL.startswith("http"):
    issues.append("❌ RPC_URL is invalid")

if issues:
    print("\nIssues found:")
    for issue in issues:
        print(f"  {issue}")
else:
    print("\n✅ All config values look OK!")

print("\n" + "=" * 70)
