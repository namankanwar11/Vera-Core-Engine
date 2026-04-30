import asyncio
import httpx
import time

async def hit_tick(client, idx):
    start = time.time()
    try:
        response = await client.post("http://127.0.0.1:8080/v1/tick", json={
            "now": "2026-04-30T10:00:00Z",
            "available_triggers": ["trg_001", "trg_002"]
        }, timeout=15.0)
        end = time.time()
        print(f"Request {idx} completed in {end - start:.2f}s with status {response.status_code}")
        return response.status_code
    except Exception as e:
        end = time.time()
        print(f"Request {idx} failed in {end - start:.2f}s: {e}")
        return str(e)

async def main():
    print("Starting concurrency test (5 concurrent /v1/tick requests)...")
    async with httpx.AsyncClient() as client:
        tasks = [hit_tick(client, i) for i in range(5)]
        results = await asyncio.gather(*tasks)
    print("All requests finished.", results)

if __name__ == "__main__":
    asyncio.run(main())
