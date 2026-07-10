import logging
import sqlite3
import re
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from models.webhook_payload import WhatsAppWebhookPayload, WhatsAppMessage
from conversation.state_machine import ConversationStateMachine
from conversation.session_store import SessionStore
from nlp.text_parser import parse_text_query
from vision.photo_analyzer import analyze_shoe_photo
from inventory.db import find_matches
from inventory.pricing import calculate_price

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Global instances
session_store = SessionStore()
state_machine = ConversationStateMachine()

# Cache for the last identified brand and model per customer phone number
last_query_cache = {}

# Constants for common brands/models to augment database list
KNOWN_BRANDS = ["Nike", "Adidas", "Jordan", "New Balance", "Puma", "Reebok", "Asics"]
KNOWN_MODELS = ["Air Jordan 1", "Air Jordan 11", "Yeezy 350", "Samba", "Ultraboost", "Superstar"]


def get_known_brands_and_models():
    """
    Combines static known brands/models with any dynamic ones present in the DB.
    """
    brands = set(KNOWN_BRANDS)
    models = set(KNOWN_MODELS)
    try:
        conn = sqlite3.connect("dna_thrift.db")
        cursor = conn.execute("SELECT DISTINCT brand, model_name FROM inventory")
        for brand, model in cursor.fetchall():
            if brand:
                brands.add(brand)
            if model:
                models.add(model)
        conn.close()
    except Exception as e:
        logger.warning(f"Could not load brands/models from database: {e}")
    return list(brands), list(models)


def extract_size_only(text: str) -> float | None:
    """
    Helper to extract size number (5 to 15) from a size-only confirmation message.
    """
    size_match = re.search(r'\bsize\s*(\d+(?:\.\d+)?)\b', text, re.IGNORECASE)
    if size_match:
        try:
            return float(size_match.group(1))
        except ValueError:
            pass
    # Standalone number fallback
    numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', text)
    for num_str in numbers:
        try:
            val = float(num_str)
            if 5.0 <= val <= 15.0:
                return val
        except ValueError:
            pass
    return None


def process_customer_message(message: WhatsAppMessage) -> str:
    """
    Processes a customer's WhatsApp message, updates state, queries inventory,
    and returns the reply text.
    """
    phone = message.from_
    session = session_store.get_or_create(phone)

    # 1. Handle CLARIFICATION_FAILED entry transition out
    if session.current_state == "CLARIFICATION_FAILED":
        session = state_machine.transition(session, "customer_message")
        session_store.save(session)
        return "I will connect you to a human agent for assistance."

    known_brands, known_models = get_known_brands_and_models()

    # 2. Handle AWAITING_SIZE_CONFIRMATION state specifically
    if session.current_state == "AWAITING_SIZE_CONFIRMATION":
        text_body = message.text.body if (message.type == "text" and message.text) else ""
        extracted_size = extract_size_only(text_body)

        if extracted_size is not None:
            # Transition with usable_size
            session = state_machine.transition(session, "usable_size")
            session_store.save(session)

            # Retrieve brand and model from cache
            brand, model_name = last_query_cache.get(phone, (None, None))
            if brand or model_name:
                try:
                    conn = sqlite3.connect("dna_thrift.db")
                    matches = find_matches(conn, brand, model_name, extracted_size, "US")
                    conn.close()
                except Exception as e:
                    logger.error(f"Database query failed: {e}")
                    matches = []

                # Determine if we have an exact match
                exact_match = None
                for row in matches:
                    if (row["brand"] == brand and
                            row["model_name"] == model_name and
                            row["size"] == extracted_size):
                        exact_match = row
                        break

                if exact_match:
                    session = state_machine.transition(session, "exact_match")
                    session_store.save(session)
                    price = calculate_price(exact_match["base_price"], exact_match["condition_score"])
                    return (
                        f"Great news! We found an exact match for {brand} {model_name} "
                        f"in size {extracted_size} US. Price: PKR {price:.2f}. Would you like to buy it?"
                    )
                elif matches:
                    session = state_machine.transition(session, "no_match")
                    session_store.save(session)
                    sizes_str = ", ".join([f"{r['size']} {r['size_unit']}" for r in matches])
                    return (
                        f"Sorry, we don't have size {extracted_size} US in stock. "
                        f"However, we have these sizes available: {sizes_str}."
                    )
                else:
                    session = state_machine.transition(session, "no_match")
                    session_store.save(session)
                    return f"Sorry, {brand} {model_name} is currently out of stock."
            else:
                session = state_machine.transition(session, "no_match")
                session_store.save(session)
                return "Got the size, but I lost track of the shoe model. Please search again!"
        else:
            # Transition with unusable_size
            session = state_machine.transition(session, "unusable_size")
            session_store.save(session)
            if session.current_state == "CLARIFICATION_FAILED":
                return "I'm offering a human handoff. A support representative will be with you shortly."
            else:
                return "I didn't catch a valid size. Please specify a size between 5 and 15 (e.g., 'size 10')."

    # 3. Handle purchase confirmation state
    if session.current_state == "AWAITING_PURCHASE_INTENT":
        text_body = message.text.body.strip().lower() if (message.type == "text" and message.text) else ""
        if text_body in ["confirm", "buy", "yes", "purchase", "y"]:
            session = state_machine.transition(session, "confirm_purchase")
            session_store.save(session)
            return "Thank you for your purchase! We will process your order shortly."
        else:
            session = state_machine.transition(session, "new_query")
            # Fall through to process new query in IDENTIFYING_SHOE state

    # 4. Standard flow (AWAITING_QUERY or newly transitioned to IDENTIFYING_SHOE)
    if session.current_state == "AWAITING_QUERY":
        session = state_machine.transition(session, "customer_message")
        session_store.save(session)

    # State is now IDENTIFYING_SHOE
    query = None
    if message.type == "text" and message.text:
        query = parse_text_query(message.text.body, known_brands, known_models)
    elif message.type == "image" and message.image:
        logger.info(f"would download media_id: {message.image.id}")
        query = analyze_shoe_photo(message.image.id, known_brands, known_models)

    if query is None:
        session = state_machine.transition(session, "invalid_query")
        session_store.save(session)
        if session.current_state == "CLARIFICATION_FAILED":
            return "I'm offering a human handoff. A support representative will be with you shortly."
        return "Could you please be more specific with the brand or model name of the shoe?"

    # Cache successfully parsed brand and model
    last_query_cache[phone] = (query.brand, query.model_name)

    if query.size is None:
        session = state_machine.transition(session, "valid_query_missing_size")
        session_store.save(session)
        return f"What size (US/UK/EU) are you looking for in the {query.brand} {query.model_name}?"

    # Query inventory
    session = state_machine.transition(session, "valid_query_with_size")
    session_store.save(session)

    try:
        conn = sqlite3.connect("dna_thrift.db")
        matches = find_matches(conn, query.brand, query.model_name, query.size, query.size_unit or "US")
        conn.close()
    except Exception as e:
        logger.error(f"Database query failed: {e}")
        matches = []

    # Check for exact match
    exact_match = None
    for row in matches:
        if (row["brand"] == query.brand and
                row["model_name"] == query.model_name and
                row["size"] == query.size):
            exact_match = row
            break

    if exact_match:
        session = state_machine.transition(session, "exact_match")
        session_store.save(session)
        price = calculate_price(exact_match["base_price"], exact_match["condition_score"])
        return (
            f"We found {query.brand} {query.model_name} in size {query.size} US! "
            f"Price: PKR {price:.2f}. Would you like to buy it?"
        )
    elif matches:
        session = state_machine.transition(session, "no_match")
        session_store.save(session)
        sizes_str = ", ".join([f"{r['size']} {r['size_unit']}" for r in matches])
        return (
            f"Sorry, we don't have size {query.size} US in stock for {query.brand} {query.model_name}. "
            f"Available sizes: {sizes_str}."
        )
    else:
        session = state_machine.transition(session, "no_match")
        session_store.save(session)
        return f"Sorry, {query.brand} {query.model_name} is currently out of stock."


@app.post("/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Request body is not valid JSON: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid JSON body"}
        )

    try:
        payload = WhatsAppWebhookPayload(**body)
    except ValidationError as e:
        logger.error(f"WhatsApp webhook payload validation failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Validation failed", "errors": e.errors()}
        )

    last_reply = "No messages processed"
    for entry in payload.entry:
        for change in entry.changes:
            messages = change.value.messages
            if messages is None:
                logger.debug("Value has no messages. Skipping.")
                continue

            for message in messages:
                last_reply = process_customer_message(message)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "success", "reply": last_reply}
    )
