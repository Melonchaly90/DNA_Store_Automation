from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from models.conversation_session import ConversationSession, ConversationStateName


# ── Event types matching the transition table ────────────────────────────
EventName = Literal[
    "customer_message",          # AWAITING_QUERY  → IDENTIFYING_SHOE
    "valid_query_with_size",     # IDENTIFYING_SHOE → PRESENTING_RESULT
    "valid_query_missing_size",  # IDENTIFYING_SHOE → AWAITING_SIZE_CONFIRMATION
    "invalid_query",             # IDENTIFYING_SHOE → AWAITING_QUERY (+1)
    "usable_size",               # AWAITING_SIZE_CONFIRMATION → PRESENTING_RESULT
    "unusable_size",             # AWAITING_SIZE_CONFIRMATION → stay / CLARIFICATION_FAILED
    "exact_match",               # PRESENTING_RESULT → AWAITING_PURCHASE_INTENT
    "no_match",                  # PRESENTING_RESULT → AWAITING_QUERY (no counter change)
    "confirm_purchase",          # AWAITING_PURCHASE_INTENT → end of flow
    "new_query",                 # AWAITING_PURCHASE_INTENT → IDENTIFYING_SHOE
]


class ConversationStateMachine:
    """Applies one transition from the table and returns the updated session."""

    MAX_CLARIFICATION_ATTEMPTS = 2

    def transition(
        self,
        session: ConversationSession,
        event: EventName,
        ambiguous_field: str | None = None,
    ) -> ConversationSession:
        state = session.current_state
        attempts = session.clarification_attempts
        field = session.last_ambiguous_field

        next_state: ConversationStateName
        next_attempts = attempts
        next_field = field

        # ── AWAITING_QUERY ───────────────────────────────────────────
        if state == "AWAITING_QUERY" and event == "customer_message":
            next_state = "IDENTIFYING_SHOE"

        # ── IDENTIFYING_SHOE ─────────────────────────────────────────
        elif state == "IDENTIFYING_SHOE" and event == "valid_query_with_size":
            next_state = "PRESENTING_RESULT"

        elif state == "IDENTIFYING_SHOE" and event == "valid_query_missing_size":
            next_state = "AWAITING_SIZE_CONFIRMATION"
            next_field = ambiguous_field or "size"

        elif state == "IDENTIFYING_SHOE" and event == "invalid_query":
            next_attempts = attempts + 1
            if next_attempts >= self.MAX_CLARIFICATION_ATTEMPTS:
                next_state = "CLARIFICATION_FAILED"
            else:
                next_state = "AWAITING_QUERY"

        # ── AWAITING_SIZE_CONFIRMATION ───────────────────────────────
        elif state == "AWAITING_SIZE_CONFIRMATION" and event == "usable_size":
            next_state = "PRESENTING_RESULT"
            next_attempts = 0

        elif state == "AWAITING_SIZE_CONFIRMATION" and event == "unusable_size":
            next_attempts = attempts + 1
            if next_attempts >= self.MAX_CLARIFICATION_ATTEMPTS:
                next_state = "CLARIFICATION_FAILED"
            else:
                next_state = "AWAITING_SIZE_CONFIRMATION"

        # ── PRESENTING_RESULT ────────────────────────────────────────
        elif state == "PRESENTING_RESULT" and event == "exact_match":
            next_state = "AWAITING_PURCHASE_INTENT"
            next_attempts = 0

        elif state == "PRESENTING_RESULT" and event == "no_match":
            next_state = "AWAITING_QUERY"
            # no counter change — not a customer failure

        # ── AWAITING_PURCHASE_INTENT ─────────────────────────────────
        elif state == "AWAITING_PURCHASE_INTENT" and event == "confirm_purchase":
            # End of flow — stay in this terminal state
            next_state = "AWAITING_PURCHASE_INTENT"

        elif state == "AWAITING_PURCHASE_INTENT" and event == "new_query":
            next_state = "IDENTIFYING_SHOE"

        # ── CLARIFICATION_FAILED ──────────────────────────────────────
        # Session genuinely sits in this state so the conversation handler
        # can detect it and send a handoff / browse-catalogue message.
        # The *next* customer_message resets everything and restarts.
        elif state == "CLARIFICATION_FAILED" and event == "customer_message":
            next_state = "AWAITING_QUERY"
            next_attempts = 0
            next_field = None

        else:
            raise ValueError(
                f"No transition from state={state!r} on event={event!r}"
            )

        # NOTE: last_ambiguous_field is tracked but not checked today.
        # If a second ambiguity type is added (e.g. brand), add logic
        # here to reset the counter when the ambiguous field changes.

        return session.model_copy(
            update={
                "current_state": next_state,
                "clarification_attempts": next_attempts,
                "last_ambiguous_field": next_field,
                "updated_at": datetime.now(timezone.utc),
            }
        )
