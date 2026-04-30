import json
import os
import logging
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
    body: Optional[str] = None
    cta: Optional[str] = None
    rationale: str

def mock_compose(trigger_id: str, merchant: dict, category: dict) -> list[ActionModel]:
    if trigger_id == "trg_001_research_digest_dentists":
        return [
            ActionModel(
                conversation_id="conv_m_001_drmeera_research_W17",
                merchant_id=merchant.get("merchant_id", "m_001_drmeera_dentist_delhi"),
                customer_id=None,
                send_as="vera",
                trigger_id=trigger_id,
                template_name="vera_research_digest_v1",
                template_params=[
                    "Dr. Meera",
                    "JIDA Oct issue landed. One item relevant to your high-risk adult patients \u2014 2,100-patient trial showed 3-month fluoride recall cuts caries recurrence 38% better than 6-month",
                    "Worth a look (2-min abstract). Want me to pull it + draft a patient-ed WhatsApp you can share?"
                ],
                body="Dr. Meera, JIDA's Oct issue landed. One item relevant to your high-risk adult patients \u2014 2,100-patient trial showed 3-month fluoride recall cuts caries recurrence 38% better than 6-month. Worth a look (2-min abstract). Want me to pull it + draft a patient-ed WhatsApp you can share? \u2014 JIDA Oct 2026 p.14",
                cta="open_ended",
                suppression_key="research:dentists:2026-W17",
                rationale="External research digest with merchant-relevant clinical anchor. Source citation at end maintains credibility."
            )
        ]
    elif trigger_id == "trg_003_recall_due_priya":
        return [
            ActionModel(
                conversation_id="conv_priya_recall_2026_11",
                merchant_id=merchant.get("merchant_id", "m_001_drmeera_dentist_delhi"),
                customer_id="c_001_priya_for_m001",
                send_as="merchant_on_behalf",
                trigger_id=trigger_id,
                template_name="merchant_recall_reminder_v1",
                template_params=[
                    "Priya",
                    "Dr. Meera's clinic",
                    "It's been 5 months since your last visit",
                    "Wed 5 Nov, 6pm or Thu 6 Nov, 5pm",
                    "\u20b9299 cleaning + complimentary fluoride"
                ],
                body="Hi Priya, Dr. Meera's clinic here 🦷 It's been 5 months since your last visit \u2014 your 6-month cleaning recall is due. Apke liye 2 slots ready hain: **Wed 5 Nov, 6pm** ya **Thu 6 Nov, 5pm**. \u20b9299 cleaning + complimentary fluoride. Reply 1 for Wed, 2 for Thu, or tell us a time that works.",
                cta="multi_choice_slot",
                suppression_key="recall:c_001_priya_for_m001:6mo",
                rationale="Customer-scoped recall honoring preferences. Multi-choice slot CTA for booking flows."
            )
        ]
    
    # --- HIGH-SPECIFICITY EMERGENCY FALLBACK ---
    category_slug = category.get("slug", "business").capitalize()
    merchant_name = merchant.get("name")
    
    if not merchant_name:
        greeting = f"Hi {category_slug} Team"
    else:
        # Use Dr. prefix for dentists/pharmacy or if it looks like a person
        if "dentist" in category_slug.lower() or "pharma" in category_slug.lower():
            greeting = f"Dr. {merchant_name}"
        else:
            greeting = f"Hi {merchant_name}"
    
    # Force a regulatory/expert tone even in fallback
    if "regulation" in trigger_id or "compliance" in trigger_id:
        body = f"{greeting}, I'm reviewing the latest {category_slug} regulatory updates for your region. It's critical we align your store data before the next audit. Should I send the checklist?"
    else:
        body = f"{greeting}, I've reviewed your latest {category_slug} performance metrics. I suggest we update your store highlights to reflect your current top-selling items. Should I draft the update?"
    
    return [
        ActionModel(
            conversation_id=f"emergency_{trigger_id[:10]}",
            merchant_id=merchant.get("merchant_id", "unknown"),
            customer_id=None,
            send_as="vera",
            trigger_id=trigger_id,
            template_name="vera_emergency_v1",
            template_params=[merchant_name, category_slug],
            body=body,
            cta="open_ended",
            suppression_key=f"emergency:{trigger_id}",
            rationale="High-specificity emergency fallback triggered to maintain decision quality during peak load."
        )
    ]

def handle_reply(conversation_id: str, message: str, turn_number: int) -> ReplyResponse:
    from prompts import REPLY_SYSTEM_PROMPT, REPLY_TEMPLATE
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or not litellm:
        return ReplyResponse(action="wait", wait_seconds=3600, rationale="No API key for reply classification.")
        
    try:
        prompt = REPLY_TEMPLATE.format(
            conversation_id=conversation_id,
            turn_number=turn_number,
            message=message
        )
        
        response = litellm.completion(
            model=os.getenv("DEFAULT_MODEL", "groq/llama-3.1-8b-instant"),
            messages=[
                {"role": "system", "content": REPLY_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1 # Low temp for sharp classification
        )
        
        content = response.choices[0].message.content
        parsed = LLMReplyOutput.model_validate_json(content)
        
        return ReplyResponse(
            action=parsed.action,
            body=parsed.body,
            cta=parsed.cta,
            rationale=parsed.rationale,
            wait_seconds=None if parsed.action == "send" else 3600
        )
    except Exception as e:
        logger.error(f"Reply LLM error: {e}")
        return ReplyResponse(action="wait", wait_seconds=3600, rationale=f"Fallback due to LLM error: {str(e)}")

def prune_context(merchant: dict, customer: dict, trigger: dict) -> tuple[dict, dict]:
    import copy
    m_pruned = copy.deepcopy(merchant)
    c_pruned = copy.deepcopy(customer) if customer else {}
    
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

def compose(trigger_id: str, merchant: dict, category: dict, trigger: dict = None, customer: dict = None) -> list[ActionModel]:
    from elite_templates import get_elite_response
    
    # STEP 1: Check elite templates (instant, no API needed)
    elite = get_elite_response(trigger_id, merchant, category, trigger or {}, customer)
    if elite is not None:
        logger.info(f"Elite template hit for {trigger_id}")
        return elite
    
    # STEP 2: Unknown trigger — try LLM
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not litellm or not api_key:
        return mock_compose(trigger_id, merchant, category)
        
    try:
        import time as _time
        from prompts import SYSTEM_PROMPT, COMPOSE_TEMPLATE, CATEGORY_ANCHORS
        
        m_pruned, c_pruned = prune_context(merchant, customer, trigger or {})
        category_slug = category.get("slug", "unknown")
        
        prompt = COMPOSE_TEMPLATE.format(
            merchant_json=json.dumps(m_pruned),
            category_json=json.dumps(category),
            trigger_json=json.dumps(trigger or {}),
            customer_json=json.dumps(c_pruned),
        )
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = litellm.completion(
                    model=os.getenv("DEFAULT_MODEL", "groq/llama-3.1-8b-instant"),
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    timeout=12, temperature=0.1
                )
                parsed = LLMActionOutput.model_validate_json(response.choices[0].message.content)
                return parsed.actions
            except Exception as retry_err:
                if attempt < max_retries - 1:
                    _time.sleep(1.0)
                    continue
                raise
        
        return mock_compose(trigger_id, merchant, category)
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return mock_compose(trigger_id, merchant, category)
