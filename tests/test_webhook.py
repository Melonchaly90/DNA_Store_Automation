import pytest
import os
import json
import hmac
import hashlib
import sqlite3
from fastapi.testclient import TestClient
from webhook.main import app, session_store, last_query_cache

# Test secret — set in the environment before importing the app
TEST_SECRET = "test_webhook_secret_key_12345"
os.environ["WHATSAPP_WEBHOOK_SECRET"] = TEST_SECRET

client = TestClient(app)


def _sign(payload: dict) -> str:
    """Compute the sha256=<hex> signature for a JSON payload using the test secret."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(TEST_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _post_webhook(payload: dict):
    """POST to /webhook with a valid HMAC signature header."""
    body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(TEST_SECRET.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return client.post(
        "/webhook",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={sig}",
        },
    )


@pytest.fixture(autouse=True)
def setup_db_and_clean_store():
    # Setup clean SQLite test database
    conn = sqlite3.connect("dna_thrift.db")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        brand TEXT NOT NULL,
        model_name TEXT NOT NULL,
        size REAL NOT NULL,
        size_unit TEXT NOT NULL,
        condition_score INTEGER NOT NULL,
        base_price REAL NOT NULL,
        in_stock BOOLEAN NOT NULL DEFAULT 1,
        description TEXT
    );
    """)
    conn.execute("DELETE FROM inventory;")
    conn.execute("""
    INSERT INTO inventory (brand, model_name, size, size_unit, condition_score, base_price, in_stock)
    VALUES ('Nike', 'Air Jordan 1', 10.0, 'US', 8, 10000.0, 1);
    """)
    conn.execute("""
    INSERT INTO inventory (brand, model_name, size, size_unit, condition_score, base_price, in_stock)
    VALUES ('Adidas', 'Samba', 9.0, 'US', 9, 8000.0, 1);
    """)
    conn.commit()
    conn.close()

    # Reset global session store and query cache to isolate tests
    session_store._sessions.clear()
    last_query_cache.clear()


# ── Security Tests ──────────────────────────────────────────────────────

def test_missing_signature_returns_401():
    """Request without X-Hub-Signature-256 header should be rejected."""
    payload = {"object": "whatsapp_business_account", "entry": []}
    response = client.post("/webhook", json=payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_bad_signature_returns_401():
    """Request with an incorrect signature should be rejected."""
    payload = {"object": "whatsapp_business_account", "entry": []}
    response = client.post(
        "/webhook",
        json=payload,
        headers={"X-Hub-Signature-256": "sha256=badhex0000"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


# ── Existing Tests (updated with signature) ─────────────────────────────

def test_webhook_valid_payload():
    sample_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "456"},
                            "messages": [
                                {
                                    "from": "923001234567",
                                    "id": "wamid.abc",
                                    "timestamp": "1720000000",
                                    "type": "text",
                                    "text": {"body": "looking for Nike Air Jordan 1 size 10"}
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    response = _post_webhook(sample_payload)
    assert response.status_code == 200
    assert "We found Nike Air Jordan 1 in size 10.0 US!" in response.json()["reply"]


def test_webhook_invalid_payload():
    invalid_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": []
                        }
                    }
                ]
            }
        ]
    }

    response = _post_webhook(invalid_payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid payload"
    # Verify internal errors are NOT leaked
    assert "errors" not in response.json()


# ── Integration Tests ───────────────────────────────────────────────────

def test_full_text_query_exact_match():
    """Full text query with exact match."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "1",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "1"},
                    "messages": [{
                        "from": "1112223333",
                        "id": "msg.1",
                        "timestamp": "1720000000",
                        "type": "text",
                        "text": {"body": "looking for Adidas Samba size 9"}
                    }]
                }
            }]
        }]
    }

    response = _post_webhook(payload)
    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "We found Adidas Samba in size 9.0 US!" in reply
    assert "Would you like to buy it?" in reply

    session = session_store.get_or_create("1112223333")
    assert session.current_state == "AWAITING_PURCHASE_INTENT"


def test_text_query_missing_size_then_confirmation():
    """Text query with missing size followed by a size-confirmation message."""
    phone = "4445556666"

    # Step 1: Missing size query
    payload1 = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "1",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "1"},
                    "messages": [{
                        "from": phone,
                        "id": "msg.1",
                        "timestamp": "1720000000",
                        "type": "text",
                        "text": {"body": "looking for Nike Air Jordan 1"}
                    }]
                }
            }]
        }]
    }

    response1 = _post_webhook(payload1)
    assert response1.status_code == 200
    reply1 = response1.json()["reply"]
    assert "What size (US/UK/EU) are you looking for in the Nike Air Jordan 1?" in reply1

    session = session_store.get_or_create(phone)
    assert session.current_state == "AWAITING_SIZE_CONFIRMATION"

    # Step 2: Size confirmation query
    payload2 = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "1",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "1"},
                    "messages": [{
                        "from": phone,
                        "id": "msg.2",
                        "timestamp": "1720000010",
                        "type": "text",
                        "text": {"body": "10"}
                    }]
                }
            }]
        }]
    }

    response2 = _post_webhook(payload2)
    assert response2.status_code == 200
    reply2 = response2.json()["reply"]
    assert "We found an exact match for Nike Air Jordan 1 in size 10.0 US" in reply2

    session = session_store.get_or_create(phone)
    assert session.current_state == "AWAITING_PURCHASE_INTENT"


def test_two_consecutive_unclear_messages_trigger_failed():
    """Two consecutive unclear messages trigger CLARIFICATION_FAILED handoff."""
    phone = "7778889999"

    # Message 1
    payload1 = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "1",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "1"},
                    "messages": [{
                        "from": phone,
                        "id": "msg.1",
                        "timestamp": "1720000000",
                        "type": "text",
                        "text": {"body": "hello"}
                    }]
                }
            }]
        }]
    }

    response1 = _post_webhook(payload1)
    assert response1.status_code == 200
    assert "please be more specific" in response1.json()["reply"].lower()

    session = session_store.get_or_create(phone)
    assert session.current_state == "AWAITING_QUERY"
    assert session.clarification_attempts == 1

    # Message 2
    payload2 = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "1",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "1"},
                    "messages": [{
                        "from": phone,
                        "id": "msg.2",
                        "timestamp": "1720000010",
                        "type": "text",
                        "text": {"body": "what up"}
                    }]
                }
            }]
        }]
    }

    response2 = _post_webhook(payload2)
    assert response2.status_code == 200
    reply2 = response2.json()["reply"]
    assert "human handoff" in reply2.lower()

    session = session_store.get_or_create(phone)
    assert session.current_state == "CLARIFICATION_FAILED"