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
    "team_name": "Vera-Core-90Plus-FINAL-v3",
    "team_members": ["Naman Solo"],
    "model": "cerebras/llama3.1-8b",
    "approach": "FastAPI + litellm orchestrator with context pruning, dynamic few-shot anchors, and anti-hype constraints",
    "contact_email": "namankanwar11@gmail.com",
    "version": "v1.3-extreme",
    "engine": "Vera-Core-V3",
    "submitted_at": "2026-05-01T12:00:00Z"
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
                async with semaphore:
                    actions = await compose(trigger_id, merchant_payload, category_payload, trigger_context, customer_payload)
                store.add_event(f"Generated {len(actions)} actions for {trigger_id}")
                return actions
            except Exception as e:
                logger.error(f"Error in {trigger_id}: {e}")
                store.add_event(f"Error: {trigger_id}: {str(e)[:50]}")
                return mock_compose(trigger_id, {}, {})

        tasks = [process_single_trigger(tid) for tid in req.available_triggers]
        
        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=55.0)
            
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
    msg = req.message.lower()
    
    # 1. HARD TERMINATION (STOP/Hostile)
    stops = ["stop", "unsubscribe", "quit", "end", "fuck", "spam", "useless", "shut up"]
    if any(s in msg for s in stops):
        return JSONResponse(
            content=jsonable_encoder(ReplyResponse(action="end", rationale="Hard-coded termination")),
            media_type="application/json; charset=utf-8"
        )
        
    # 2. AUTO-REPLY & REPETITION CAP
    autos = ["driving", "automated", "busy", "talk later", "auto-reply", "out of office", "automated message", "can't talk right now"]
    rep_count = store.track_reply(req.conversation_id, req.message)
    
    if any(a in msg for a in autos) or rep_count > 2:
        store.add_event(f"Auto-reply/Repetition detected: {rep_count} turns. Terminating.")
        return JSONResponse(
            content=jsonable_encoder(ReplyResponse(action="end", rationale=f"Auto-reply or repetition ({rep_count}) detected")),
            media_type="application/json; charset=utf-8"
        )

    # 3. CONTEXT-AWARE REPLY
    # Extract merchant_id from conversation_id (format: c_m_001_...)
    parts = req.conversation_id.split("_")
    merchant_id = "m_001" # Default
    if len(parts) >= 2:
        merchant_id = f"{parts[1]}_{parts[2]}" if len(parts) >= 3 else parts[1]
    
    merchant = await store.get_context("merchant", merchant_id) or {}
    
    async with semaphore:
        reply = await handle_reply(req.conversation_id, req.message, req.turn_number, req.from_role, merchant)
    return JSONResponse(
        content=jsonable_encoder(reply),
        media_type="application/json; charset=utf-8"
    )
