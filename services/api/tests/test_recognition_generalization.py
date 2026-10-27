"""Regressions from newly supplied scans, not hardcoded recognition rules."""

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from app.services.catalog.matcher import retrieve_and_rank_candidates
from app.services.catalog.provider_cache import CachedRecognitionCatalog
from app.services.catalog.ranker import derive_confidence_state, rank_card_candidate
from app.services.catalog.set_resolver import resolve_printed_set_code
from app.services.detail_cache import DetailCache
from app.services.ocr.engine import OcrResult, OcrTimeoutError, TesseractOcrEngine
from app.services.ocr.normalizer import normalize_collector_number
from app.services.ocr.pipeline import recognize_card_image


def test_words_after_promo_prefix_are_not_collector_numbers():
    assert normalize_collector_number("BW thts") is None


def test_optional_ocr_timeout_preserves_primary_evidence(tmp_path):
    path = tmp_path / "card.jpg"
    Image.new("RGB", (600, 840), "white").save(path)
    engine = MagicMock()
    engine.recognize.side_effect = [
        OcrResult("Pikachu HP 50", 95),
        OcrResult("60/64", 95),
        OcrTimeoutError("Optional body pass timed out"),
    ]
    result = recognize_card_image(path, engine)
    assert result.name == "Pikachu"
    assert result.number == "60/64"
    assert "tijdslimiet" in result.image_quality["warning"]


@pytest.mark.parametrize(
    "printed,provider",
    [
        ("MEW", "sv03.5"),
        ("SVI", "sv01"),
        ("PAF", "sv04.5"),
        ("SCR", "sv07"),
        ("SSP", "sv08"),
        ("PRE", "sv08.5"),
        ("CRZ", "swsh12.5"),
        ("PGO", "swsh10.5"),
    ],
)
def test_printed_codes_use_actual_tcgdex_identifiers(printed, provider):
    assert resolve_printed_set_code(printed) == provider


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Requires real Tesseract")
@pytest.mark.parametrize(
    "file,name,number",
    [
        ("geodude-fossil.jpg", "Geodude", "47/62"),
        ("meganium-prime.jpg", "Meganium", "109/123"),
        ("meganium-lost-thunder.jpg", "Meganium", "8/214"),
    ],
)
def test_new_scan_actual_ocr(file, name, number):
    result = recognize_card_image(
        Path(__file__).parent / "fixtures" / "regression_scans" / file,
        TesseractOcrEngine(),
    )
    assert result.name == name
    assert result.number == number


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Requires real Tesseract")
@pytest.mark.parametrize(
    "card_id,number", [("swsh8-157", "157/264"), ("xy12-101", "101/108")]
)
def test_full_art_footer_keeps_complete_denominator(card_id, number):
    result = recognize_card_image(
        Path(__file__).parent / "fixtures" / "additional_catalog" / f"{card_id}.webp",
        TesseractOcrEngine(),
    )
    assert result.number == number


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Requires real Tesseract")
@pytest.mark.parametrize(
    "card_id,name,number",
    [
        ("base1-53", "Magnemite", "53/102"),
        ("hgss1-110", "Typhlosion", "110/123"),
        ("swsh8-225", "Battle VIP Pass", "225/264"),
    ],
)
def test_wide_title_preserves_name_instead_of_clipped_fragment(card_id, name, number):
    result = recognize_card_image(
        Path(__file__).parent / "fixtures" / "additional_catalog" / f"{card_id}.webp",
        TesseractOcrEngine(),
    )
    assert result.name == name
    assert result.number == number


@pytest.mark.asyncio
async def test_denominator_recovers_card_even_when_name_search_fails():
    client = AsyncMock()
    client.get_sets.return_value = [
        {"id": "sm8", "name": "Lost Thunder", "cardCount": {"official": 214}},
        {"id": "base1", "name": "Base", "cardCount": {"official": 102}},
    ]
    card = {"id": "sm8-8", "localId": "8", "name": "Meganium"}
    client.get_set.return_value = {"id": "sm8", "cards": [card]}
    client.get_cards_search.return_value = []
    client.get_card.return_value = {**card, "attacks": [{"name": "Solar Beam"}]}
    candidates, _ = await retrieve_and_rank_candidates(
        client,
        name="vace2 Meganiu",
        number="8/214",
        name_confidence="low",
        attacks=["Solar Beam"],
    )
    assert candidates[0].id == "sm8-8"
    client.get_set.assert_awaited_once_with("sm8")
    assert any("denominator match" in r for r in candidates[0].reasons)


@pytest.mark.asyncio
async def test_name_search_continues_beyond_first_provider_page():
    client = AsyncMock()
    client.get_sets.return_value = []
    client.get_card.return_value = None
    client.get_set.return_value = None
    first_page = [
        {"id": f"set-{i}", "localId": str(i), "name": "Pikachu"} for i in range(100)
    ]
    target = {"id": "new-200", "localId": "200", "name": "Pikachu"}

    async def search(**kwargs):
        if kwargs.get("name") and "local_id" not in kwargs:
            return first_page if kwargs.get("page") == 1 else [target]
        return []

    client.get_cards_search.side_effect = search
    candidates, _ = await retrieve_and_rank_candidates(
        client, name="Pikachu", number="200"
    )
    assert candidates[0].id == "new-200"
    assert any(
        call.kwargs.get("page") == 2 for call in client.get_cards_search.await_args_list
    )


def test_shared_attacks_and_hp_cannot_override_wrong_printed_denominator():
    def rank(sid, denominator):
        return rank_card_candidate(
            {
                "id": f"{sid}-4",
                "localId": "4",
                "name": "Charizard",
                "hp": 120,
                "set": {"id": sid, "cardCount": {"official": denominator}},
                "attacks": [{"name": "Fire Spin"}],
                "abilities": [{"name": "Energy Burn"}],
            },
            query_name="Charizard",
            query_number="4/130",
            extracted_hp="120",
            extracted_attacks=["Fire Spin"],
            extracted_abilities=["Energy Burn"],
        )

    correct, wrong = rank("base4", 130), rank("base1", 102)
    assert correct.score > wrong.score + 25
    assert derive_confidence_state([wrong]) == "low"
    assert derive_confidence_state([correct, correct]) == "low"


@pytest.mark.asyncio
async def test_confirmed_number_candidate_survives_noisy_name_budget():
    client = AsyncMock()
    client.get_sets.return_value = [
        {"id": "right", "cardCount": {"official": 50}},
        {"id": "other", "cardCount": {"official": 102}},
    ]
    target = {"id": "right-1", "name": "Actual name", "localId": "1"}
    client.get_set.return_value = {"id": "right", "cards": [target]}
    client.get_card.return_value = None
    client.get_cards_search.return_value = [
        {"id": f"other-{i}", "localId": "1", "name": "Wrong"} for i in range(40)
    ]
    candidates, _ = await retrieve_and_rank_candidates(
        client, name="Wrong", number="1/50", limit=5
    )
    assert len(candidates) <= 5
    assert any(c.id == "right-1" for c in candidates)


@pytest.mark.asyncio
async def test_repeated_recognition_reuses_provider_metadata():
    client = AsyncMock()
    client.base_url = "https://example.test/v2"
    client.get_sets.return_value = [{"id": "test", "cardCount": {"official": 50}}]
    cached = CachedRecognitionCatalog(client, DetailCache(max_entries=4))
    assert await cached.get_sets() == await cached.get_sets()
    client.get_sets.assert_awaited_once()
