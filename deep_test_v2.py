import requests
import json

URL = "http://localhost:8000"

def test_compliance_trigger():
    print("\n--- TEST: Compliance Trigger Specificity ---")
    payload = {
        "now": "2026-10-27T10:00:00Z",
        "available_triggers": ["trg_002_compliance_dci_radiograph"]
    }
    r = requests.post(f"{URL}/v1/tick", json=payload)
    if r.status_code != 200:
        print(f"FAIL: Tick failed {r.status_code}: {r.text}")
        return
    actions = r.json().get("actions", [])
    if not actions:
        print("FAIL: No actions generated")
        return
    
    body = actions[0]["body"]
    print(f"Bot said: {body}")
    
    # Check for DCI and specific technical details
    if "DCI" in body or "Dental Council" in body:
        print("PASS: References DCI")
    else:
        print("FAIL: Generic message (missing DCI)")

def test_reply_merchant_xray():
    print("\n--- TEST: Merchant Reply (X-ray Audit) ---")
    payload = {
        "conversation_id": "conv_test_xray",
        "merchant_id": "m_001",
        "customer_id": None,
        "from_role": "merchant",
        "message": "Got it doc — need help auditing my X-ray setup. We have an old D-speed film unit.",
        "received_at": "2026-10-27T10:00:00Z",
        "turn_number": 2
    }
    r = requests.post(f"{URL}/v1/reply", json=payload)
    if r.status_code != 200:
        print(f"FAIL: Reply failed {r.status_code}: {r.text}")
        return
    res = r.json()
    print(f"Response: {res}")
    action = res.get("action")
    if action == "send":
        print("PASS: Correctly identified intent to SEND")
    else:
        print(f"FAIL: Incorrectly returned {action}")

def test_reply_customer_booking():
    print("\n--- TEST: Customer Reply (Booking Slot) ---")
    payload = {
        "conversation_id": "conv_test_booking",
        "merchant_id": "m_001",
        "customer_id": "c_001",
        "from_role": "customer",
        "message": "Yes please book me for Wed 5 Nov, 6pm.",
        "received_at": "2026-10-27T10:00:00Z",
        "turn_number": 2
    }
    r = requests.post(f"{URL}/v1/reply", json=payload)
    if r.status_code != 200:
        print(f"FAIL: Reply failed {r.status_code}: {r.text}")
        return
    res = r.json()
    print(f"Response: {res}")
    action = res.get("action")
    if action == "send":
        print("PASS: Correctly identified intent to SEND")
    else:
        print(f"FAIL: Incorrectly returned {action}")

if __name__ == "__main__":
    test_compliance_trigger()
    test_reply_merchant_xray()
    test_reply_customer_booking()
