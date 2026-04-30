# Vera Message Engine

**Vera** is an elite AI growth assistant for local merchants, built for the magicpin AI Challenge. It orchestrates high-quality, context-grounded merchant and customer communication using LLM-powered message composition over a FastAPI backbone.

---

## Elite-Level Orchestration

Vera is designed to survive the "Grand Final" 60-minute stress test with a focus on three senior-level engineering pillars:

1. **Sub-Second Latency**: Leveraging **Groq's LPU inference** and **LiteLLM**, Vera generates high-quality, grounded responses with sub-second time-to-first-token.
2. **Concurrent Ticking**: Using `asyncio.gather`, Vera processes up to 20 triggers in parallel, ensuring the system stays well under the 30-second judge timeout even under peak load.
3. **API Resilience**: Implemented exponential backoff (1s → 2s → 4s) to handle transient `429 Rate Limit` errors from LLM providers, ensuring zero-fail delivery.

---

## Architecture

### Why FastAPI?

We chose **FastAPI** over heavier frameworks (Django, Flask) for three reasons:

1. **Native async**: FastAPI is built on Starlette and runs on `uvicorn`, giving us true async I/O without third-party plugins. Every endpoint (`/v1/tick`, `/v1/context`, `/v1/reply`) is an `async def`, which means the event loop never blocks while waiting for LLM responses or state locks.
2. **Pydantic V2 validation at the boundary**: Every incoming payload is validated against strict Pydantic models *before* it reaches business logic. Malformed JSON from the judge harness bounces with a clean `422` instead of causing an obscure crash three layers deep.
3. **Zero-config OpenAPI**: FastAPI auto-generates Swagger docs at `/docs`, which made manual `curl` testing against the `api-call-examples.md` contract trivial during development.

### The 20-Action Cap & Concurrency Strategy

The challenge enforces a **20-action maximum per tick** and a **30-second timeout**. Processing triggers sequentially (one LLM call after another) would exceed this timeout.

**Solution:** We use `asyncio.to_thread()` + `asyncio.gather()` to fire all LLM composition calls in parallel:

```python
async def process_single_trigger(trigger_id):
    # ... resolve merchant + category from store ...
    return await asyncio.to_thread(compose, trigger_id, merchant, category, trigger)

tasks = [process_single_trigger(tid) for tid in triggers]
results = await asyncio.gather(*tasks)
actions = [a for result in results for a in result][:20]  # hard cap
```

This ensures that even with 20 triggers, all LLM calls execute concurrently and return well within the 30-second window.

### Idempotency on `/v1/context`

The judge harness may re-send the same `(scope, context_id, version)` tuple. Our `MemoryStateStore` handles this atomically:

| Condition | HTTP Response | Behavior |
|---|---|---|
| `incoming_version > stored_version` | `200 OK` | Accept and overwrite |
| `incoming_version == stored_version` | `200 OK` | No-op (idempotent) |
| `incoming_version < stored_version` | `409 Conflict` | Reject as stale |

All operations are guarded by `asyncio.Lock` to prevent race conditions in the single-worker deployment.

### LLM Orchestration

| Feature | Implementation |
|---|---|
| **Provider** | Groq (`llama-3.1-8b-instant`) via `litellm` |
| **Context Pruning** | Signal-to-noise filter strips irrelevant merchant fields before injection |
| **Few-Shot Anchors** | Category-specific gold-standard examples injected into the system prompt |
| **Anti-Hype Filter** | Negative constraints suppress exclamation marks, marketing buzzwords |
| **Rate Limit Handling** | Exponential backoff retry (1s → 2s → 4s) on `429` errors |
| **Fallback** | Graceful degradation to deterministic mock responses on LLM failure |

### State Management

We use an in-memory `MemoryStateStore` with `asyncio.Lock` instead of Redis/PostgreSQL because:
- The challenge runs on a **single worker** (`--workers 1`), so in-memory state is consistent.
- No external dependencies to install or configure.
- O(1) read/write with atomic locking.

---

## Running the Project

### Prerequisites
```bash
pip install fastapi uvicorn pydantic litellm python-dotenv
```

### 1. Configure `.env`
```env
GROQ_API_KEY="gsk_your_key_here"
DEFAULT_MODEL="groq/llama-3.1-8b-instant"
USE_MOCK_LLM="false"
```
Set `USE_MOCK_LLM="true"` for structural testing without LLM costs.

### 2. Expand the Dataset
```bash
python dataset/generate_dataset.py --seed-dir dataset --out expanded
```
Generates 50 merchants, 200 customers, 100 triggers, and 30 canonical test pairs.

### 3. Start the Server (TERMINAL 1)
Run this command to start your bot. Keep this window open.
```bash
python -m uvicorn vera_engine.main:app --port 8080 --workers 1
```

### 4. Run the Judge Simulator (TERMINAL 2)
Open a **new, second terminal window** to run the evaluation suite.
```powershell
$env:PYTHONIOENCODING="utf-8"
python judge_simulator.py
```

### 5. Verify Concurrency
```bash
python concurrency_test.py
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/healthz` | Health check with uptime and context counts |
| `GET` | `/v1/metadata` | Team info, model, and approach |
| `POST` | `/v1/context` | Ingest category/merchant/trigger/customer context |
| `POST` | `/v1/tick` | Process triggers and compose actions |
| `POST` | `/v1/reply` | Handle merchant replies with intent detection |

---

## Test Results

```
[PASS] warmup
[PASS] auto_reply      — 3-turn escalation: wait 4h → wait 24h → end
[PASS] intent          — "lets do it" → switched to ACTION mode
[PASS] hostile         — "stop messaging me" → ended conversation
Exit code: 0
```

---

## Production Hardening

### Cross-Platform Encoding Safety
During testing, we discovered that Python's surrogate pair escapes (e.g., `\ud83e\uddb7` for 🦷) cause `UnicodeEncodeError` on Windows when serialized through Starlette's JSON response encoder. We replaced all surrogate escapes with their actual Unicode characters, ensuring JSON payload integrity across Linux, macOS, and Windows — the kind of "boring but critical" fix that prevents a crash at minute 58 of a 60-minute evaluation.

### Compose Logic: Merchant Metrics First
The `compose()` function prioritizes **merchant-specific performance data** (views, calls, CTR, active offers) over generic greetings. Before the LLM prompt is assembled:
1. The **context pruner** strips fields that have zero lexical overlap with the current trigger, reducing noise.
2. **Category-specific few-shot anchors** are injected to shape the output toward the gold-standard examples from the case studies.
3. **Negative constraints** enforce a clinical, utility-first tone — no exclamation marks, no "Exciting!" or "Hurry!".

This ensures the LLM grounds every message in real merchant data rather than producing generic marketing copy.

### Rate Limit Resilience
The engine implements exponential backoff (`1s → 2s → 4s`) on `429 Too Many Requests` from Groq. After 3 failed retries, it gracefully degrades to deterministic mock responses — guaranteeing the bot never returns an empty `actions[]` array to the judge, even under heavy API throttling.

---

## Trade-offs

| Decision | Rationale |
|---|---|
| **In-memory store vs Redis** | Simpler deployment, no external deps. Trade-off: state lost on restart. |
| **`--workers 1`** | Required for in-memory state consistency. Horizontal scaling would need Redis. |
| **Mock fallback on LLM failure** | Guarantees the bot never returns an empty `actions[]` array to the judge, even if the LLM is down. |
| **Trigger cap per tick** | Limits concurrent LLM calls to avoid TPM exhaustion on free-tier providers. |
| **Rate Limit Strategy** | Custom exponential backoff wrapper for LiteLLM ensures resilience under heavy evaluation load without failing silently. |

---

## Post-Mortem: Concurrency & Performance

One of the primary technical hurdles was the **30-second timeout** for the `/v1/tick` endpoint when processing up to 20 triggers. 

**The Challenge:** Sequential processing of LLM calls resulted in latencies exceeding 40 seconds on average-parameter models. 
**The Solution:** We migrated from a synchronous loop to an `asyncio.gather` pattern. By wrapping the synchronous `compose` function in `asyncio.to_thread`, we achieved near-perfect horizontal scaling within the single-worker environment. This reduced our peak tick latency from **40s+** down to **~12s** (including the network RTT for 20 parallel Groq calls). 

This architecture proves that a Python-based AI agent can handle high-density data injection without sacrificing structural deterministic behavior or meeting strict API contract deadlines.
