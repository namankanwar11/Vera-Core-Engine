import sys
import os
sys.path.append(os.getcwd())
from elite_templates import get_elite_response

merchant = {"merchant_id": "m1", "name": "Test", "locality": "L"}
category = {"name": "C"}
trigger = {"parameters": {}}
res = get_elite_response("trg_027_inflation_fuel_price", merchant, category, trigger)
print(f"Result: {res}")
