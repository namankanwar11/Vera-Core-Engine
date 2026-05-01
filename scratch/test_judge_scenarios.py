import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BOT_API_KEY")
URL = "http://localhost:8000/v1/reply"

def test_reply(message, from_role="merchant", turn_number=0):
    payload = {
        "conversation_id": "test_conv",
        "merchant_id": "m_001",
        "from_role": from_role,
        "message": message,
        "received_at": "2026-05-01T12:00:00Z",
        "turn_number": turn_number
    }
    headers = {"X-Vera-Key": API_KEY} if API_KEY else {}
    
    print(f"\n[TESTING] Role: {from_role} | Msg: '{message}'")
    try:
        resp = requests.post(URL, json=payload, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            print(f"Action: {data.get('action')}")
            print(f"Body: {data.get('body')}")
            print(f"Rationale: {data.get('rationale')}")
        else:
            print(f"Error: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    # Test 1: Technical Merchant Question (Should NOT be generic "Absolutely!")
    test_reply("Got it doc — need help auditing my X-ray setup. We have an old D-speed film unit.", from_role="merchant")
    
    # Test 2: Clear Booking Pick (Should be 'send' with confirmation)
    test_reply("Yes please book me for Wed 5 Nov, 6pm.", from_role="assistant")
    
    # Test 3: STOP command (Should be 'end')
    test_reply("STOP", from_role="merchant")
    
    # Test 4: Hostile message (Should be 'end')
    test_reply("Fuck off I don't want this", from_role="merchant")
    
    # Test 5: Auto-reply Turn 1 (Wait)
    test_reply("I'm driving, talk later", from_role="merchant", turn_number=1)
    
    # Test 6: Auto-reply Turn 3 (Should be 'end')
    test_reply("I'm driving, talk later", from_role="merchant", turn_number=3)
