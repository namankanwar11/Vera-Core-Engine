import os
import sys
from dotenv import load_dotenv

# Add current dir to path
sys.path.append(os.getcwd())

from llm import handle_reply

load_dotenv()

def debug_reply():
    msg = "Got it doc — need help auditing my X-ray setup. We have an old D-speed film unit."
    try:
        resp = handle_reply("debug_conv", msg, 0, "merchant")
        print(f"Action: {resp.action}")
        print(f"Body: {resp.body}")
        print(f"Rationale: {resp.rationale}")
    except Exception as e:
        print(f"DIRECT ERROR: {e}")

if __name__ == "__main__":
    debug_reply()
