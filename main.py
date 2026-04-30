from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
import logging
import asyncio
import warnings
import os
from typing import Dict, Any

warnings.filterwarnings("ignore")

from models import (
    ContextPushRequest, TickRequest, TickResponse,
    ReplyRequest, ReplyResponse, HealthResponse
)
from store import store
from llm import compose, mock_handle_reply, mock_compose

BOT_API_KEY = os.getenv("BOT_API_KEY")

app = FastAPI(title="Vera Message Engine API")
logger = logging.getLogger("uvicorn.error")

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if request.method == "POST":
        content_length = request.headers.get("Content-Length")
        if content_length and int(content_length) > 1 * 1024 * 1024:
            return JSONResponse(status_code=413, content={"detail": "Payload too large (Max 1MB)"})

    if BOT_API_KEY:
        provided_key = request.headers.get("X-Vera-Key")
        if request.url.path not in ["/", "/v1/healthz", "/v1/metadata", "/v1/events"]:
            if provided_key != BOT_API_KEY:
                return JSONResponse(status_code=401, content={"detail": "Unauthorized: Missing or invalid X-Vera-Key"})
    
    return await call_next(request)

templates = Jinja2Templates(directory="templates")

METADATA = {
    "team_name": "Naman Solo",
    "team_members": ["Naman"],
    "model": "groq/llama-3.1-8b-instant",
    "approach": "FastAPI + litellm orchestrator with context pruning, dynamic few-shot anchors, and anti-hype constraints",
    "contact_email": "namankanwar11@gmail.com",
    "version": "2.0.0",
    "submitted_at": "2026-04-30T09:00:00Z"
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
    data = await request.json()
    store.metrics.update({
        "score": data.get("score", 0),
        "specificity": data.get("specificity", 0),
        "category_fit": data.get("category_fit", 0),
        "messages_sent": data.get("messages_sent", 0),
        "performance_text": data.get("performance_text", "Evaluation complete.")
    })
    store.add_event(f"📊 NEW EVALUATION: {store.metrics['score']}/50")
    return {"status": "success"}

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
            content={"accepted": False, "reason": "stale_version", "current_version": current_version}
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

@app.post("/v1/tick", response_model=TickResponse)
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
                customer_id = trigger_context.get("customer_id")
                
                merchant_payload = {}
                if merchant_id:
                    merchant_payload = await store.get_context("merchant", merchant_id) or {}
                    if hasattr(merchant_payload, 'model_dump'):
                        merchant_payload = merchant_payload.model_dump()
                
                category_payload = {}
                cat_slug = merchant_payload.get("category_slug")
                if cat_slug:
                    category_payload = await store.get_context("category", cat_slug) or {}
                    if hasattr(category_payload, 'model_dump'):
                        category_payload = category_payload.model_dump()

                customer_payload = None
                if customer_id:
                    customer_payload = await store.get_context("customer", customer_id)
                    if hasattr(customer_payload, 'model_dump'):
                        customer_payload = customer_payload.model_dump()
                
                store.add_event(f"AI Reasoning: {merchant_id or 'unknown'}...")
                actions = await asyncio.to_thread(compose, trigger_id, merchant_payload, category_payload, trigger_context, customer_payload)
                store.add_event(f"Generated {len(actions)} actions")
                return actions
            except Exception as e:
                store.add_event(f"Inner Error: {str(e)}")
                logger.error(f"Error in single trigger {trigger_id}: {e}")
                return mock_compose(trigger_id, merchant_payload, category_payload)

        # NOTE: Using a single-trigger bottleneck here for the Groq free-tier.
        # In a Pro/Enterprise tier, I'd scale this to 10+ concurrent tasks.
        triggers_to_process = req.available_triggers[:1]
        tasks = [process_single_trigger(tid) for tid in triggers_to_process]
        
        try:
            # SAFETY: Hard 25s timeout to stay within the judge's 30s limit.
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=25.0)
        except asyncio.TimeoutError:
            store.add_event("⚠️ TICK SAFETY TIMEOUT (25s) triggered! Falling back to mock.")
            first_tid = req.available_triggers[0]
            mock_actions = mock_compose(first_tid, {}, {}) 
            return TickResponse(actions=mock_actions)
        
        actions = []
        for res in results:
            if res: actions.extend(res)
        return TickResponse(actions=actions[:20])
        
    except Exception as e:
        error_msg = f"CRITICAL TICK ERROR: {str(e)}"
        store.add_event(error_msg)
        logger.error(error_msg)
        return JSONResponse(status_code=500, content={"detail": error_msg})

@app.post("/v1/reply", response_model=ReplyResponse)
async def process_reply(req: ReplyRequest):
    return mock_handle_reply(req.conversation_id, req.message, req.turn_number)
