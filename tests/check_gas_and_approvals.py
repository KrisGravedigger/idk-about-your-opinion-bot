#!/usr/bin/env python3
"""
Opinion.trade Gas & Approval Checker
=====================================

Checks:
1. BNB balance (for gas) on main wallet and subwallet
2. USDT approval status for Opinion.trade contracts
3. Diagnoses why order placement might be failing
"""

import sys
import os
from web3 import Web3

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Configuration
MAIN_WALLET = "0x707fE8Fa60365e3CA57C9c70Fca42c2829387D9A"
SUB_WALLET = "0x756ac564686531dc82789c022f4216d2f553dca0"
USDT_CONTRACT = "0x55d398326f99059fF775485246999027B3197955"
OPINION_CONDITIONAL_TOKEN = "0xAD1a38cEc043e70E83a3eC30443dB285ED10D774"

RPC_URL = os.getenv('RPC_URL', 'https://bsc-dataseed.binance.org/')

# ERC20 ABI (just allowance and balanceOf)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]


def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def check_bnb_balance(w3, address, name):
    """Check BNB balance."""
    try:
        balance_wei = w3.eth.get_balance(address)
        balance_bnb = w3.from_wei(balance_wei, 'ether')
        
        print(f"\n{name}:")
        print(f"  Address: {address}")
        print(f"  BNB Balance: {balance_bnb:.6f} BNB")
        
        if balance_bnb == 0:
            print(f"  ⚠️ WARNING: No BNB for gas fees!")
            print(f"  You need at least 0.001 BNB (~$0.60) for transaction gas")
            return False
        elif balance_bnb < 0.001:
            print(f"  ⚠️ WARNING: Very low BNB ({balance_bnb:.6f})")
            print(f"  Recommended: at least 0.001 BNB for gas")
            return False
        else:
            print(f"  ✓ Sufficient BNB for gas")
            return True
            
    except Exception as e:
        print(f"  ✗ Error checking BNB: {e}")
        return False


def check_usdt_balance(w3, usdt_contract, address, name):
    """Check USDT balance."""
    try:
        balance_raw = usdt_contract.functions.balanceOf(address).call()
        balance_usdt = balance_raw / 1e18  # USDT has 18 decimals
        
        print(f"\n{name} USDT:")
        print(f"  Balance: {balance_usdt:.2f} USDT")
        
        if balance_usdt > 0:
            print(f"  ✓ Has USDT")
        else:
            print(f"  ✗ No USDT on this address")
        
        return balance_usdt
        
    except Exception as e:
        print(f"  ✗ Error checking USDT: {e}")
        return 0


def check_usdt_approval(w3, usdt_contract, owner, spender, spender_name):
    """Check USDT approval."""
    try:
        allowance = usdt_contract.functions.allowance(owner, spender).call()
        allowance_usdt = allowance / 1e18
        
        print(f"\n{spender_name}:")
        print(f"  Spender: {spender}")
        print(f"  Allowance: {allowance_usdt:.2f} USDT")
        
        if allowance == 0:
            print(f"  ✗ NOT APPROVED - This is likely the problem!")
            print(f"  Solution: Approve USDT spending via Opinion.trade UI")
            return False
        elif allowance_usdt < 100:
            print(f"  ⚠️ Low allowance ({allowance_usdt:.2f} USDT)")
            return True
        else:
            print(f"  ✓ Approved (sufficient allowance)")
            return True
            
    except Exception as e:
        print(f"  ✗ Error checking approval: {e}")
        return False


def main():
    """Main diagnostic routine."""
    print_section("OPINION.TRADE GAS & APPROVAL CHECKER")
    
    print("\nChecking blockchain state on BSC...")
    
    # Connect to BSC
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            print("✗ Failed to connect to BSC RPC")
            return 1
        print(f"✓ Connected to BSC (Chain ID: {w3.eth.chain_id})")
    except Exception as e:
        print(f"✗ Error connecting to RPC: {e}")
        return 1
    
    # Create USDT contract
    try:
        usdt_contract = w3.eth.contract(
            address=Web3.to_checksum_address(USDT_CONTRACT),
            abi=ERC20_ABI
        )
    except Exception as e:
        print(f"✗ Error creating USDT contract: {e}")
        return 1
    
    # =========================================================================
    # CHECK 1: BNB BALANCES (GAS)
    # =========================================================================
    print_section("CHECK 1: BNB BALANCE (FOR GAS)")
    
    main_has_gas = check_bnb_balance(w3, MAIN_WALLET, "Main Wallet")
    sub_has_gas = check_bnb_balance(w3, SUB_WALLET, "Sub-wallet")
    
    # =========================================================================
    # CHECK 2: USDT BALANCES
    # =========================================================================
    print_section("CHECK 2: USDT BALANCES")
    
    main_usdt = check_usdt_balance(w3, usdt_contract, MAIN_WALLET, "Main Wallet")
    sub_usdt = check_usdt_balance(w3, usdt_contract, SUB_WALLET, "Sub-wallet")
    
    # =========================================================================
    # CHECK 3: USDT APPROVALS
    # =========================================================================
    print_section("CHECK 3: USDT APPROVALS")
    
    print("\nChecking if USDT is approved for Opinion.trade contracts...")
    
    # Check approval from main wallet
    print(f"\nFrom Main Wallet ({MAIN_WALLET}):")
    main_approved = check_usdt_approval(
        w3, usdt_contract,
        MAIN_WALLET,
        OPINION_CONDITIONAL_TOKEN,
        "Opinion ConditionalToken Contract"
    )
    
    # Check approval from subwallet
    print(f"\n\nFrom Sub-wallet ({SUB_WALLET}):")
    sub_approved = check_usdt_approval(
        w3, usdt_contract,
        SUB_WALLET,
        OPINION_CONDITIONAL_TOKEN,
        "Opinion ConditionalToken Contract"
    )
    
    # =========================================================================
    # DIAGNOSIS
    # =========================================================================
    print_section("DIAGNOSIS")
    
    issues = []
    
    if not main_has_gas and not sub_has_gas:
        issues.append("❌ CRITICAL: No BNB for gas on either wallet!")
        issues.append("   Solution: Send at least 0.001 BNB to main wallet (0x707f...)")
    elif not main_has_gas:
        issues.append("⚠️ Main wallet has no BNB for gas")
        issues.append("   Opinion.trade might handle gas differently, but this could be an issue")
    
    if main_usdt == 0 and sub_usdt == 0:
        issues.append("❌ No USDT found on either address")
        issues.append("   But API showed 11 USDT - check if USDT is locked in contract")
    elif sub_usdt > 0:
        issues.append(f"✓ Found {sub_usdt:.2f} USDT on sub-wallet")
    
    if not main_approved and not sub_approved:
        issues.append("❌ CRITICAL: USDT not approved for Opinion.trade!")
        issues.append("   This is LIKELY the main problem!")
        issues.append("   Solution: Go to Opinion.trade UI and approve USDT spending")
    elif not sub_approved:
        issues.append("⚠️ Sub-wallet USDT not approved (might be needed)")
    
    if not issues:
        issues.append("✓ All checks passed!")
        issues.append("  If order still fails, check:")
        issues.append("  - Network congestion")
        issues.append("  - RPC node issues")
        issues.append("  - Opinion.trade system status")
    
    print("\nIssues found:")
    for issue in issues:
        print(f"  {issue}")
    
    # =========================================================================
    # RECOMMENDATIONS
    # =========================================================================
    print_section("RECOMMENDATIONS")
    
    if not main_has_gas:
        print("\n1. ADD BNB FOR GAS:")
        print(f"   Send 0.001-0.01 BNB to: {MAIN_WALLET}")
        print(f"   This covers gas fees for transactions")
        print(f"   Current BNB price ~$600, so 0.001 BNB = ~$0.60")
    
    if not main_approved or not sub_approved:
        print("\n2. APPROVE USDT SPENDING:")
        print(f"   Go to: https://opinion.trade")
        print(f"   Connect your wallet ({MAIN_WALLET})")
        print(f"   Try to place an order - it will prompt for USDT approval")
        print(f"   Approve the transaction (costs small gas fee)")
        print(f"   Then bot should work!")
    
    if main_usdt == 0 and sub_usdt == 0 and issues:
        print("\n3. CHECK USDT LOCATION:")
        print(f"   Main wallet: https://bscscan.com/address/{MAIN_WALLET}")
        print(f"   Sub-wallet: https://bscscan.com/address/{SUB_WALLET}")
        print(f"   Verify where your 11 USDT actually is")
    
    print("\n" + "=" * 70)
    
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
