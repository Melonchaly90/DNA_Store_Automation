import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from models.webhook_payload import WhatsAppWebhookPayload, WhatsAppMessage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()


def process_customer_message(message: WhatsAppMessage):
    """
    Placeholder stub function to process a single WhatsApp message.
    Will be wired to the state machine by the user.
    """
    logger.info(f"Stub processing message: {message.id} from {message.from_}")


@app.post("/webhook")
async def webhook(request: Request):
    # Attempt to read request body as JSON
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Request body is not valid JSON: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid JSON body"}
        )

    # Validate against WhatsAppWebhookPayload Pydantic model
    try:
        payload = WhatsAppWebhookPayload(**body)
    except ValidationError as e:
        logger.error(f"WhatsApp webhook payload validation failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Validation failed", "errors": e.errors()}
        )

    # Process valid payload
    for entry in payload.entry:
        for change in entry.changes:
            messages = change.value.messages
            if messages is None:
                logger.debug("Value has no messages. Skipping.")
                continue

            for message in messages:
                process_customer_message(message)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "success"}
    )
