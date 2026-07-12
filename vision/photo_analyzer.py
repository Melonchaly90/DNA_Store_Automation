import os
import re
import base64
import logging
from typing import Optional, Tuple
import pytesseract
from PIL import Image
from dotenv import load_dotenv
import requests

from models.shoe_query import ShoeQuery

# Setup logging
logger = logging.getLogger(__name__)

import shutil

# Configure pytesseract path
tesseract_path = shutil.which("tesseract")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
else:
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def run_ocr(image_path: str) -> str:
    """
    Uses pytesseract to extract raw text from the image.
    """
    try:
        img = Image.open(image_path)
        raw_text = pytesseract.image_to_string(img)
        return raw_text
    except Exception as e:
        logger.warning(f"OCR execution failed: {e}")
        return ""


def extract_size_from_ocr_text(text: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Searches the OCR text for patterns like 'US 9', 'UK 8', 'EU 42' using regex.
    Returns (size, unit) or (None, None) if nothing is found.
    """
    match = re.search(r'\b(US|UK|EU)\s*(\d+(?:\.\d+)?)\b', text, re.IGNORECASE)
    if match:
        unit = match.group(1).upper()
        try:
            size = float(match.group(2))
            return size, unit
        except ValueError:
            pass

    match_reverse = re.search(r'\b(\d+(?:\.\d+)?)\s*(US|UK|EU)\b', text, re.IGNORECASE)
    if match_reverse:
        unit = match_reverse.group(2).upper()
        try:
            size = float(match_reverse.group(1))
            return size, unit
        except ValueError:
            pass

    return None, None


def ask_gemini_about_shoe(image_path: str) -> str:
    """
    Sends the image to a vision model via OpenRouter's free tier and returns
    the raw text description.
    """
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not found in environment")

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": "openrouter/free",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe the brand, model name, and condition (on a scale of 1 to 10) of the shoe in this photo."
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
                        }
                    ]
                }
            ]
        }
    )
    response.raise_for_status()
    data = response.json()
    if "choices" not in data:
        raise ValueError(f"OpenRouter response missing 'choices': {data}")
    return data["choices"][0]["message"]["content"]


def parse_gemini_description(
    description: str,
    known_brands: list[str],
    known_models: list[str]
) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """
    Reuses substring-matching logic for brand/model, and regex-extracts a condition score (1-10).
    """
    desc_lower = description.lower()

    matched_brands = []
    for brand in known_brands:
        pos = desc_lower.find(brand.lower())
        if pos != -1:
            matched_brands.append((pos, brand))
    matched_brand = None
    if matched_brands:
        matched_brands.sort(key=lambda x: (x[0], -len(x[1])))
        matched_brand = matched_brands[0][1]

    matched_models = []
    for model in known_models:
        pos = desc_lower.find(model.lower())
        if pos != -1:
            matched_models.append((pos, model))
    matched_model = None
    if matched_models:
        matched_models.sort(key=lambda x: (x[0], -len(x[1])))
        matched_model = matched_models[0][1]

    condition_score = None
    match_frac = re.search(r'\b([1-9]|10)\s*/\s*10\b', description)
    if match_frac:
        condition_score = int(match_frac.group(1))
    else:
        match_cond = re.search(
            r'condition\b.*?\b([1-9]|10)\b', description, re.IGNORECASE | re.DOTALL
        )
        if match_cond:
            condition_score = int(match_cond.group(1))
        else:
            match_score = re.search(
                r'score\b.*?\b([1-9]|10)\b', description, re.IGNORECASE | re.DOTALL
            )
            if match_score:
                condition_score = int(match_score.group(1))

    return matched_brand, matched_model, condition_score


def should_build_query(brand: Optional[str], model_name: Optional[str]) -> bool:
    """
    Returns True if either brand or model_name is truthy.
    """
    return bool(brand or model_name)


def calculate_confidence(
    brand: Optional[str],
    model_name: Optional[str],
    size_val: Optional[float]
) -> float:
    """
    Calculates confidence score based on what details were successfully extracted.
    """
    if brand and model_name:
        return 1.0 if size_val is not None else 0.9
    elif brand or model_name:
        return 0.6 if size_val is not None else 0.5
    return 0.1


def analyze_shoe_photo(
    image_path: str,
    known_brands: list[str],
    known_models: list[str]
) -> Optional[ShoeQuery]:
    """
    The main function that calls OCR and vision analysis to build a ShoeQuery.
    """
    raw_text = run_ocr(image_path)
    size_val, size_unit = extract_size_from_ocr_text(raw_text)

    try:
        desc = ask_gemini_about_shoe(image_path)
    except Exception as e:
        logger.error(f"Vision API call failed: {e}")
        desc = ""

    brand, model_name, condition = parse_gemini_description(
        desc, known_brands, known_models
    )

    if not should_build_query(brand, model_name):
        return None

    confidence = calculate_confidence(brand, model_name, size_val)

    return ShoeQuery(
        brand=brand,
        model_name=model_name,
        size=size_val,
        size_unit=size_unit,
        condition_score=condition,
        source="photo",
        confidence=confidence,
        raw_input=f"OCR Text: {raw_text.strip()} | Vision Description: {desc.strip()}"
    )