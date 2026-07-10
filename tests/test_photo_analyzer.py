import pytest
from unittest.mock import MagicMock, patch
from vision.photo_analyzer import (
    extract_size_from_ocr_text,
    parse_gemini_description,
    should_build_query,
    calculate_confidence,
    analyze_shoe_photo
)


@pytest.fixture
def known_brands():
    return ["Nike", "Adidas", "Jordan"]


@pytest.fixture
def known_models():
    return ["Air Jordan 1", "Samba", "Ultraboost"]


def test_extract_size_from_ocr_text():
    # Test different layouts and units
    assert extract_size_from_ocr_text("Label info US 9.5 made in Vietnam") == (9.5, "US")
    assert extract_size_from_ocr_text("Size is UK 8") == (8.0, "UK")
    assert extract_size_from_ocr_text("Size: 42 EU") == (42.0, "EU")
    assert extract_size_from_ocr_text("No size info here") == (None, None)


def test_parse_gemini_description(known_brands, known_models):
    desc_1 = "This is a Nike Air Jordan 1 shoe. Condition is 8 out of 10."
    brand, model, cond = parse_gemini_description(desc_1, known_brands, known_models)
    assert brand == "Nike"
    assert model == "Air Jordan 1"
    assert cond == 8

    desc_2 = "An Adidas shoe with score: 9. I think it is Samba model."
    brand, model, cond = parse_gemini_description(desc_2, known_brands, known_models)
    assert brand == "Adidas"
    assert model == "Samba"
    assert cond == 9

    desc_3 = "Just some random shoe, condition 5/10."
    brand, model, cond = parse_gemini_description(desc_3, known_brands, known_models)
    assert brand is None
    assert model is None
    assert cond == 5


def test_should_build_query():
    assert should_build_query("Nike", "Samba") is True
    assert should_build_query("Nike", None) is True
    assert should_build_query(None, "Samba") is True
    assert should_build_query(None, None) is False


def test_calculate_confidence():
    # Both brand & model
    assert calculate_confidence("Nike", "Samba", 9.5) == 1.0
    assert calculate_confidence("Nike", "Samba", None) == 0.9
    # One of brand & model
    assert calculate_confidence("Nike", None, 9.5) == 0.6
    assert calculate_confidence(None, "Samba", None) == 0.5
    # Neither
    assert calculate_confidence(None, None, 9.5) == 0.1


@patch("vision.photo_analyzer.run_ocr")
@patch("vision.photo_analyzer.ask_gemini_about_shoe")
def test_analyze_shoe_photo_success(mock_gemini, mock_ocr, known_brands, known_models):
    mock_ocr.return_value = "Size label US 10.5"
    mock_gemini.return_value = "This is a Nike Air Jordan 1. The condition is 9/10."

    query = analyze_shoe_photo("dummy_path.jpg", known_brands, known_models)

    assert query is not None
    assert query.brand == "Nike"
    assert query.model_name == "Air Jordan 1"
    assert query.size == 10.5
    assert query.size_unit == "US"
    assert query.condition_score == 9
    assert query.source == "photo"
    assert query.confidence == 1.0
    assert "US 10.5" in query.raw_input
    assert "Nike Air Jordan 1" in query.raw_input


@patch("vision.photo_analyzer.run_ocr")
@patch("vision.photo_analyzer.ask_gemini_about_shoe")
def test_analyze_shoe_photo_no_match(mock_gemini, mock_ocr, known_brands, known_models):
    mock_ocr.return_value = "Random label"
    mock_gemini.return_value = "I cannot identify this shoe. It is in bad condition."

    query = analyze_shoe_photo("dummy_path.jpg", known_brands, known_models)

    assert query is None
