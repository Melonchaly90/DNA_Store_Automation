import pytest
from datetime import datetime, timezone

from models.conversation_session import ConversationSession
from conversation.state_machine import ConversationStateMachine


def _make_session(
    state: str = "AWAITING_QUERY",
    attempts: int = 0,
    field: str | None = None,
) -> ConversationSession:
    return ConversationSession(
        customer_phone="+1234567890",
        current_state=state,
        clarification_attempts=attempts,
        last_ambiguous_field=field,
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sm() -> ConversationStateMachine:
    return ConversationStateMachine()


# ── 1. Counter increments correctly ─────────────────────────────────────

class TestCounterIncrements:

    def test_invalid_query_increments(self, sm):
        """IDENTIFYING_SHOE + invalid_query → AWAITING_QUERY, +1 attempt."""
        s = _make_session("IDENTIFYING_SHOE", attempts=0)
        s = sm.transition(s, "invalid_query")
        assert s.clarification_attempts == 1
        assert s.current_state == "AWAITING_QUERY"

    def test_unusable_size_increments(self, sm):
        """AWAITING_SIZE_CONFIRMATION + unusable_size → stay, +1 attempt."""
        s = _make_session("AWAITING_SIZE_CONFIRMATION", attempts=0, field="size")
        s = sm.transition(s, "unusable_size")
        assert s.clarification_attempts == 1
        assert s.current_state == "AWAITING_SIZE_CONFIRMATION"


# ── 2. CLARIFICATION_FAILED after 2 consecutive same-field failures ─────

class TestClarificationFailed:

    def test_unusable_size_triggers_after_two_failures(self, sm):
        """Two consecutive unusable_size events → state lands on
        CLARIFICATION_FAILED (visible to conversation handler)."""
        s = _make_session("AWAITING_SIZE_CONFIRMATION", attempts=0, field="size")

        # First failure
        s = sm.transition(s, "unusable_size")
        assert s.clarification_attempts == 1
        assert s.current_state == "AWAITING_SIZE_CONFIRMATION"

        # Second failure — must land ON CLARIFICATION_FAILED
        s = sm.transition(s, "unusable_size")
        assert s.current_state == "CLARIFICATION_FAILED"
        assert s.clarification_attempts == 2

    def test_invalid_query_triggers_after_two_failures(self, sm):
        """Two consecutive invalid_query events → CLARIFICATION_FAILED."""
        s = _make_session("IDENTIFYING_SHOE", attempts=0)
        s = sm.transition(s, "invalid_query")   # → AWAITING_QUERY, attempts=1
        assert s.current_state == "AWAITING_QUERY"
        assert s.clarification_attempts == 1

        s = sm.transition(s, "customer_message")  # → IDENTIFYING_SHOE
        s = sm.transition(s, "invalid_query")     # attempts=2 → CLARIFICATION_FAILED
        assert s.current_state == "CLARIFICATION_FAILED"
        assert s.clarification_attempts == 2

    def test_single_failure_does_not_trigger(self, sm):
        """One failure stays in AWAITING_SIZE_CONFIRMATION — no escalation."""
        s = _make_session("AWAITING_SIZE_CONFIRMATION", attempts=0, field="size")
        s = sm.transition(s, "unusable_size")
        assert s.current_state == "AWAITING_SIZE_CONFIRMATION"
        assert s.clarification_attempts == 1


# ── 3. No-match result does NOT increment the counter ────────────────────

class TestNoMatchNoIncrement:

    def test_no_match_keeps_counter_unchanged(self, sm):
        """PRESENTING_RESULT + no_match → AWAITING_QUERY, counter unchanged."""
        s = _make_session("PRESENTING_RESULT", attempts=3)
        s = sm.transition(s, "no_match")
        assert s.clarification_attempts == 3   # unchanged
        assert s.current_state == "AWAITING_QUERY"

    def test_no_match_zero_counter_stays_zero(self, sm):
        s = _make_session("PRESENTING_RESULT", attempts=0)
        s = sm.transition(s, "no_match")
        assert s.clarification_attempts == 0
        assert s.current_state == "AWAITING_QUERY"


# ── 4. Counter resets on CLARIFICATION_FAILED entry ──────────────────────

class TestCounterResetOnClarificationFailed:

    def test_reset_on_next_message_after_cf(self, sm):
        """When session sits on CLARIFICATION_FAILED and customer sends a
        new message, counter resets to 0 and state goes to AWAITING_QUERY."""
        # Get into CLARIFICATION_FAILED
        s = _make_session("AWAITING_SIZE_CONFIRMATION", attempts=1, field="size")
        s = sm.transition(s, "unusable_size")  # attempts=2 → CLARIFICATION_FAILED
        assert s.current_state == "CLARIFICATION_FAILED"

        # Next message resets
        s = sm.transition(s, "customer_message")
        assert s.current_state == "AWAITING_QUERY"
        assert s.clarification_attempts == 0
        assert s.last_ambiguous_field is None

    def test_explicit_clarification_failed_state_resets(self, sm):
        """If already in CLARIFICATION_FAILED, customer_message resets."""
        s = _make_session("CLARIFICATION_FAILED", attempts=5, field="size")
        s = sm.transition(s, "customer_message")
        assert s.clarification_attempts == 0
        assert s.current_state == "AWAITING_QUERY"
        assert s.last_ambiguous_field is None


# ── 5. Happy-path smoke tests ───────────────────────────────────────────

class TestHappyPath:

    def test_full_flow_with_size(self, sm):
        s = _make_session("AWAITING_QUERY")
        s = sm.transition(s, "customer_message")
        assert s.current_state == "IDENTIFYING_SHOE"

        s = sm.transition(s, "valid_query_with_size")
        assert s.current_state == "PRESENTING_RESULT"

        s = sm.transition(s, "exact_match")
        assert s.current_state == "AWAITING_PURCHASE_INTENT"

    def test_flow_with_missing_size(self, sm):
        s = _make_session("AWAITING_QUERY")
        s = sm.transition(s, "customer_message")
        s = sm.transition(s, "valid_query_missing_size")
        assert s.current_state == "AWAITING_SIZE_CONFIRMATION"

        s = sm.transition(s, "usable_size")
        assert s.current_state == "PRESENTING_RESULT"
        assert s.clarification_attempts == 0

    def test_new_query_from_purchase_intent(self, sm):
        s = _make_session("AWAITING_PURCHASE_INTENT")
        s = sm.transition(s, "new_query")
        assert s.current_state == "IDENTIFYING_SHOE"

    def test_invalid_event_raises(self, sm):
        s = _make_session("AWAITING_QUERY")
        with pytest.raises(ValueError, match="No transition"):
            sm.transition(s, "exact_match")
