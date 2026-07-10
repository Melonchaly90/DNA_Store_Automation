from pydantic import BaseModel, Field
from typing import Optional, Literal


class TextContent(BaseModel):
    body: str


class ImageContent(BaseModel):
    id: str
    mime_type: Optional[str] = None
    sha256: Optional[str] = None


class WhatsAppMessage(BaseModel):
    from_: str = Field(alias="from")
    id: str
    timestamp: str
    type: Literal["text", "image"]
    text: Optional[TextContent] = None
    image: Optional[ImageContent] = None

    model_config = {"populate_by_name": True}


class WebhookMetadata(BaseModel):
    phone_number_id: str


class WebhookValue(BaseModel):
    messaging_product: str
    metadata: WebhookMetadata
    messages: Optional[list[WhatsAppMessage]] = None


class WebhookChange(BaseModel):
    value: WebhookValue
    field: str


class WebhookEntry(BaseModel):
    id: str
    changes: list[WebhookChange]


class WhatsAppWebhookPayload(BaseModel):
    object: str
    entry: list[WebhookEntry]


if __name__ == "__main__":
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

    parsed = WhatsAppWebhookPayload(**sample_payload)
    print(parsed.entry[0].changes[0].value.messages[0].text.body)
    print(parsed.entry[0].changes[0].value.messages[0].from_)