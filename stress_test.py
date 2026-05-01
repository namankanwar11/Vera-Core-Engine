import asyncio
import httpx
import time
import json
from datetime import datetime

BOT_URL = "http://localhost:8000" # Test locally first

async def test_tick(client, i):
    payload = {
        "now": datetime.utcnow().isoformat() + "Z",
        "available_triggers": [
            "trg_001_research_digest_dentists",
            "trg_003_recall_due_priya",
            "trg_004_perf_dip_bharat"
        ]
    }
    try:
        start = time.time()
        resp = await client.post(f"{BOT_URL}/v1/tick", json=payload, timeout=60)
        latency = time.time() - start
        print(f"[Tick {i}] {resp.status_code} in {latency:.2f}s | {len(resp.json().get('actions', []))} actions")
    except Exception as e:
        print(f"[Tick {i}] FAILED: {e}")

async def test_reply(client, i):
    payload = {
        "conversation_id": f"conv_stress_{i}",
        "message": "Yes please book me for Wed 5 Nov, 6pm. I need help auditing my X-ray setup.",
        "turn_number": 2
    }
    try:
        start = time.time()
        resp = await client.post(f"{BOT_URL}/v1/reply", json=payload, timeout=20)
        latency = time.time() - start
        action = resp.json().get('action')
        print(f"[Reply {i}] {resp.status_code} in {latency:.2f}s | action={action}")
    except Exception as e:
        print(f"[Reply {i}] FAILED: {e}")

async def run_stress_test(concurrency=20):
    print(f"--- Starting Stress Test (Concurrency={concurrency}) ---")
    async with httpx.AsyncClient() as client:
        # Test Tick
        tick_tasks = [test_tick(client, i) for i in range(concurrency)]
        await asyncio.gather(*tick_tasks)
        
        print("\n--- Starting Reply Stress Test ---")
        # Test Reply
        reply_tasks = [test_reply(client, i) for i in range(concurrency)]
        await asyncio.gather(*reply_tasks)

if __name__ == "__main__":
    asyncio.run(run_stress_test(20))
