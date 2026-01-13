#!/usr/bin/env python3
"""
Debug script to inspect get_order() API response structure
"""

import json
from api_client import create_client
from utils import load_state

def main():
    print("=" * 70)
    print("DEBUG: Order Status Structure Inspector")
    print("=" * 70)
    
    # Load state to get order_id
    state = load_state()
    if not state:
        print("ERROR: No state file found!")
        return
    
    order_id = state.get('order_id', '')
    if not order_id:
        print("ERROR: No order_id in state!")
        return
    
    print(f"\nInspecting order: {order_id}")
    print("=" * 70)
    
    # Create client
    client = create_client()
    
    # Get order
    order = client.get_order(order_id)
    
    print(f"\n1. ORDER OBJECT TYPE:")
    print(f"   type(order) = {type(order)}")
    
    print(f"\n2. ORDER OBJECT CONTENT:")
    if order:
        print(f"   {json.dumps(order, indent=2, default=str)}")
    else:
        print("   None")
    
    print(f"\n3. TOP-LEVEL KEYS:")
    if order and isinstance(order, dict):
        print(f"   Keys: {list(order.keys())}")
    
    print(f"\n4. STATUS FIELD:")
    if order and isinstance(order, dict):
        status = order.get('status')
        print(f"   order.get('status') = {repr(status)}")
        print(f"   Type: {type(status)}")
        
        # Check case variations
        for key in order.keys():
            if 'status' in key.lower():
                print(f"   Found status-like key: '{key}' = {order[key]}")
    
    print(f"\n5. OTHER POSSIBLY RELEVANT FIELDS:")
    if order and isinstance(order, dict):
        interesting_keys = ['state', 'order_status', 'filled', 'is_filled', 
                          'filled_amount', 'remaining_amount', 'executed']
        for key in interesting_keys:
            if key in order:
                print(f"   {key} = {order[key]}")
    
    print("\n" + "=" * 70)
    print("DEBUG COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
