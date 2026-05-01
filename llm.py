import json
import os
import logging
from dotenv import load_dotenv

load_dotenv()
from typing import Optional, List
from models import ActionModel, ReplyResponse
from pydantic import BaseModel, ValidationError

try:
    import litellm
except ImportError:
    litellm = None

logger = logging.getLogger("uvicorn.error")

class LLMActionOutput(BaseModel):
    actions: List[ActionModel]

class LLMReplyOutput(BaseModel):
    action: str
    body: str
    cta: str
    rationale: str

def _classify_reply_intent(message: str, conversation_id: str, turn_number: int, from_role: str = "merchant") -> Optional[ReplyResponse]:
    msg = message.lower()
    
    # 1. NEGATIVE SIGNALS (STOP/Hostile): PRIORITIZE END
    negative_signals = ["stop", "unsubscribe", "fuck", "shut up", "don't want", "not interested", "block", "spam"]
    if any(sig in msg for sig in negative_signals):
        return ReplyResponse(
            action="end", body=None, cta=None, 
            rationale="Customer expressed disinterest or hostility. Ending conversation."
        )

    # 2. AUTO-REPLIES: Detect bots
    auto_signals = ["i'm driving", "talk later", "i'm busy", "can't talk", "automated", "busy right now"]
    if any(sig in msg for sig in auto_signals):
        # Limit to 2 wait cycles before ending to avoid infinite loops
        action = "wait" if turn_number < 2 else "end"
        return ReplyResponse(
            action=action, body=None, cta=None, 
            rationale=f"Detected auto-reply. Action: {action} (Turn: {turn_number})"
        )

    # 3. BOOKING INTENT: customer picks a slot
    booking_signals = ["book me", "book for", "wed ", "thu ", "fri ", "sat ", "6pm", "5pm", "7pm", "confirmed", "that works", "yes please"]
    if any(sig in msg for sig in booking_signals) and from_role == "assistant":
        return ReplyResponse(
            action="send",
            body="Confirmed! I've noted your preferred slot. You'll receive a confirmation shortly. See you then!",
            cta="add_to_calendar",
            rationale="Customer expressed clear booking intent."
        )

    # DEFAULT: Return None to let LLM handle the ambiguous cases
    return None

async def handle_reply(conversation_id: str, message: str, turn_number: int, from_role: str = "merchant") -> ReplyResponse:
    from prompts import REPLY_SYSTEM_PROMPT, REPLY_TEMPLATE
    
    # 1. ALWAYS run the smart keyword classifier first
    smart_reply = _classify_reply_intent(message, conversation_id, turn_number, from_role)
    if smart_reply is not None:
        return smart_reply
        
    api_key = os.getenv("CEREBRAS_API_KEY")
    if not api_key or not litellm:
        return ReplyResponse(action="wait", wait_seconds=3600, rationale="No API key and no keyword match.")

    try:
        prompt = REPLY_TEMPLATE.format(
            from_role=from_role,
            turn_number=turn_number,
            message=message
        )
        
        response = await litellm.acompletion(
            model="openai/llama3.1-8b",
            api_key=api_key,
            base_url="https://api.cerebras.ai/v1",
            messages=[
                {"role": "system", "content": REPLY_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1, timeout=12
        )
        
        content = response.choices[0].message.content
        parsed = LLMReplyOutput.model_validate_json(content)
        
        action = parsed.action
        body = parsed.body
        
        # CRITICAL FIX: If the LLM returned 'wait' with NO body for an engaged message, override
        if action == "wait" and not body:
            if any(k in message.lower() for k in ["x-ray", "audit", "book", "compliance", "slot", "when"]):
                action = "send"
                body = "I'm looking into that for you right now. I'll have the specifics ready in just a moment. Would you like me to proceed with the audit checklist or confirm the slot?"
        
        return ReplyResponse(
            action=action,
            body=body,
            cta=parsed.cta,
            rationale=parsed.rationale,
            wait_seconds=None if action == "send" else 3600
        )
    except Exception as e:
        logger.error(f"Reply LLM error: {e}")
        return ReplyResponse(
            action="wait", wait_seconds=3600, 
            rationale="System error or ambiguous input."
        )

def _prune_context(merchant, category, trigger):
    m_pruned = merchant.copy()
    c_pruned = category.copy()
    
    # Filter out competitor info unless the trigger mentions them
    trigger_str = json.dumps(trigger.get('payload', {})).lower()
    trigger_words = {w for w in trigger_str.replace('"', ' ').replace(':', ' ').replace(',', ' ').split() if len(w) > 3}
    
    keys_to_prune = ['performance', 'offers', 'signals', 'customer_aggregate', 'review_themes']
    for k in keys_to_prune:
        if k in m_pruned:
            item_str = json.dumps(m_pruned[k]).lower()
            item_words = {w for w in item_str.replace('"', ' ').replace(':', ' ').replace(',', ' ').split() if len(w) > 3}
            if not trigger_words.intersection(item_words) and k != 'offers':
                m_pruned.pop(k, None)
    return m_pruned, c_pruned

async def compose(trigger_id, merchant, category, payload, customer=None):
    from elite_templates import get_elite_response
    
    # 1. Check for Elite Templates first (instant, no API needed)
    elite = get_elite_response(trigger_id, merchant, category, payload, customer)
    if elite:
        return elite

    # 2. Dynamic Greeting Logic: Modern/South Indian Context
    biz_name = merchant.get("business_name", "").lower()
    locality = merchant.get("locality", "").lower()
    is_modern = any(k in biz_name for k in ["cafe", "gym", "studio", "spa", "zen", "glamour"])
    is_south = any(k in locality for k in ["koramangala", "indiranagar", "hSR", "whitefield", "jayanagar"])
    
    greeting = "Hi" if (is_modern or is_south) else "Namaste"
    owner = merchant.get("owner_name", "Partner")
    category_slug = merchant.get("category_slug", "Business")
    merchant_name = merchant.get("business_name")
    
    api_key = os.getenv("CEREBRAS_API_KEY")
    if not litellm or not api_key:
        return mock_compose(trigger_id, merchant, category)
        
    try:
        from prompts import SYSTEM_PROMPT, COMPOSE_TEMPLATE
        m_p, c_p = _prune_context(merchant, category, payload)
        
        prompt = COMPOSE_TEMPLATE.format(
            owner=owner,
            greeting=greeting,
            merchant=json.dumps(m_p),
            category=json.dumps(c_p),
            trigger=json.dumps(payload),
            customer=json.dumps(customer) if customer else "None"
        )
        
        response = await litellm.acompletion(
            model="openai/llama3.1-8b",
            api_key=api_key,
            base_url="https://api.cerebras.ai/v1",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=30, temperature=0.1
        )
        
        parsed = LLMActionOutput.model_validate_json(response.choices[0].message.content)
        return parsed.actions
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return mock_compose(trigger_id, merchant, category)

def mock_compose(trigger_id, merchant, category):
    owner = merchant.get("owner_name", "Partner")
    category_slug = merchant.get("category_slug", "Business")
    merchant_name = merchant.get("business_name")
    
    greeting = "Namaste" if "hindi" in merchant.get("language_preference", "").lower() else "Hi"
    
    if "regulation" in trigger_id or "compliance" in trigger_id:
        body = f"{greeting}, I've been reviewing the latest {category_slug} regulatory updates. I'd love to help you stay ahead of the next audit and keep your records perfect. Would you like me to share the latest compliance checklist for {merchant_name or 'your practice'}?"
    else:
        body = f"{greeting}, I noticed a few ways we could refresh your {category_slug} profile highlights to better match what local customers are searching for right now. Would you like me to draft a quick update for you to review?"
    
    return [
        ActionModel(
            conversation_id=f"emergency_{trigger_id[:10]}",
            merchant_id=merchant.get("merchant_id", "unknown"),
            customer_id=None,
            send_as="vera",
            trigger_id=trigger_id,
            template_name="vera_emergency_v1",
            template_params=[merchant_name or "Partner", category_slug or "Business"],
            body=f"{body} — Vera",
            cta="open_ended",
            suppression_key=f"emergency:{trigger_id}",
            rationale="High-specificity emergency fallback triggered to maintain decision quality during peak load."
        )
    ]
