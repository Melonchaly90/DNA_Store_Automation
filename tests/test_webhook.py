import pytest
import sqlite3
from fastapi.testclient import TestClient
from webhook.main import app, session_store, last_query_cache

client = TestClient(app)


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
    # Insert test items
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

    response = client.post("/webhook", json=sample_payload)
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

    response = client.post("/webhook", json=invalid_payload)
    assert response.status_code == 400
    assert "Validation failed" in response.json()["detail"]


# ── Integration Tests requested by User ─────────────────────────────────

def test_full_text_query_exact_match():
    """
    Integration Test 1: Full text query with exact match.
    Customer texts: "looking for Adidas Samba size 9"
    Should result in: Exact match found in inventory, state goes to AWAITING_PURCHASE_INTENT.
    """
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

    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "We found Adidas Samba in size 9.0 US!" in reply
    assert "Would you like to buy it?" in reply

    # Verify session state is updated
    session = session_store.get_or_create("1112223333")
    assert session.current_state == "AWAITING_PURCHASE_INTENT"


def test_text_query_missing_size_then_confirmation():
    """
    Integration Test 2: Text query with missing size followed by a size-confirmation message.
    1. Customer texts: "looking for Nike Air Jordan 1"
       Should reply asking for size. State: AWAITING_SIZE_CONFIRMATION.
    2. Customer texts: "size 10" (or just "10")
       Should reply finding the exact match. State: AWAITING_PURCHASE_INTENT.
    """
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

    response1 = client.post("/webhook", json=payload1)
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

    response2 = client.post("/webhook", json=payload2)
    assert response2.status_code == 200
    reply2 = response2.json()["reply"]
    assert "We found an exact match for Nike Air Jordan 1 in size 10.0 US" in reply2

    session = session_store.get_or_create(phone)
    assert session.current_state == "AWAITING_PURCHASE_INTENT"


def test_two_consecutive_unclear_messages_trigger_failed():
    """
    Integration Test 3: Two consecutive unclear messages trigger CLARIFICATION_FAILED handoff.
    1st message: "hello" -> returns specific query instruction. attempts -> 1
    2nd message: "what up" -> triggers CLARIFICATION_FAILED.
    """
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

    response1 = client.post("/webhook", json=payload1)
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

    response2 = client.post("/webhook", json=payload2)
    assert response2.status_code == 200
    reply2 = response2.json()["reply"]
    assert "human handoff" in reply2.lower()

    # Verify session landed in CLARIFICATION_FAILED
    # Note: Immediately after landing in CLARIFICATION_FAILED, the next incoming message
    # will transition it back out to AWAITING_QUERY.
    # Our session state right now (after the 2nd message finished processing) is CLARIFICATION_FAILED.
    session = session_store.get_or_create(phone)
    assert session.current_state == "CLARIFICATION_FAILED"