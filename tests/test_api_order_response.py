"""
Test diagnostyczny API - sprawdza co zwraca get_order()

Ten skrypt:
1. Pobiera szczegóły order przez API
2. Wypisuje CAŁĄ odpowiedź w czytelnym formacie
3. Pokazuje jakie pola są dostępne i ich wartości
4. Pomaga zdiagnozować dlaczego filled_amount = 0

Użycie:
    python test_api_order_response.py <order_id>
    
Przykład:
    python test_api_order_response.py fce93d4d-df90-11f0-9d12-0a58a9feac02
"""

import sys
import json
from api_client import create_client

def print_dict_recursive(d, indent=0, max_depth=10):
    """Wypisuje dict rekurencyjnie w czytelnym formacie"""
    if indent > max_depth:
        print("  " * indent + "... (max depth reached)")
        return
    
    for key, value in d.items():
        if isinstance(value, dict):
            print("  " * indent + f"{key}:")
            print_dict_recursive(value, indent + 1, max_depth)
        elif isinstance(value, list):
            print("  " * indent + f"{key}: [{len(value)} items]")
            if len(value) > 0 and len(value) <= 5:
                for i, item in enumerate(value):
                    print("  " * (indent + 1) + f"[{i}]:")
                    if isinstance(item, dict):
                        print_dict_recursive(item, indent + 2, max_depth)
                    else:
                        print("  " * (indent + 2) + str(item))
            elif len(value) > 5:
                print("  " * (indent + 1) + f"(showing first 2 of {len(value)} items)")
                for i in range(2):
                    print("  " * (indent + 1) + f"[{i}]:")
                    if isinstance(value[i], dict):
                        print_dict_recursive(value[i], indent + 2, max_depth)
                    else:
                        print("  " * (indent + 2) + str(value[i]))
        else:
            # Wyświetl typ dla lepszej diagnostyki
            type_name = type(value).__name__
            print("  " * indent + f"{key}: {value} ({type_name})")


def test_order_response(order_id: str):
    """
    Testuje odpowiedź API dla get_order()
    
    Args:
        order_id: ID zamówienia do sprawdzenia
    """
    print("=" * 80)
    print("TEST API ORDER RESPONSE")
    print("=" * 80)
    print()
    print(f"Order ID: {order_id}")
    print()
    
    # Utwórz klienta
    print("🔌 Łączenie z API...")
    try:
        client = create_client()
        print("✅ Połączono")
    except Exception as e:
        print(f"❌ Błąd połączenia: {e}")
        return
    
    print()
    print("📡 Pobieranie szczegółów order...")
    print()
    
    # Pobierz order
    try:
        order = client.get_order(order_id)
    except Exception as e:
        print(f"❌ Błąd API: {e}")
        import traceback
        traceback.print_exc()
        return
    
    if not order:
        print("❌ API zwróciło None - order nie znaleziony lub błąd")
        return
    
    print("✅ Otrzymano odpowiedź")
    print()
    print("=" * 80)
    print("STRUKTURA ODPOWIEDZI (rekurencyjna)")
    print("=" * 80)
    print()
    
    # Wypisz całą strukturę
    print_dict_recursive(order)
    
    print()
    print("=" * 80)
    print("KLUCZOWE POLA DLA FILL DATA")
    print("=" * 80)
    print()
    
    # Wypisz kluczowe pola
    key_fields = [
        'filled_shares',
        'filled_amount', 
        'price',
        'amount',
        'status',
        'status_enum',
        'trades',
        'executedQty',
        'avgPrice',
        'cumQuote',
        'fills'
    ]
    
    for field in key_fields:
        if field in order:
            value = order[field]
            type_name = type(value).__name__
            print(f"  ✅ {field}: {value} ({type_name})")
        else:
            print(f"  ❌ {field}: BRAK")
    
    print()
    print("=" * 80)
    print("ANALIZA TRADES (jeśli istnieją)")
    print("=" * 80)
    print()
    
    trades = order.get('trades', [])
    if trades:
        print(f"Znaleziono {len(trades)} trade(s)")
        print()
        
        for i, trade in enumerate(trades):
            print(f"Trade #{i+1}:")
            if isinstance(trade, dict):
                print_dict_recursive(trade, indent=1, max_depth=3)
            else:
                print(f"  (raw): {trade}")
            print()
    else:
        print("❌ Brak trades w odpowiedzi")
    
    print()
    print("=" * 80)
    print("PEŁNA ODPOWIEDŹ JSON")
    print("=" * 80)
    print()
    
    # Wypisz jako JSON dla łatwego kopiowania
    try:
        print(json.dumps(order, indent=2, default=str))
    except Exception as e:
        print(f"Nie można skonwertować do JSON: {e}")
        print()
        print("Raw output:")
        print(order)
    
    print()
    print("=" * 80)
    print("DIAGNOSTYKA")
    print("=" * 80)
    print()
    
    # Sprawdź co możemy użyć do obliczenia filled_amount
    filled_shares = order.get('filled_shares', 0)
    price = order.get('price', 0)
    amount = order.get('amount', 0)
    filled_amount_field = order.get('filled_amount', 0)
    
    print("Możliwości obliczenia filled_amount:")
    print()
    
    if filled_shares and price:
        calculated = float(filled_shares) * float(price)
        print(f"  ✅ Z filled_shares × price:")
        print(f"     {filled_shares} × {price} = {calculated:.4f} USDT")
        print()
    
    if filled_amount_field:
        print(f"  ✅ Bezpośrednio z filled_amount:")
        print(f"     {filled_amount_field}")
        print()
    
    if amount and price:
        calculated_shares = float(amount) / float(price)
        print(f"  ℹ️  Z amount ÷ price (jeśli order był BUY):")
        print(f"     {amount} ÷ {price} = {calculated_shares:.4f} tokens")
        print()
    
    if trades:
        total_shares = sum(float(t.get('shares', 0)) for t in trades if isinstance(t, dict))
        total_cost = sum(float(t.get('amount', 0)) for t in trades if isinstance(t, dict))
        print(f"  ✅ Z trades[]:")
        print(f"     Total shares: {total_shares:.4f}")
        print(f"     Total cost: {total_cost:.4f} USDT")
        if total_shares > 0:
            avg_price = total_cost / total_shares
            print(f"     Avg price: {avg_price:.4f}")
        print()
    
    if not any([filled_shares, filled_amount_field, trades]):
        print("  ❌ BRAK DANYCH - API nie zwraca żadnych pól potrzebnych do obliczenia!")
        print("     To wyjaśnia dlaczego filled_amount = 0 w state")
        print()
        print("  🔍 Możliwe przyczyny:")
        print("     1. Order jeszcze nie został filled (mimo status=Finished)")
        print("     2. API bug - nie zwraca pełnych danych")
        print("     3. Potrzeba dodatkowego API call żeby pobrać trades")
    
    print()
    print("=" * 80)
    print("KONIEC TESTU")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie: python test_api_order_response.py <order_id>")
        print()
        print("Przykład:")
        print("  python test_api_order_response.py fce93d4d-df90-11f0-9d12-0a58a9feac02")
        print()
        print("Order ID można znaleźć w:")
        print("  - state.json (current_position.order_id)")
        print("  - logach bota (✅ BUY order placed: ...)")
        sys.exit(1)
    
    order_id = sys.argv[1]
    test_order_response(order_id)