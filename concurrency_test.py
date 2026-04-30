import asyncio
import httpx
import time

URL = "https://web-production-d3e66.up.railway.app/v1/tick"

async def hit_tick(client, idx):
    start = time.time()
    try:
        # Use a LONG trigger ID that we SAW in the live logs
        response = await client.post(URL, json={
            "now": "2026-04-30T10:00:00Z",
            "available_triggers": ["trg_019_chronic_refill_grandfather"]
        }, timeout=45.0)
        end = time.time()
        print(f"Request {idx} completed in {end - start:.2f}s with status {response.status_code}")
        return response.status_code
    except Exception as e:
        end = time.time()
        print(f"Request {idx} failed in {end - start:.2f}s: {e}")
        return str(e)

async def main():
    print(f"Starting ABSOLUTE Stress Test against {URL}...")
    print("Firing 5 concurrent LLM Reasoning calls...")
    async with httpx.AsyncClient() as client:
        tasks = [hit_tick(client, i) for i in range(5)]
        results = await asyncio.gather(*tasks)
    print("\n--- STRESS TEST SUMMARY ---")
    print(f"Total Requests: {len(results)}")
    print(f"Success Count: {results.count(200)}")
    print(f"Failed Count:  {len(results) - results.count(200)}")

if __name__ == "__main__":
    asyncio.run(main())
