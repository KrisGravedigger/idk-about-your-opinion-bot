# debug_filled_order.py
from api_client import create_client
import json

client = create_client()
order_id = "2e436b27-dbee-11f0-9c8e-0a58a9feac02"  # Twój order_id

print("=" * 70)
print(f"Debugging order: {order_id}")
print("=" * 70)

order = client.get_order(order_id)

if order:
    print("\nFULL ORDER DATA:")
    print(json.dumps(order, indent=2, default=str))
    
    print("\n" + "=" * 70)
    print("KEY FIELDS:")
    print("=" * 70)
    print(f"status: {order.get('status')} (type: {type(order.get('status'))})")
    print(f"status_enum: {order.get('status_enum')}")
    print(f"filled_amount: {order.get('filled_amount')}")
    print(f"filled_shares: {order.get('filled_shares')}")
    print(f"price: {order.get('price')}")
    print(f"average_price: {order.get('average_price')}")
    
    print("\nALL KEYS:")
    print(list(order.keys()))
    
    print("\nTRADES (if any):")
    trades = order.get('trades', [])
    print(f"Number of trades: {len(trades)}")
    if trades:
        for i, trade in enumerate(trades):
            print(f"\nTrade {i+1}:")
            print(f"  shares: {trade.get('shares')}")
            print(f"  amount: {trade.get('amount')}")
            print(f"  price: {trade.get('price')}")
else:
    print("ERROR: Could not fetch order!")