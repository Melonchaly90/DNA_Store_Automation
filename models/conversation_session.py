from pydantic import BaseModel
from typing import Literal
from datetime import datetime

ConversationStateName = Literal[
    "AWAITING_QUERY",
    "IDENTIFYING_SHOE",
    "AWAITING_SIZE_CONFIRMATION",
    "PRESENTING_RESULT",
    "AWAITING_PURCHASE_INTENT",
    "CLARIFICATION_FAILED",
]


class ConversationSession(BaseModel):
    customer_phone: str
    current_state: ConversationStateName = "AWAITING_QUERY"
    clarification_attempts: int = 0          # the counter lives here
    last_ambiguous_field: str | None = None  # e.g. "size" — what we're clarifying
    updated_at: datetime
