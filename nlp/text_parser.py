import re
from typing import Optional
from models.shoe_query import ShoeQuery


def parse_text_query(
    raw_text: str,
    known_brands: list[str],
    known_models: list[str]
) -> Optional[ShoeQuery]:
    """
    Parses a customer's raw text query to extract brand, model name, and size.
    Returns None if neither brand nor model is found.
    """
    raw_text_lower = raw_text.lower()

    # Find all matching brands, recording their start index
    matched_brands = []
    for brand in known_brands:
        pos = raw_text_lower.find(brand.lower())
        if pos != -1:
            matched_brands.append((pos, brand))
    
    # Prioritize brand that starts earliest, then by length descending
    matched_brand = None
    if matched_brands:
        matched_brands.sort(key=lambda x: (x[0], -len(x[1])))
        matched_brand = matched_brands[0][1]

    # Find all matching models, recording their start index
    matched_models = []
    for model in known_models:
        pos = raw_text_lower.find(model.lower())
        if pos != -1:
            matched_models.append((pos, model))

    # Prioritize model that starts earliest, then by length descending
    matched_model = None
    if matched_models:
        matched_models.sort(key=lambda x: (x[0], -len(x[1])))
        matched_model = matched_models[0][1]

    # If neither brand nor model found, return None
    if not matched_brand and not matched_model:
        return None

    # Determine confidence: 1.0 if both are found, 0.5 if only one is found
    if matched_brand and matched_model:
        confidence = 1.0
    else:
        confidence = 0.5

    # Extract size number
    # First check explicit patterns like "size 10", "size 9.5"
    size_match = re.search(r'\bsize\s*(\d+(?:\.\d+)?)\b', raw_text, re.IGNORECASE)
    size_val = None

    if size_match:
        try:
            size_val = float(size_match.group(1))
        except ValueError:
            pass
    else:
        # Look for a standalone number between 5 and 15 (inclusive)
        # To avoid matching part of brand/model names (e.g. Jordan 11),
        # remove matched brand and model substrings from the search string first.
        # Remove longer strings first to prevent shorter substrings from destroying longer ones.
        text_for_standalone = raw_text
        to_remove = []
        if matched_brand:
            to_remove.append(matched_brand)
        if matched_model:
            to_remove.append(matched_model)

        for item in sorted(to_remove, key=len, reverse=True):
            text_for_standalone = re.sub(
                re.escape(item), "", text_for_standalone, flags=re.IGNORECASE
            )

        numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', text_for_standalone)
        for num_str in numbers:
            try:
                val = float(num_str)
                if 5.0 <= val <= 15.0:
                    size_val = val
                    break
            except ValueError:
                pass

    return ShoeQuery(
        brand=matched_brand,
        model_name=matched_model,
        size=size_val,
        size_unit="US" if size_val is not None else None,  # Default unit if size is found
        source="text",
        confidence=confidence,
        raw_input=raw_text
    )
