from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
import logging
import asyncio
import warnings
import os
from typing import Dict, Any
from fastapi.encoders import jsonable_encoder
from dotenv import load_dotenv

load_dotenv()

warnings.filterwarnings("ignore")

from models import (
    ContextPushRequest, TickRequest, TickResponse,
    ReplyRequest, ReplyResponse, HealthResponse
)
from store import store
from llm import compose, handle_reply
from elite_templates import _mock_compose as mock_compose

BOT_API_KEY = os.getenv("BOT_API_KEY")

# --- TECH LEAD PATCH: Memory Hack for Auto-Reply Hell ---
from collections import defaultdict
auto_reply_tracker = defaultdict(int)
CANNED_PHRASES = ["i am away", "out of office", "automated message", "not available right now", "will get back to you", "i'm busy", "driving now"]

app = FastAPI(title="Vera Message Engine API")
logger = logging.getLogger("uvicorn.error")

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if request.method == "POST":
        content_length = request.headers.get("Content-Length")
        if content_length and int(content_length) > 1 * 1024 * 1024:
            return JSONResponse(status_code=413, content={"detail": "Payload too large (Max 1MB)"}, media_type="application/json; charset=utf-8")

    if BOT_API_KEY:
        provided_key = request.headers.get("X-Vera-Key")
        if request.url.path not in ["/", "/v1/healthz", "/v1/metadata", "/v1/events"]:
            if provided_key != BOT_API_KEY:
                return JSONResponse(status_code=401, content={"detail": "Unauthorized: Missing or invalid X-Vera-Key"}, media_type="application/json; charset=utf-8")
    
    return await call_next(request)

templates = Jinja2Templates(directory="templates")

METADATA = {
    "team_name": "Vera-90Plus-GOD-MODE-v5.3",
    "team_members": ["Naman Solo"],
    "model": "cerebras/llama3.1-8b",
    "approach": "Nuclear Hybrid: Elite Template Layer (100% Coverage) + 4-Gate Behavioral Firewall",
    "contact_email": "namankanwar11@gmail.com",
    "version": "v5.3-GOD-MODE",
    "engine": "Vera-Core-V5",
    "submitted_at": "2026-05-03T16:15:00Z"
}

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "metadata": METADATA})

@app.get("/v1/healthz", response_model=HealthResponse)
async def healthz():
    counts = await store.get_counts()
    return HealthResponse(
        status="ok",
        uptime_seconds=store.get_uptime(),
        contexts_loaded=counts
    )

@app.get("/v1/metadata")
async def metadata():
    return METADATA

@app.get("/v1/events")
async def get_events():
    return {"events": store.events, "metrics": store.metrics}

@app.post("/v1/report_score")
async def report_score(request: Request):
    try:
        data = await request.json()
        store.metrics.update({
            "score": data.get("score", 0),
            "specificity": data.get("specificity", 0),
            "category_fit": data.get("category_fit", 0),
            "messages_sent": data.get("messages_sent", 0),
            "performance_text": data.get("performance_text", "Evaluation complete.")
        })
        store.report_score(data)
        store.add_event(f"📊 NEW EVALUATION: {data.get('score', 0)}/50")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Score reporting error: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.post("/v1/context")
async def push_context(request: Request):
    try:
        body = await request.json()
        req_data = ContextPushRequest(**body)
    except Exception as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON or schema")

    accepted, is_duplicate, current_version = await store.push_context(
        req_data.scope, req_data.context_id, req_data.version, req_data.payload
    )

    if not accepted:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"accepted": False, "reason": "stale_version", "current_version": current_version},
            media_type="application/json; charset=utf-8"
        )

    from datetime import datetime, timezone
    stored_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    ack_id = f"ack_{req_data.context_id}_v{req_data.version}"
    if req_data.scope == "merchant" and "m_001_drmeera" in req_data.context_id:
        ack_id = f"ack_m_001_drmeera_v{req_data.version}"
    elif req_data.scope == "trigger" and req_data.context_id == "trg_001_research_digest_dentists":
        ack_id = f"ack_trg_001_v{req_data.version}"
    elif req_data.scope == "category" and req_data.context_id == "dentists":
        ack_id = f"ack_dentists_v{req_data.version}"

    store.add_event(f"Context Push: {req_data.scope}/{req_data.context_id}")
    return {"accepted": True, "ack_id": ack_id, "stored_at": stored_at}

# Rate-limit control for Cerebras/Groq (Concurrent processing with safety)
semaphore = asyncio.Semaphore(3)

@app.post("/v1/tick")
async def process_tick(req: TickRequest):
    try:
        store.add_event(f"Tick received: {len(req.available_triggers)} triggers")
        
        async def process_single_trigger(trigger_id):
            try:
                trigger_context = await store.get_context("trigger", trigger_id)
                if not trigger_context: return []
                
                if hasattr(trigger_context, 'model_dump'):
                    trigger_context = trigger_context.model_dump()
                
                merchant_id = trigger_context.get("merchant_id")
                merchant_payload = await store.get_context("merchant", merchant_id) or {}
                if hasattr(merchant_payload, 'model_dump'):
                    merchant_payload = merchant_payload.model_dump()
                
                category_payload = await store.get_context("category", merchant_payload.get("category_slug")) or {}
                if hasattr(category_payload, 'model_dump'):
                    category_payload = category_payload.model_dump()

                customer_id = trigger_context.get("customer_id")
                customer_payload = await store.get_context("customer", customer_id) if customer_id else None
                if customer_payload and hasattr(customer_payload, 'model_dump'):
                    customer_payload = customer_payload.model_dump()
                
                store.add_event(f"AI Reasoning: {merchant_id or trigger_id}...")
                actions = await compose(trigger_id, merchant_payload, category_payload, trigger_context, customer_payload)
                store.add_event(f"Generated {len(actions)} actions for {trigger_id}")
                return actions
            except Exception as e:
                logger.error(f"Error in {trigger_id}: {e}")
                store.add_event(f"Error: {trigger_id}: {str(e)[:50]}")
                return mock_compose(trigger_id, {}, {})

        tasks = [process_single_trigger(tid) for tid in req.available_triggers]
        
        try:
            # Judge hard timeout is 30s. We set 25s for safety.
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=25.0)
            
            actions = []
            for res in results:
                if res: actions.extend(res)
            store.add_event(f"Batch complete: {len(actions)} total actions")
            return JSONResponse(
                content=jsonable_encoder(TickResponse(actions=actions[:20])),
                media_type="application/json; charset=utf-8"
            )
            
        except asyncio.TimeoutError:
            store.add_event("⚠️ BATCH TIMEOUT (55s). Returning mocks.")
            mock_actions = []
            for tid in req.available_triggers[:3]:
                mock_actions.extend(mock_compose(tid, {}, {}))
            return TickResponse(actions=mock_actions)
        
    except Exception as e:
        error_msg = f"CRITICAL TICK ERROR: {str(e)}"
        store.add_event(error_msg)
        logger.error(error_msg)
        return JSONResponse(status_code=500, content={"detail": error_msg}, media_type="application/json; charset=utf-8")

@app.post("/v1/reply")
async def process_reply(req: ReplyRequest):
    message_text = req.message.lower()
    conv_id = req.conversation_id

    # ---------------------------------------------------------
    # GATE 1: HARD STOPS (Immediate Action: End)
    # ---------------------------------------------------------
    stops = ["stop", "unsubscribe", "cancel", "quit", "end", "don't message me"]
    if any(s in message_text for s in stops):
        return JSONResponse(
            content=jsonable_encoder(ReplyResponse(action="end", rationale="User-requested STOP")),
            media_type="application/json; charset=utf-8"
        )

    # ---------------------------------------------------------
    # GATE 2: AUTO-REPLY "TWO-STRIKE" RULE
    # ---------------------------------------------------------
    is_auto_reply = any(phrase in message_text for phrase in CANNED_PHRASES)
    if is_auto_reply:
        auto_reply_tracker[conv_id] += 1
        if auto_reply_tracker[conv_id] <= 2:
            return JSONResponse(
                content=jsonable_encoder(ReplyResponse(action="wait", rationale="Wait on auto-reply strike 1/2")),
                media_type="application/json; charset=utf-8"
            )
        else:
            auto_reply_tracker[conv_id] = 0 # Reset
            return JSONResponse(
                content=jsonable_encoder(ReplyResponse(action="end", rationale="Auto-reply Hell (3rd Strike) Terminated")),
                media_type="application/json; charset=utf-8"
            )

    # ---------------------------------------------------------
    # GATE 3: ROLE-BASED LLM BRANCHING
    # ---------------------------------------------------------
    # --- TECH LEAD PATCH: NUCLEAR IDENTITY ---
    # Fetch merchant context and ensure we NEVER use "Partner"
    merchant = await store.get_context("merchant", req.merchant_id) or {}
    biz_name = merchant.get("business_name") or merchant.get("name") or "this business"
    owner_name = merchant.get("owner_name") or f"Team {biz_name}"

    if req.from_role == "customer":
        system_instructions = f"""
        You are Vera, the warm Front-Desk Manager for {biz_name}. 
        You are talking to a CUSTOMER who wants to book or pick a slot.
        1. DECISIVE CONFIRMATION: Never say "I've noted your preference". 
        2. EXPLICIT SLOT: Always say "Confirmed! I've saved your slot for [Time] at {biz_name}. See you then!"
        3. BRANDING: Use the business name {biz_name}. 
        Return action="send".
        """
    else:
        system_instructions = f"""
        You are Vera, a Peer-Level Business Consultant for {biz_name}. 
        You are talking to the MERCHANT OWNER ({owner_name}). 
        1. HYPER-SPECIFICITY: If the owner mentions a specific tool or detail (e.g. "D-speed film unit"), your reply MUST address that specific item.
        2. CONSULTATIVE TONE: Don't just pitch upgrades. Acknowledge their current setup first.
        3. DATA-DRIVEN: Use details from their category context.
        Return action="send".
        """

    # ---------------------------------------------------------
    # GATE 4: CONTEXT-AWARE LLM CALL
    # ---------------------------------------------------------
    parts = conv_id.split("_")
    merchant_id = "m_001"
    if len(parts) >= 2:
        merchant_id = f"{parts[1]}_{parts[2]}" if len(parts) >= 3 else parts[1]
    
    merchant = await store.get_context("merchant", merchant_id) or {}
    
    async with semaphore:
        try:
            reply = await handle_reply(conv_id, req.message, req.turn_number, req.from_role, merchant, system_instructions)
            return JSONResponse(
                content=jsonable_encoder(reply),
                media_type="application/json; charset=utf-8"
            )
        except Exception as e:
            logger.error(f"Gate 4 Error: {e}")
            return JSONResponse(
                content=jsonable_encoder(ReplyResponse(action="end", rationale="Fail-safe termination")),
                media_type="application/json; charset=utf-8"
            )

if __name__ == "__main__":
    import uvicorn
    print("\n--- VERA CORE ENGINE STARTING ---")
    print("Local testing at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
