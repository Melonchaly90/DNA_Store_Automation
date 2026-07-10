import pytest
from nlp.text_parser import parse_text_query


@pytest.fixture
def known_brands():
    return ["Nike", "Adidas", "Jordan", "New Balance"]


@pytest.fixture
def known_models():
    return ["Air Jordan 1", "Air Jordan 11", "Yeezy 350", "Samba", "Ultraboost"]


def test_clean_match(known_brands, known_models):
    # Nike Air Jordan 1 size 10
    query = parse_text_query("Nike Air Jordan 1 size 10", known_brands, known_models)
    assert query is not None
    assert query.brand == "Nike"
    # Note: "Air Jordan 1" is in known_models, so it matched that model name
    assert query.model_name == "Air Jordan 1"
    assert query.size == 10.0
    assert query.source == "text"
    assert query.confidence == 1.0
    assert query.raw_input == "Nike Air Jordan 1 size 10"


def test_missing_size(known_brands, known_models):
    # Adidas Samba (no size mentioned)
    query = parse_text_query("Looking for Adidas Samba", known_brands, known_models)
    assert query is not None
    assert query.brand == "Adidas"
    assert query.model_name == "Samba"
    assert query.size is None
    assert query.confidence == 1.0


def test_no_brand_no_model_match(known_brands, known_models):
    # "some random text size 9" should return None
    query = parse_text_query("some random text size 9", known_brands, known_models)
    assert query is None


def test_only_brand_found(known_brands, known_models):
    # "Nike size 9.5" (only brand, no model)
    query = parse_text_query("Nike size 9.5", known_brands, known_models)
    assert query is not None
    assert query.brand == "Nike"
    assert query.model_name is None
    assert query.size == 9.5
    assert query.confidence == 0.5


def test_only_model_found(known_brands, known_models):
    # "Yeezy 350 11.5" (only model, brand Adidas not explicitly mentioned in raw text)
    query = parse_text_query("Yeezy 350 11.5", known_brands, known_models)
    assert query is not None
    assert query.brand is None
    assert query.model_name == "Yeezy 350"
    assert query.size == 11.5
    assert query.confidence == 0.5


def test_standalone_size_exclusion_from_model(known_brands, known_models):
    # "Air Jordan 11" has 11 in the model name, but no size is explicitly mentioned.
    # It should NOT extract 11 as the size.
    query = parse_text_query("Air Jordan 11", known_brands, known_models)
    assert query is not None
    assert query.model_name == "Air Jordan 11"
    assert query.size is None
