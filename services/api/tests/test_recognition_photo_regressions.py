"""Real photo regression test suite; no provider network calls in this suite.

Covers key regressions:
- Charizard: Base Set 2, 4/130, TCGdex ID base4-4
- Pikachu: Jungle, 60/64, TCGdex ID base2-60 (pikachu.jpg)
- Gastly: Perfect Order, 048/088, TCGdex ID me03-048 (gastly.jpg)
- Steelix: Fusion Strike, 139/264, TCGdex ID swsh8-139 (never ex7-10)
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import cv2
import httpx
import numpy as np
import pytest

from app.services.card_detector import detect_card_corners
from app.services.catalog import visual_matcher
from app.services.catalog.matcher import retrieve_and_rank_candidates
from app.services.catalog.ranker import CandidateMatch, rank_card_candidate
from app.services.catalog.visual_matcher import artwork_similarity
from app.services.crop_service import perform_crop_and_warp
from app.services.ocr.engine import get_ocr_engine
from app.services.ocr.pipeline import recognize_card_image

FIXTURES = Path(__file__).parent / "fixtures" / "regression_scans"


def test_printed_denominator_leading_zeros_are_not_a_conflict():
    candidate = rank_card_candidate(
        {
            "id": "me03-048",
            "name": "Gastly",
            "localId": "048",
            "set": {
                "id": "me03",
                "name": "Perfect Order",
                "cardCount": {"official": 88},
            },
        },
        "Gastly",
        "048/088",
    )
    assert candidate.score == 95
    assert any("denominator match" in reason for reason in candidate.reasons)


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract required")
@pytest.mark.parametrize(
    "photo,name,number",
    [
        ("charizard", "charizard", "4/130"),
        ("gastly", "gastly", "048/088"),
        ("pikachu", "pikachu", "60/64"),
        ("steelix", "steelix", None),
    ],
)
def test_real_photo_text(photo, name, number):
    result = recognize_card_image(FIXTURES / f"{photo}.jpg", get_ocr_engine())
    assert name in [n.lower() for n in result.name_hypotheses]
    if number:
        assert result.number == number
    else:
        assert result.number_strength in {"weak", "none"}
        assert result.name_confidence != "high"


def test_closeup_detection_includes_the_whole_card():
    found, corners, _, _ = detect_card_corners(FIXTURES / "charizard-original.jpg")
    assert found
    # The previous detector selected only the illustration (bottom y < .48).
    assert corners.top_left.x < 0.1
    assert corners.top_right.x > 0.9
    assert corners.bottom_left.y > 0.94
    assert corners.bottom_right.y > 0.94


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract required")
def test_charizard_closeup_crop_retains_title_and_footer():
    """Close-up detection on charizard-original.jpg must retain title and footer."""
    orig_path = FIXTURES / "charizard-original.jpg"
    found, corners, _, _ = detect_card_corners(orig_path)
    assert found
    assert corners.top_left.x < 0.10
    assert corners.top_right.x > 0.90
    assert corners.bottom_left.y > 0.90
    assert corners.bottom_right.y > 0.90

    with tempfile.TemporaryDirectory() as tmpdir:
        crop_dest = Path(tmpdir) / "charizard_crop.jpg"
        w, h, sz = perform_crop_and_warp(orig_path, crop_dest, corners)
        assert w > 400 and h > 550

        # Perform OCR recognition on the cropped card
        rec = recognize_card_image(crop_dest, get_ocr_engine())
        assert "charizard" in [h.lower() for h in rec.name_hypotheses]
        assert rec.number == "4/130"
        assert rec.local_id == "4"

        # Candidate ranking must rank Base Set 2 (base4-4) as exact rank 1 match
        base4_match = rank_card_candidate(
            {
                "id": "base4-4",
                "name": "Charizard",
                "localId": "4",
                "set": {
                    "id": "base4",
                    "name": "Base Set 2",
                    "cardCount": {"official": 130},
                },
            },
            rec.name,
            rec.number,
            name_hypotheses=rec.name_hypotheses,
        )
        base1_match = rank_card_candidate(
            {
                "id": "base1-4",
                "name": "Charizard",
                "localId": "4",
                "set": {
                    "id": "base1",
                    "name": "Base Set",
                    "cardCount": {"official": 102},
                },
            },
            rec.name,
            rec.number,
            name_hypotheses=rec.name_hypotheses,
        )
        assert base4_match.score >= 90
        assert base1_match.score < base4_match.score
        assert any("denominator match" in r.lower() for r in base4_match.reasons)
        assert any("denominator conflict" in r.lower() for r in base1_match.reasons)


@pytest.mark.asyncio
async def test_charizard_base4_4_ranked_first_over_base1_4():
    """Verify Charizard 4/130 specifically resolves to Base Set 2 (base4-4)."""
    client = AsyncMock()
    client.get_cards_search.return_value = [
        {"id": "base1-4", "name": "Charizard", "localId": "4"},
        {"id": "base4-4", "name": "Charizard", "localId": "4"},
    ]

    async def get_set(sid):
        counts = {"base1": 102, "base4": 130}
        return {
            "id": sid,
            "name": "Base Set 2" if sid == "base4" else "Base Set",
            "cardCount": {"official": counts.get(sid, 100)},
        }

    client.get_set.side_effect = get_set
    ranked, _ = await retrieve_and_rank_candidates(client, "Charizard", "4/130")
    assert len(ranked) >= 2
    assert ranked[0].id == "base4-4"
    assert ranked[0].set_name == "Base Set 2"
    assert ranked[0].score > ranked[1].score


@pytest.mark.asyncio
async def test_gastly_me03_048_ranked_first():
    """Verify Gastly 048/088 specifically resolves to Perfect Order (me03-048)."""
    client = AsyncMock()
    client.get_cards_search.return_value = [
        {"id": "me03-048", "name": "Gastly", "localId": "048"},
        {"id": "base1-50", "name": "Gastly", "localId": "50"},
    ]

    async def get_set(sid):
        return {
            "id": sid,
            "name": "Perfect Order" if sid == "me03" else sid,
            "cardCount": {"official": 88 if sid == "me03" else 102},
        }

    client.get_set.side_effect = get_set
    ranked, _ = await retrieve_and_rank_candidates(client, "Gastly", "048/088")
    assert len(ranked) >= 1
    assert ranked[0].id == "me03-048"
    assert ranked[0].score >= 95


@pytest.mark.asyncio
async def test_best_number_candidates_are_enriched_even_when_retrieved_last():
    client = AsyncMock()
    client.get_cards_search.return_value = [
        {"id": f"other{i}-1", "name": "Pikachu", "localId": "1"} for i in range(30)
    ] + [
        {"id": "ex9-60", "name": "Pikachu", "localId": "60"},
        {"id": "base2-60", "name": "Pikachu", "localId": "60"},
    ]

    async def get_set(sid):
        return {
            "id": sid,
            "name": sid,
            "cardCount": {
                "official": 64 if sid == "base2" else 106,
            },
        }

    client.get_set.side_effect = get_set
    ranked, _ = await retrieve_and_rank_candidates(client, "Pikachu", "60/64")
    assert ranked[0].id == "base2-60"
    assert ranked[0].score > next(c.score for c in ranked if c.id == "ex9-60")
    assert len(client.get_set.call_args_list) <= 10


def test_visual_evidence_requires_spatial_agreement_not_just_card_colour():
    image = cv2.imread(str(FIXTURES / "steelix.jpg"))
    thumbnail = cv2.resize(image, (150, 210))
    assert artwork_similarity(image, thumbnail) > 0.9
    assert artwork_similarity(image, np.full_like(image, 180)) == 0
    assert artwork_similarity(image, cv2.flip(image, 1)) < 0.65


@pytest.mark.asyncio
async def test_steelix_identified_as_fusion_strike_swsh8_139_not_ex7_10(monkeypatch):
    """Low-res Steelix crop must identify as Fusion Strike (swsh8-139), never ex7-10."""
    steelix_img = cv2.imread(str(FIXTURES / "steelix.jpg"))
    swsh8_bytes = cv2.imencode(".jpg", cv2.resize(steelix_img, (150, 210)))[1].tobytes()
    # ex7-10 is Dark Steelix from Team Rocket Returns with totally distinct artwork
    ex7_bytes = cv2.imencode(".jpg", np.full((210, 150, 3), 120, dtype=np.uint8))[
        1
    ].tobytes()

    def mock_transport_handler(request: httpx.Request):
        url = str(request.url)
        if "swsh8/139" in url:
            return httpx.Response(200, content=swsh8_bytes)
        elif "ex7/10" in url:
            return httpx.Response(200, content=ex7_bytes)
        return httpx.Response(404)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        visual_matcher.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(mock_transport_handler), **kwargs
        ),
    )
    visual_matcher._cache.clear()

    cand_swsh8 = CandidateMatch(
        id="swsh8-139",
        name="Steelix",
        local_id="139",
        set_id="swsh8",
        set_name="Fusion Strike",
        image_url="https://assets.tcgdex.net/en/swsh/swsh8/139/low.webp",
        score=45,
        reasons=["Exact card name match ('Steelix')"],
    )
    cand_ex7 = CandidateMatch(
        id="ex7-10",
        name="Dark Steelix",
        local_id="10",
        set_id="ex7",
        set_name="Team Rocket Returns",
        image_url="https://assets.tcgdex.net/en/ex/ex7/10/low.webp",
        score=35,
        reasons=["Name closely matches ('Dark Steelix')"],
    )
    cand_other = CandidateMatch(
        id="bw9-79",
        name="Steelix",
        local_id="79",
        set_id="bw9",
        set_name="Plasma Freeze",
        image_url="https://assets.tcgdex.net/en/bw/bw9/79/low.webp",
        score=45,
        reasons=["Exact card name match ('Steelix')"],
    )

    ranked = await visual_matcher.rerank_by_artwork(
        FIXTURES / "steelix.jpg",
        [cand_ex7, cand_other, cand_swsh8],
    )

    # swsh8-139 MUST be rank 1
    assert ranked[0].id == "swsh8-139"
    assert ranked[0].set_name == "Fusion Strike"
    assert ranked[0].score >= 65
    assert any("resembles the scan" in r for r in ranked[0].reasons)

    # MUST NOT be labeled ex7-10 (Dark Steelix)
    assert ranked[0].id != "ex7-10"
    assert not any(c.id == "ex7-10" for c in ranked[:1])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://assets.tcgdex.net/en/swsh/swsh8/139/low.webp",
        "http://localhost:8000/private",
    ],
)
async def test_optional_image_failure_preserves_text_candidates(monkeypatch, url):
    requests = []

    def fail(request):
        requests.append(request)
        raise httpx.ConnectError("offline")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        visual_matcher.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(fail), **kwargs),
    )
    visual_matcher._cache.clear()
    candidate = CandidateMatch(
        "swsh8-139",
        "Steelix",
        "139",
        "swsh8",
        "Fusion Strike",
        url,
        45,
        ["Exact card name match ('Steelix')"],
    )
    result = await visual_matcher.rerank_by_artwork(
        FIXTURES / "steelix.jpg",
        [candidate],
    )
    assert result[0].score == 45
    assert len(requests) == (1 if url.startswith("https://assets.tcgdex.net/") else 0)
