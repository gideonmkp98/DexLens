import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.services.catalog.ranker import rank_card_candidate
from app.services.ocr.engine import OcrResult, get_ocr_engine
from app.services.ocr.normalizer import normalize_card_name
from app.services.ocr.pipeline import recognize_card_image

FIXTURES = Path(__file__).parent / "fixtures" / "regression_scans"


@pytest.mark.parametrize(
    "header,expected",
    [
        ("Basic Pokémon\n\nPikachu\n\n50.H\n\noa", "Pikachu"),
        ("Basic Pokemon Pikachu HP 50", "Pikachu"),
        ("STAGE 2\nCharizard ex HP 330", "Charizard ex"),
        ("Pokémon", None),
        ("BASIC POKEMON", None),
        ("Pokémon Center Lady", "Pokémon Center Lady"),
        ("Rayquaza VMAX", "Rayquaza VMAX"),
    ],
)
def test_name_line_selection(header, expected):
    assert normalize_card_name(header) == expected


def test_vintage_photo_uses_clean_header_and_number_corner(tmp_path):
    """OCR transcripts from the failing Jungle Pikachu scan, not a name lookup."""
    path = tmp_path / "card.jpg"
    Image.new("RGB", (620, 866), "white").save(path)
    engine = MagicMock()
    engine.recognize.side_effect = [
        OcrResult("", 0),
        OcrResult("retreat cost\nLV.14 #25", 53),
        OcrResult("Basic Pokémon\n\nPikachu\n\n50.H\n\noa", 78),
        OcrResult("storms LV.14 SSP\n©1999 Wizards 60/64", 49),
        OcrResult("Spark If your opponent has any Benched Pokémon...", 80),
    ]
    result = recognize_card_image(path, engine)
    assert result.name == "Pikachu"
    assert result.number == "60/64"
    assert result.set_code is None
    assert "Spark" in result.attacks
    assert "[Header sparse]" in result.raw_text
    assert engine.recognize.call_count == 5
    assert (
        len({call.kwargs["deadline"] for call in engine.recognize.call_args_list}) == 1
    )


def test_clear_modern_card_does_not_need_extra_passes(tmp_path):
    path = tmp_path / "card.jpg"
    Image.new("RGB", (600, 840), "white").save(path)
    engine = MagicMock()
    engine.recognize.side_effect = [
        OcrResult("Charizard ex HP 330", 92),
        OcrResult("MEW 199/165", 90),
        OcrResult("Slash 60\nInferno X 330", 88),
    ]
    result = recognize_card_image(path, engine)
    assert (result.name, result.number, result.set_code) == (
        "Charizard ex",
        "199/165",
        "MEW",
    )
    assert result.hp == "330"
    assert result.attacks == ["Slash", "Inferno X"]
    assert engine.recognize.call_count == 3


def test_pipeline_extracts_attacks_and_abilities(tmp_path):
    path = tmp_path / "card.jpg"
    Image.new("RGB", (600, 840), "white").save(path)
    engine = MagicMock()
    engine.recognize.side_effect = [
        OcrResult("Pidgeot ex HP 280", 95),
        OcrResult("OBF 164/197", 92),
        OcrResult(
            "Ability: Quick Search\n"
            "Once during your turn, you may search your deck for a card.\n"
            "() () () Air Slash 120",
            89,
        ),
    ]
    result = recognize_card_image(path, engine)
    assert result.name == "Pidgeot ex"
    assert result.hp == "280"
    assert result.number == "164/197"
    assert result.abilities == ["Quick Search"]
    assert result.attacks == ["Air Slash"]
    assert result.source_regions.get("attacks") == "body"
    assert result.source_regions.get("abilities") == "body"


def test_pipeline_extracts_hp_from_hp_roi_when_not_in_header(tmp_path):
    path = tmp_path / "card.jpg"
    Image.new("RGB", (600, 840), "white").save(path)
    engine = MagicMock()
    engine.recognize.side_effect = [
        OcrResult("Steelix", 85),
        OcrResult("8/100", 80),
        OcrResult("** Powerful Rage 20\n22+ Earthquake 180", 85),
        OcrResult("190 HP", 88),
    ]
    result = recognize_card_image(path, engine)
    assert result.name == "Steelix"
    assert result.hp == "190"
    assert result.attacks == ["Powerful Rage", "Earthquake"]
    assert result.source_regions.get("hp") == "hp_roi"


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract required")
def test_real_photo_verification_charizard():
    result = recognize_card_image(FIXTURES / "charizard.jpg", get_ocr_engine())
    assert "charizard" in [n.lower() for n in result.name_hypotheses]
    assert result.number == "4/130"
    assert "Energy Burn" in result.abilities or "Energy Burn" in result.attacks
    assert "Fire Spin" in result.attacks
    assert result.hp in {"120", None}


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract required")
def test_real_photo_verification_gastly():
    result = recognize_card_image(FIXTURES / "gastly.jpg", get_ocr_engine())
    assert "gastly" in [n.lower() for n in result.name_hypotheses]
    assert result.number == "048/088"
    assert "Surprise Attack" in result.attacks


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract required")
def test_real_photo_verification_pikachu():
    result = recognize_card_image(FIXTURES / "pikachu.jpg", get_ocr_engine())
    assert "pikachu" in [n.lower() for n in result.name_hypotheses]
    assert result.number == "60/64"
    assert "Spark" in result.attacks
    assert result.hp in {"50", "60"}


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract required")
def test_real_photo_verification_steelix():
    result = recognize_card_image(FIXTURES / "steelix.jpg", get_ocr_engine())
    assert "steelix" in [n.lower() for n in result.name_hypotheses]
    assert (
        result.hp == "190"
        or "Powerful Rage" in result.attacks
        or "Earthquake" in result.attacks
    )


def test_generic_pokemon_label_is_not_positive_name_evidence():
    candidate = {"id": "swsh3.5-60", "name": "Pokémon Center Lady", "localId": "60"}
    result = rank_card_candidate(candidate, "Pokémon", "60/64")
    assert result.score == 42
    assert not any("name match" in reason.lower() for reason in result.reasons)
    assert any("unverified" in reason for reason in result.reasons)
