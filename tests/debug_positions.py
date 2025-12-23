from api_client import create_client
import json

client = create_client()

print("=" * 70)
print("Fetching positions...")
print("=" * 70)

try:
    raw_client = client.get_raw_client()
    response = raw_client.get_my_positions()
    
    print(f"\nResponse type: {type(response)}")
    print(f"Response errno: {response.errno}")
    print(f"Response errmsg: {response.errmsg}")
    
    if hasattr(response, 'result'):
        print(f"\nResult type: {type(response.result)}")
        print(f"Result dir: {dir(response.result)}")
        
        if hasattr(response.result, 'model_dump'):
            print(f"\nResult model_dump():")
            print(json.dumps(response.result.model_dump(), indent=2, default=str))
    
    print("\n" + "=" * 70)
    print("Now trying via OpinionClient wrapper:")
    print("=" * 70)
    
    positions = client.get_positions()
    print(f"\nPositions count: {len(positions)}")
    
    if positions:
        print(f"\nFirst position:")
        print(json.dumps(positions[0], indent=2, default=str))
        
        # Look for market 2622
        for pos in positions:
            if pos.get('market_id') == 2622:
                print(f"\n\nFound position for market 2622:")
                print(json.dumps(pos, indent=2, default=str))
    
except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()