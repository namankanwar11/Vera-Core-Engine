import requests
import json
from datetime import datetime

URL = "http://localhost:8000"

def test_extreme_triggers():
    print("\n" + "="*50)
    print("      EXTREME TRIGGER TEST (Hard Scenarios)      ")
    print("="*50)
    
    scenarios = [
        {
            "id": "trg_extreme_001_ayurvedic_recall",
            "desc": "DCGI Recall on niche Ayurvedic molecule (conflicting categories)",
            "payload": {"molecule": "Ashwagandha-Extract-X", "affected_batches": ["AX-99", "AX-101"], "manufacturer": "AyurCorp"}
        },
        {
            "id": "trg_extreme_002_fuel_spike_delivery",
            "desc": "Macro-Economic: Fuel spike affecting delivery-heavy restaurant",
            "payload": {"fuel_hike_pct": 0.12, "delivery_margin_impact": -0.05, "avg_delivery_dist_km": 4.2}
        },
        {
            "id": "trg_extreme_003_waste_management_audit",
            "desc": "Deep Regulation: New Biomedical Waste Rules 2026",
            "payload": {"rule_id": "BMW-2026-V2", "deadline": "2026-11-30", "fine_amount": 50000}
        }
    ]

    for s in scenarios:
        print(f"\n[SCENARIO] {s['desc']}")
        payload = {
            "now": datetime.utcnow().isoformat() + "Z",
            "available_triggers": [s['id']],
            "trigger_payload_override": s['payload'] # We'll handle this in main.py if needed
        }
        r = requests.post(f"{URL}/v1/tick", json=payload)
        actions = r.json().get("actions", [])
        if actions:
            print(f"Bot Response: \"{actions[0]['body']}\"")
            print(f"Decision Quality: {actions[0]['rationale']}")
        else:
            print("FAIL: No actions generated for extreme trigger.")

def test_extreme_replies():
    print("\n" + "="*50)
    print("      EXTREME REPLY TEST (Complex Intents)       ")
    print("="*50)

    replies = [
        {
            "role": "customer",
            "msg": "I'm interested in the cleaning but I heard your clinic has a lot of negative reviews about sanitation. Is it really safe?",
            "desc": "Skeptical Customer (Sanitation Concern)"
        },
        {
            "role": "merchant",
            "msg": "I want to match my competitor's 90% discount. Is that a good idea or will I lose money?",
            "desc": "Strategic Merchant (Price War Question)"
        },
        {
            "role": "customer",
            "msg": "Yes book me, but I'm traveling and my phone might be off. Can you email me the confirmation to test@example.com instead?",
            "desc": "Difficult Logistics (Multi-channel request)"
        }
    ]

    for r in replies:
        print(f"\n[REPLY TEST] {r['desc']}")
        payload = {
            "conversation_id": f"extreme_{r['role']}",
            "merchant_id": "m_001",
            "customer_id": "c_001" if r['role'] == 'customer' else None,
            "from_role": r['role'],
            "message": r['msg'],
            "received_at": datetime.utcnow().isoformat() + "Z",
            "turn_number": 3
        }
        resp = requests.post(f"{URL}/v1/reply", json=payload)
        res = resp.json()
        print(f"Bot Action: {res.get('action')}")
        print(f"Bot Body: {res.get('body')}")
        print(f"Rationale: {res.get('rationale')}")

if __name__ == "__main__":
    test_extreme_triggers()
    test_extreme_replies()
