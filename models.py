from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

# --- Common Enums/Types ---

# --- Category Models ---
class OfferCatalogItem(BaseModel):
    id: str
    title: str
    value: str
    audience: str
    type: str

class VoiceModel(BaseModel):
    tone: str
    voice_register: Optional[str] = Field(None, alias="register")
    code_mix: Optional[str] = None
    vocab_allowed: Optional[List[str]] = None
    vocab_taboo: Optional[List[str]] = None
    salutation_examples: Optional[List[str]] = None
    tone_examples: Optional[List[str]] = None

class PeerStats(BaseModel):
    scope: Optional[str] = None
    avg_rating: Optional[float] = None
    avg_review_count: Optional[int] = None
    avg_views_30d: Optional[int] = None
    avg_calls_30d: Optional[int] = None
    avg_directions_30d: Optional[int] = None
    avg_ctr: Optional[float] = None
    avg_photos: Optional[int] = None
    avg_post_freq_days: Optional[int] = None
    retention_6mo_pct: Optional[float] = None

class DigestItem(BaseModel):
    id: str
    kind: str
    title: str
    source: str
    trial_n: Optional[int] = None
    patient_segment: Optional[str] = None
    summary: Optional[str] = None
    actionable: Optional[str] = None
    date: Optional[str] = None
    credits: Optional[int] = None

class PatientContent(BaseModel):
    id: str
    title: str
    channel: str
    length_seconds: int
    body: str

class SeasonalBeat(BaseModel):
    month_range: str
    note: str

class TrendSignal(BaseModel):
    query: str
    delta_yoy: float
    segment_age: Optional[str] = None
    skew: Optional[str] = None

class CategoryPayload(BaseModel):
    slug: str
    display_name: Optional[str] = None
    voice: VoiceModel
    offer_catalog: Optional[List[OfferCatalogItem]] = []
    peer_stats: Optional[PeerStats] = None
    digest: Optional[List[DigestItem]] = []
    patient_content_library: Optional[List[PatientContent]] = []
    seasonal_beats: Optional[List[SeasonalBeat]] = []
    trend_signals: Optional[List[TrendSignal]] = []
    regulatory_authorities: Optional[List[str]] = []
    professional_journals: Optional[List[str]] = []

# --- Merchant Models ---
class MerchantIdentity(BaseModel):
    name: str
    city: str
    locality: str
    place_id: Optional[str] = None
    verified: bool
    languages: List[str]
    owner_first_name: str
    established_year: Optional[int] = None

class Subscription(BaseModel):
    status: str
    plan: str
    days_remaining: Optional[int] = None
    days_since_expiry: Optional[int] = None
    renewed_at: Optional[str] = None

class PerformanceDelta(BaseModel):
    views_pct: Optional[float] = None
    calls_pct: Optional[float] = None
    ctr_pct: Optional[float] = None

class Performance(BaseModel):
    window_days: int
    views: int
    calls: int
    directions: int
    ctr: float
    leads: Optional[int] = None
    delta_7d: Optional[PerformanceDelta] = None

class MerchantOffer(BaseModel):
    id: str
    title: str
    status: str
    started: Optional[str] = None
    ended: Optional[str] = None

class ConversationHistoryItem(BaseModel):
    ts: str
    from_role: Optional[str] = Field(None, alias="from") # using alias as 'from' is keyword
    body: str
    engagement: str

class CustomerAggregate(BaseModel):
    total_unique_ytd: Optional[int] = None
    lapsed_180d_plus: Optional[int] = None
    retention_6mo_pct: Optional[float] = None
    high_risk_adult_count: Optional[int] = None
    lapsed_90d_plus: Optional[int] = None
    retention_3mo_pct: Optional[float] = None
    delivery_orders_30d: Optional[int] = None
    dine_in_orders_30d: Optional[int] = None
    repeat_customer_pct: Optional[float] = None
    delivery_share_pct: Optional[float] = None
    total_active_members: Optional[int] = None
    monthly_churn_pct: Optional[float] = None
    trial_to_paid_pct: Optional[float] = None
    chronic_rx_count: Optional[int] = None

class ReviewTheme(BaseModel):
    theme: str
    sentiment: str
    occurrences_30d: int
    common_quote: Optional[str] = None

class MerchantPayload(BaseModel):
    merchant_id: str
    category_slug: str
    identity: MerchantIdentity
    subscription: Subscription
    performance: Performance
    offers: List[MerchantOffer] = []
    conversation_history: List[ConversationHistoryItem] = []
    customer_aggregate: CustomerAggregate
    signals: List[str] = []
    review_themes: Optional[List[ReviewTheme]] = []

# --- Trigger Payload ---
class TriggerPayloadDetails(BaseModel):
    category: Optional[str] = None
    top_item_id: Optional[str] = None
    # Add other flexible fields as needed
    model_config = {"extra": "allow"}

class TriggerPayload(BaseModel):
    id: str
    scope: str
    kind: str
    source: str
    merchant_id: str
    customer_id: Optional[str] = None
    payload: TriggerPayloadDetails
    urgency: int
    suppression_key: str
    expires_at: str

# --- API Request/Response Models ---

class ContextPushRequest(BaseModel):
    scope: str # "category", "merchant", "customer", "trigger"
    context_id: str
    version: int
    delivered_at: Optional[str] = None
    payload: Union[CategoryPayload, MerchantPayload, TriggerPayload, Dict[str, Any]] # Allowing Dict to capture unmodeled customer scopes or flexibility

class TickRequest(BaseModel):
    now: str
    available_triggers: List[str]

class ActionModel(BaseModel):
    conversation_id: Optional[str] = None
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    send_as: Optional[str] = None
    trigger_id: Optional[str] = None
    template_name: Optional[str] = None
    template_params: List[str] = Field(default_factory=list)
    
    @field_validator('template_params', mode='before')
    @classmethod
    def sanitize_template_params(cls, v):
        if v is None:
            return []
        if isinstance(v, list):
            return [str(item) if item is not None else "" for item in v]
        return v

    body: str
    cta: str
    suppression_key: Optional[str] = None
    rationale: str
    action: Optional[str] = None
    wait_seconds: Optional[int] = None

class TickResponse(BaseModel):
    actions: List[ActionModel]

class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: str
    turn_number: int

class ReplyResponse(BaseModel):
    action: str # "send", "wait", "end"
    body: Optional[str] = None
    cta: Optional[str] = None
    wait_seconds: Optional[int] = None
    rationale: str

class HealthResponse(BaseModel):
    status: str
    uptime_seconds: int
    contexts_loaded: Dict[str, int]
