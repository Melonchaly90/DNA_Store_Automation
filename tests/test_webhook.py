import pytest
from fastapi.testclient import TestClient

from webhook.main import app

client = TestClient(app)


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
                                    "text": {"body": "looking for air jordan 1 size 10"}
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
    assert response.json() == {"status": "success"}


def test_webhook_invalid_payload():
    # Brand new invalid payload missing required fields
    invalid_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            # missing messaging_product and metadata
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


def test_webhook_no_messages_event():
    """Simulates a non-message event (e.g. read receipt) — should return
    200 and skip silently, not error."""
    receipt_payload = {
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
                            "messages": None
                        }
                    }
                ]
            }
        ]
    }

    response = client.post("/webhook", json=receipt_payload)
    assert response.status_code == 200
    assert response.json() == {"status": "success"}