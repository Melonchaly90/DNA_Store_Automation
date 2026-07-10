# DNA Thrift Shoes — WhatsApp AI Automation

A conversational AI agent for DNA Thrift, a premium thrift shoe brand, built for the Khizex AI Engineering Internship. Customers message a description or photo of a shoe on WhatsApp; the bot identifies the shoe, reads its size, checks inventory, and replies with name, condition-adjusted price, and availability.

## Architecture

```
models/         # Pydantic schemas — ShoeQuery, ConversationSession, WhatsApp webhook payloads
conversation/   # State machine + in-memory session store
inventory/      # SQLite table, matching logic, condition-based pricing
nlp/            # Text query parsing (brand/model/size extraction via regex + matching)
vision/         # Photo pipeline — OCR for size tags, vision API for brand/model/condition
webhook/        # FastAPI endpoint receiving/responding to WhatsApp webhook events
tests/          # Full test suite covering every module above
```

## Setup

### 1. Install dependencies
```
pip install fastapi uvicorn pydantic pytesseract pillow python-dotenv requests pytest --break-system-packages
```

### 2. Install Tesseract OCR
Download and install from https://github.com/UB-Mannheim/tesseract/wiki (Windows). Note the install path (default: `C:\Program Files\Tesseract-OCR\tesseract.exe`) — this is hardcoded in `vision/photo_analyzer.py`.

### 3. Environment variables
Create a `.env` file in the project root:
```
OPENROUTER_API_KEY=your_key_here
```
Get a free key at https://openrouter.ai/keys.

### 4. Initialize the database
```
python inventory/db.py
```

### 5. Run tests
```
pytest -v
```

### 6. Run the webhook server
```
uvicorn webhook.main:app --reload
```

## How the state machine works

The conversation is governed by an explicit state machine (`conversation/state_machine.py`), not free-form LLM improvisation. States:

- `AWAITING_QUERY` — waiting for the customer's message
- `IDENTIFYING_SHOE` — parsing text or analyzing a photo
- `AWAITING_SIZE_CONFIRMATION` — shoe identified, size missing or unclear
- `PRESENTING_RESULT` — showing a match or alternatives
- `AWAITING_PURCHASE_INTENT` — asking if the customer wants to buy
- `CLARIFICATION_FAILED` — loop-prevention fallback

**Loop prevention**: a `clarification_attempts` counter lives on the session (`models/conversation_session.py`). It increments on unclear text, unclear photos, or unusable size replies. After 2 consecutive failures, the session enters `CLARIFICATION_FAILED` and the bot offers a human handoff instead of repeating the same question indefinitely. The counter resets whenever the customer provides usable information, so occasional confusion doesn't wrongly penalize them — and a genuine inventory no-match never counts against the customer, since that's not their mistake.

Sessions are stored in-memory (`conversation/session_store.py`), keyed by phone number — sufficient for this assignment's scope, though a production deployment would need persistent storage (e.g. Redis or a database table) so sessions survive a server restart.

## How the vision/OCR pipeline works

Two separate tools handle two separate jobs:

1. **Tesseract OCR** (`run_ocr`) reads the size tag text directly off the photo (e.g. "US 9", "UK 8", "EU 42"), via regex pattern matching in `extract_size_from_ocr_text`.
2. **A vision-language model** (via OpenRouter's free `openrouter/free` router) analyzes the full photo to describe brand, model, and condition (`ask_gemini_about_shoe`, `parse_gemini_description`).

These run independently and get merged into a single `ShoeQuery`. If OCR can't read a size tag (common — many product photos don't show the inner tag clearly), the query is still built with `size=None`, and the state machine asks the customer to confirm their size rather than guessing. A `confidence` score (0.1–1.0) reflects how much was successfully extracted, factoring into how the bot responds.

**Why OpenRouter, not a direct Gemini SDK call**: development started with Google's `google-generativeai` SDK, but the API key generated hit a documented Google account-provisioning bug (keys prefixed `AQ...` are stuck at zero free-tier quota across all models — confirmed via `genai.list_models()` returning valid models that all 404/429'd regardless of which was tried). OpenRouter's `openrouter/free` router was used instead, which automatically selects a working free vision-capable model.

## Known limitations

- **OCR reliability**: Tesseract works well on clear, well-lit, front-facing size tags, but fails silently (returns empty text, handled gracefully) on blurry, angled, or absent tags — this is expected and by design; the bot asks rather than guesses.
- **Vision model consistency**: since `openrouter/free` automatically selects from available free models, response format/quality can vary slightly between calls, unlike a pinned single model.
- **In-memory session store**: sessions reset if the server restarts. Fine for this assignment's local demo; would need persistent storage in production.
- **Query cache staleness**: the webhook handler caches the last identified brand/model per phone number to support two-step "search, then confirm size" flows. This cache isn't cleared after a completed purchase, so an out-of-context lone number sent much later in a new conversation could theoretically reuse stale data — acceptable for demo scope, flagged for future hardening.
- **`google.generativeai` deprecation**: the original SDK was fully deprecated by Google mid-development; this project uses OpenRouter's OpenAI-compatible HTTP API instead, avoiding the deprecated dependency entirely.

## Testing

All modules are covered by pytest, including mocked tests for the vision API (no real network calls in the test suite) and integration tests simulating full webhook conversation flows (exact match, missing-size clarification, and consecutive-failure handoff).
