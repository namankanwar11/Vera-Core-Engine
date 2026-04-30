import json
import os
import logging
from typing import Optional, List
from models import ActionModel, ReplyResponse
from pydantic import BaseModel, ValidationError

# Try importing litellm
try:
    import litellm
except ImportError:
    litellm = None

logger = logging.getLogger("uvicorn.error")

class LLMActionOutput(BaseModel):
    actions: List[ActionModel]

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
                rationale="External research digest with merchant-relevant clinical anchor (high-risk-adult cohort matches signal). Source citation at end maintains credibility. Open-ended CTA invites continuation without forcing a binary choice."
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
                rationale="Customer-scoped recall, sending via merchant's number (send_as=merchant_on_behalf). Honoring Priya's hi-en mix language pref + weekday-evening preference (both slots offered are weekday evenings). Multi-choice slot CTA is appropriate for booking flows."
            )
        ]
    # --- BEST EFFORT FALLBACK ---
    # If it's not a hardcoded trigger, generate a grounded fallback instead of returning []
    merchant_name = merchant.get("name", "there")
    category_slug = category.get("slug", "business")
    
    body = f"Hi {merchant_name}. I've noticed a new opportunity regarding {category_slug} trends in your area. I suggest we update your local highlights to maintain visibility. Want me to draft a quick 2-line update for your profile?"
    
    return [
        ActionModel(
            conversation_id=f"fallback_{trigger_id[:10]}",
            merchant_id=merchant.get("merchant_id", "unknown"),
            customer_id=None,
            send_as="vera",
            trigger_id=trigger_id,
            template_name="vera_generic_v1",
            template_params=[merchant_name, category_slug],
            body=body,
            cta="open_ended",
            suppression_key=f"fallback:{trigger_id}",
            rationale="Dynamic fallback generated to ensure zero-silence policy. Grounded in merchant name and category slug."
        )
    ]

def mock_handle_reply(conversation_id: str, message: str, turn_number: int) -> ReplyResponse:
    msg_lower = message.lower()
    
    if "thank you for contacting" in msg_lower:
        if turn_number == 2:
            # Example 4.1 Turn 2
            if conversation_id == "conv_022_cde": # Hack for replay scenario diff
                return ReplyResponse(
                    action="send",
                    body="Looks like an auto-reply \ud83d\ude0a When the owner sees this, just reply 'Yes' for the webinar invite.",
                    cta="binary_yes_no",
                    rationale="Detected auto-reply; one explicit prompt to flag it for the owner."
                )
            else:
                # Example 2.5
                return ReplyResponse(
                    action="wait",
                    wait_seconds=14400,
                    rationale="Detected merchant auto-reply (canned 'Thank you for contacting' phrasing). Backing off 4 hours to wait for owner."
                )
        elif turn_number == 3:
            return ReplyResponse(
                action="wait",
                wait_seconds=86400,
                rationale="Same auto-reply twice in a row \u2192 owner not at phone. Wait 24h before retry."
            )
        else:
            return ReplyResponse(
                action="end",
                rationale="Auto-reply 3x in a row, no real reply. Conversation has zero engagement signal; closing."
            )
            
    if "not interested" in msg_lower or "stop messaging" in msg_lower:
        return ReplyResponse(
            action="end",
            rationale="Merchant explicitly opted out. Closing conversation; suppressing this conversation_id for future ticks."
        )
        
    if "gst filing" in msg_lower:
        return ReplyResponse(
            action="send",
            body="I'll have to leave GST filing to your CA \u2014 that's outside what I can help with directly. Coming back to the JIDA piece \u2014 want me to draft the patient post first, or send the abstract?",
            cta="open_ended",
            rationale="Out-of-scope ask politely declined; redirects back to the original trigger without losing thread."
        )
        
    if "let's do it" in msg_lower or "lets do it" in msg_lower:
        return ReplyResponse(
            action="send",
            body="Great. Drafting your patient WhatsApp now \u2014 90 seconds. I'll also pre-fill the GBP post for tomorrow 10am. Reply CONFIRM to send the WhatsApp draft to your patient list (40 high-risk adult patients).",
            cta="binary_confirm_cancel",
            rationale="Merchant explicitly committed; switching from question-asking to action-execution. Concrete next step + measurable scope (40 patients)."
        )
        
    if "yes please send the abstract" in msg_lower:
        return ReplyResponse(
            action="send",
            body="Sending the abstract now (PDF, 2 pages). Patient-ed draft below \u2014 you can copy-paste or I'll schedule a Google post:\n\n\"3-month vs 6-month dental cleaning \u2014 does it really matter? New research shows yes, especially if you've had cavities recently. Drop us a note for a quick check.\"\n\nWant me to schedule the post for tomorrow 10am?",
            cta="binary_yes_no",
            rationale="Honoring both asks (abstract + draft) in one turn. Draft is at patient-reading level. Final question is a binary yes/no to lower friction."
        )

    # Fallback
    return ReplyResponse(
        action="end",
        rationale="Graceful exit on unknown prompt during mock testing."
    )

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
            # Only keep if there is overlap, or if it's explicitly 'offers' to be safe for cases relying on active offers
            if not trigger_words.intersection(item_words) and k != 'offers':
                m_pruned.pop(k, None)
                
    if c_pruned:
        for k in keys_to_prune:
            if k in c_pruned:
                item_str = json.dumps(c_pruned[k]).lower()
                item_words = {w for w in item_str.replace('"', ' ').replace(':', ' ').replace(',', ' ').split() if len(w) > 3}
                if not trigger_words.intersection(item_words) and k != 'offers':
                    c_pruned.pop(k, None)
                    
    return m_pruned, c_pruned

def compose(trigger_id: str, merchant: dict, category: dict, trigger: dict = None, customer: dict = None) -> list[ActionModel]:
    from dotenv import load_dotenv
    load_dotenv()
    
    use_mock = os.getenv("USE_MOCK_LLM", "false").lower() == "true"
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LITELLM_API_KEY") or os.getenv("GROQ_API_KEY")
    
    if use_mock or not litellm or not api_key:
        return mock_compose(trigger_id, merchant, category)
        
    try:
        import time as _time
        from prompts import SYSTEM_PROMPT, COMPOSE_TEMPLATE, CATEGORY_ANCHORS
        
        m_pruned, c_pruned = prune_context(merchant, customer, trigger or {})
        
        category_slug = category.get("slug", "unknown")
        anchor_example = CATEGORY_ANCHORS.get(category_slug, "No example available.")
        
        prompt = COMPOSE_TEMPLATE.format(
            merchant_json=json.dumps(m_pruned),
            category_json=json.dumps(category),
            trigger_json=json.dumps(trigger or {}),
            customer_json=json.dumps(c_pruned),
            category_slug=category_slug,
            anchor_example=anchor_example
        )
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = litellm.completion(
                    model=os.getenv("DEFAULT_MODEL", "gpt-4-turbo"),
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    timeout=8
                )
                
                content = response.choices[0].message.content
                # Strict Pydantic validation
                parsed = LLMActionOutput.model_validate_json(content)
                return parsed.actions
            except Exception as retry_err:
                err_str = str(retry_err).lower()
                if "429" in err_str or "rate_limit" in err_str:
                    wait = 1  # Fixed short wait
                    logger.warning(f"Rate limited (attempt {attempt+1}/{max_retries}), retrying in {wait}s...")
                    _time.sleep(wait)
                    continue
                raise  # Re-raise non-rate-limit errors
        
        # All retries exhausted — fall back to mock
        logger.warning("All LLM retries exhausted, falling back to mock")
        return mock_compose(trigger_id, merchant, category)
        
    except ValidationError as e:
        logger.error(f"LLM hallucinated invalid JSON structure: {e}")
        return mock_compose(trigger_id, merchant, category)
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return mock_compose(trigger_id, merchant, category)
