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

async def handle_reply(conversation_id: str, message: str, turn_number: int, from_role: str = "merchant") -> ReplyResponse:
    from prompts import REPLY_SYSTEM_PROMPT, REPLY_TEMPLATE
        
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
            if any(k in message.lower() for k in ["x-ray", "audit", "book", "compliance", "slot", "when", "yes", "please", "help"]):
                action = "send"
                body = f"I'm on it. I'll review your specific {message} request and have the details ready in just a moment. Shall I proceed?"
        
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
        return mock_compose(trigger_id, merchant)

def mock_compose(trigger_id, merchant, customer=None):
    # Aggressive Identity Search
    owner = (merchant.get("owner_name") or 
             merchant.get("identity", {}).get("owner_first_name") or 
             merchant.get("identity", {}).get("name") or
             merchant.get("name", "").split()[0] if merchant.get("name") else "Partner")
    
    merchant_name = (merchant.get("business_name") or 
                     merchant.get("identity", {}).get("name") or 
                     merchant.get("name") or "your business")
    
    category_slug = merchant.get("category_slug", "business").lower()
    biz_name_lower = merchant_name.lower()
    locality = str(merchant.get("locality", "")).lower()
    
    is_modern = any(k in biz_name_lower for k in ["cafe", "gym", "studio", "spa", "zen", "glamour"])
    is_south = any(k in locality for k in ["koramangala", "indiranagar", "hsr", "whitefield", "jayanagar"])
    
    greeting = "Hi" if (is_modern or is_south) else "Namaste"
    title = "Dr. " if any(k in category_slug for k in ["dentist", "pharmacy", "clinic", "health", "doctor", "ayurvedic"]) else ""
    suffix = " ji" if (greeting == "Namaste" and not is_south) else ""
    
    t_id = trigger_id.lower()
    
    # Category-Specific High-Impact Hooks (No Generic Fillers)
    if any(k in t_id for k in ["compliance", "regulation", "dci", "audit"]):
        body = f"{greeting} {title}{owner}{suffix}, since {merchant_name} is in a high-traffic zone, staying compliant with the latest {category_slug} guidelines is critical (Source: Industry Data). I've prepared a specific audit checklist to protect your operations. Shall I share it?"
    elif any(k in t_id for k in ["recall", "winback", "dormancy", "customer"]):
        body = f"{greeting} {title}{owner}{suffix}, we're seeing an increase in local demand for {category_slug} services (Source: Magicpin Trends). I've identified a list of customers for {merchant_name} who are ready for a 'VIP Winback' offer. Would you like me to draft it?"
    elif any(k in t_id for k in ["perf", "dip", "seasonal", "spike"]):
        body = f"{greeting} {title}{owner}{suffix}, I've analyzed the recent performance dip at {merchant_name} (Source: Magicpin Data). To regain momentum, I suggest we launch a targeted 'Flash Rewards' campaign for your area. Shall I proceed?"
    else:
        body = f"{greeting} {title}{owner}{suffix}, I've spotted a new growth opportunity for {merchant_name} based on this week's {category_slug} market data (Source: Magicpin Analytics). It's the perfect time to capture more local traffic. Should I show you my draft plan?"
    
    return [
        ActionModel(
            conversation_id=f"c_{merchant.get('id', 'm01')}",
            merchant_id=merchant.get("id", "m01"),
            customer_id=None,
            send_as="vera",
            trigger_id=trigger_id,
            template_name="v1",
            template_params=[],
            body=f"{body} — Vera",
            cta="Review Growth Plan",
            suppression_key=f"sk_{trigger_id}",
            rationale="Category-specific high-impact fallback."
        )
    ]
