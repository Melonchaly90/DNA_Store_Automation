from datetime import datetime, timezone
from models.conversation_session import ConversationSession


class SessionStore:
    """
    A simple in-memory, dict-based store for ConversationSession instances.
    """

    def __init__(self):
        self._sessions = {}

    def get_or_create(self, customer_phone: str) -> ConversationSession:
        if customer_phone not in self._sessions:
            self._sessions[customer_phone] = ConversationSession(
                customer_phone=customer_phone,
                current_state="AWAITING_QUERY",
                clarification_attempts=0,
                last_ambiguous_field=None,
                updated_at=datetime.now(timezone.utc),
            )
        return self._sessions[customer_phone]

    def save(self, session: ConversationSession):
        self._sessions[session.customer_phone] = session
