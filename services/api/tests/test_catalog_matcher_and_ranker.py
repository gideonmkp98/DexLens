import time
from unittest.mock import AsyncMock, patch

import cv2
import httpx
import numpy as np
import pytest

from app.services.catalog.matcher import (
    CatalogUnavailableError,
    retrieve_and_rank_candidates,
)
from app.services.catalog.ranker import (
    CandidateMatch,
    derive_confidence_state,
    rank_card_candidate,
)
from app.services.catalog.visual_matcher import _cache, rerank_by_artwork
from app.services.tcgdex import TcgdexConnectionError


def test_rank_exact_number_and_name_match():
    card = {
        "id": "base1-58",
        "name": "Pikachu",
        "localId": "58",
        "set": {"id": "base1", "name": "Base Set"},
        "image": "https://assets.tcgdex.net/en/base/base1/58",
    }
    match = rank_card_candidate(
        card_data=card,
        query_name="Pikachu",
        query_number="58/102",
        query_alternatives=["58", "058"],
    )
    assert match.score >= 80
    assert any("collector number" in r.lower() for r in match.reasons)
    assert any("name match" in r.lower() for r in match.reasons)
    assert match.image_url == "https://assets.tcgdex.net/en/base/base1/58/low.webp"


def test_rank_same_number_different_sets():
    # Card 1: Base Set Pikachu #58
    card1 = {
        "id": "base1-58",
        "name": "Pikachu",
        "localId": "58",
        "set": {"id": "base1", "name": "Base Set"},
    }
    # Card 2: Jungle Primeape #58
    card2 = {
        "id": "base2-58",
        "name": "Primeape",
        "localId": "58",
        "set": {"id": "base2", "name": "Jungle"},
    }

    match1 = rank_card_candidate(
        card_data=card1,
        query_name="Pikachu",
        query_number="58/102",
    )
    match2 = rank_card_candidate(
        card_data=card2,
        query_name="Pikachu",
        query_number="58/102",
    )

    # Pikachu should score significantly higher than Primeape even though both are #58
    assert match1.score > match2.score
    assert any("name differs" in r.lower() for r in match2.reasons)


def test_rank_same_name_different_numbers():
    # Charizard #4
    card1 = {
        "id": "base1-4",
        "name": "Charizard",
        "localId": "4",
        "set": {"id": "base1", "name": "Base Set"},
    }
    # Charizard #100
    card2 = {
        "id": "other-100",
        "name": "Charizard",
        "localId": "100",
        "set": {"id": "other", "name": "Other Set"},
    }

    match1 = rank_card_candidate(
        card_data=card1,
        query_name="Charizard",
        query_number="4/102",
    )
    match2 = rank_card_candidate(
        card_data=card2,
        query_name="Charizard",
        query_number="4/102",
    )

    assert match1.score > match2.score
    assert any("number differs" in r.lower() for r in match2.reasons)


def test_rank_missing_image_handled_gracefully():
    card = {
        "id": "promo-1",
        "name": "Pikachu",
        "localId": "1",
        "image": None,
    }
    match = rank_card_candidate(
        card_data=card,
        query_name="Pikachu",
        query_number="1",
    )
    assert match.image_url is None
    assert match.score > 0


@pytest.mark.asyncio
async def test_retrieve_and_rank_candidates_success():
    client = AsyncMock()
    client.get_cards_search.return_value = [
        {
            "id": "base1-58",
            "name": "Pikachu",
            "localId": "58",
            "set": {"id": "base1", "name": "Base Set"},
            "image": "https://assets.tcgdex.net/en/base/base1/58",
        },
        {
            "id": "basep-1",
            "name": "Pikachu",
            "localId": "1",
            "set": {"id": "basep", "name": "Wizards Black Star Promos"},
        },
    ]

    candidates, total = await retrieve_and_rank_candidates(
        client=client,
        name="Pikachu",
        number="58/102",
        limit=5,
    )
    assert total == 2
    assert len(candidates) == 2
    assert candidates[0].id == "base1-58"
    assert candidates[0].score > candidates[1].score


@pytest.mark.asyncio
async def test_retrieve_and_rank_candidates_empty_query():
    client = AsyncMock()
    candidates, total = await retrieve_and_rank_candidates(
        client=client,
        name=None,
        number=None,
    )
    assert candidates == []
    assert total == 0
    client.get_cards_search.assert_not_called()


@pytest.mark.asyncio
async def test_retrieve_and_rank_candidates_provider_failure():
    client = AsyncMock()
    client.get_cards_search.side_effect = TcgdexConnectionError("Connection timed out")

    with pytest.raises(CatalogUnavailableError):
        await retrieve_and_rank_candidates(
            client=client,
            name="Charizard",
            number="4/102",
        )


def test_gastly_not_displaced_by_unrelated_number_match():
    """A weak number (3) must NOT displace a credible name match (Gastly).

    Yanma (#3) has 0 name correlation and must be penalized heavily, while Gastly (#048)
    must score well on name agreement despite not matching the weak number.
    """
    gastly_card = {
        "id": "me03-048",
        "name": "Gastly",
        "localId": "048",
        "set": {
            "id": "me03",
            "name": "Perfect Order",
            "cardCount": {"official": 88, "total": 124},
        },
    }
    yanma_card = {
        "id": "neo2-3",
        "name": "Yanma",
        "localId": "3",
        "set": {
            "id": "neo2",
            "name": "Neo Discovery",
            "cardCount": {"official": 75, "total": 75},
        },
    }

    match_gastly = rank_card_candidate(
        card_data=gastly_card,
        query_name="Gastly se",
        query_number="3",
        name_hypotheses=["Gastly", "Gastly se"],
        name_confidence="high",
        number_strength="weak",
    )
    match_yanma = rank_card_candidate(
        card_data=yanma_card,
        query_name="Gastly se",
        query_number="3",
        name_hypotheses=["Gastly", "Gastly se"],
        name_confidence="high",
        number_strength="weak",
    )

    assert match_gastly.score >= 35
    assert match_yanma.score == 0
    assert match_gastly.score > match_yanma.score
    assert any("name match" in r.lower() for r in match_gastly.reasons)
    assert any("card name differs" in r.lower() for r in match_yanma.reasons)


def test_steelix_noisy_name_ranks_above_noise():
    """'ad Steelix eee 4' must recognize Steelix despite noise words."""
    steelix_card = {
        "id": "ex7-10",
        "name": "Dark Steelix",
        "localId": "10",
        "set": {"id": "ex7", "name": "Team Rocket Returns"},
    }
    match = rank_card_candidate(
        card_data=steelix_card,
        query_name="ad Steelix eee 4",
        query_number=None,
        name_hypotheses=["Steelix", "ad Steelix eee 4"],
        name_confidence="medium",
        number_strength="none",
    )
    assert match.score >= 30
    assert any("name" in r.lower() for r in match.reasons)


@pytest.mark.asyncio
async def test_weak_number_does_not_trigger_unconstrained_number_query():
    """Weak numbers (e.g. single digit '3') must not flood the candidate pool."""
    client = AsyncMock()
    client.get_cards_search.return_value = []

    await retrieve_and_rank_candidates(
        client=client,
        name="Gastly se",
        number="3",
        name_hypotheses=["Gastly", "Gastly se"],
        name_confidence="high",
        number_strength="weak",
    )

    # Check that get_cards_search was NOT called with standalone local_id='3'
    for call in client.get_cards_search.call_args_list:
        kwargs = call.kwargs
        if "local_id" in kwargs and "name" not in kwargs:
            pytest.fail(
                "Unconstrained number-only search was triggered for a weak number!"
            )


def test_derive_confidence_state():
    from app.services.catalog.ranker import CandidateMatch, derive_confidence_state

    # High confidence: strong score with verified denominator
    high_cand = [
        CandidateMatch(
            id="base1-58",
            name="Pikachu",
            local_id="58",
            set_id="base1",
            set_name="Base Set",
            image_url=None,
            score=95,
            reasons=[
                "Exact card name match ('Pikachu')",
                "Full number and denominator match (58/102)",
            ],
        )
    ]
    assert derive_confidence_state(high_cand) == "high"

    # Medium confidence: name matched, but number unverified
    med_cand = [
        CandidateMatch(
            id="me03-048",
            name="Gastly",
            local_id="048",
            set_id="me03",
            set_name="Perfect Order",
            image_url=None,
            score=40,
            reasons=[
                "Name closely matches ('Gastly')",
                "Collector number could not be read reliably",
            ],
        )
    ]
    assert derive_confidence_state(med_cand) == "medium"

    # Low confidence: empty or weak score
    low_cand = [
        CandidateMatch(
            id="unknown-1",
            name="Unknown",
            local_id="1",
            set_id="unknown",
            set_name="Unknown",
            image_url=None,
            score=15,
            reasons=["Weak match"],
        )
    ]
    assert derive_confidence_state(low_cand) == "low"
    assert derive_confidence_state([]) == "low"


def test_rank_attack_matching():
    card = {
        "id": "base1-4",
        "name": "Charizard",
        "localId": "4",
        "set": {"id": "base1", "name": "Base Set"},
        "attacks": [
            {
                "name": "Fire Spin",
                "cost": ["Fire", "Fire", "Fire", "Fire"],
                "damage": "100",
            },
            {
                "name": "Powerful Rage",
                "cost": ["Colorless", "Colorless"],
                "damage": "20x",
            },
        ],
    }
    match = rank_card_candidate(
        card_data=card,
        query_name="Charizard",
        query_number="4/102",
        extracted_attacks=["Powerful Rage"],
    )
    assert "Powerful Rage" in match.matched_attacks
    assert any("Attack matches ('Powerful Rage')" in r for r in match.reasons)
    # Attack match adds +20 points
    match_no_attack = rank_card_candidate(
        card_data=card,
        query_name="Charizard",
        query_number="4/102",
        extracted_attacks=[],
    )
    assert match.score >= match_no_attack.score + 20 or match.score == 100


def test_rank_ability_matching():
    card = {
        "id": "base1-4",
        "name": "Charizard",
        "localId": "4",
        "set": {"id": "base1", "name": "Base Set"},
        "abilities": [
            {"name": "Energy Burn", "type": "Pokémon Power", "effect": "..."}
        ],
    }
    match = rank_card_candidate(
        card_data=card,
        query_name="Charizard",
        query_number="4/102",
        extracted_abilities=["Energy Burn"],
    )
    assert "Energy Burn" in match.matched_abilities
    assert any("Ability matches ('Energy Burn')" in r for r in match.reasons)


def test_rank_hp_matching():
    card = {
        "id": "sv3pt5-6",
        "name": "Charizard ex",
        "localId": "6",
        "hp": 330,
        "set": {"id": "sv3pt5", "name": "151"},
    }
    match = rank_card_candidate(
        card_data=card,
        query_name="Charizard ex",
        query_number="006/165",
        extracted_hp="330",
    )
    assert match.hp == "330"
    assert any("HP matches (330)" in r for r in match.reasons)


def test_strong_number_fallback_with_noisy_name():
    """When number is strong but name is noise ('Str 2'), raw_text rescues card."""
    card = {
        "id": "base1-1",
        "name": "Alakazam",
        "localId": "1",
        "set": {
            "id": "base1",
            "name": "Base Set",
            "cardCount": {"official": 102, "total": 102},
        },
        "hp": 80,
        "attacks": [{"name": "Confuse Ray", "damage": "30"}],
        "abilities": [{"name": "Damage Swap", "type": "Pokémon Power"}],
    }
    raw_ocr_text = "Str 2\nAlakazam 80 HP\nDamage Swap\nConfuse Ray 30\n1/102"
    match = rank_card_candidate(
        card_data=card,
        query_name="Str 2",
        query_number="1/102",
        number_strength="strong",
        name_confidence="low",
        raw_text=raw_ocr_text,
        extracted_hp="80",
        extracted_attacks=["Confuse Ray"],
        extracted_abilities=["Damage Swap"],
    )
    assert match.score >= 90
    assert "Confuse Ray" in match.matched_attacks
    assert "Damage Swap" in match.matched_abilities
    assert any("Confuse Ray" in r for r in match.reasons)
    assert any("Damage Swap" in r for r in match.reasons)
    assert not any("differs from query" in r for r in match.reasons)


def test_printed_set_size_secret_rares_semantics():
    """Printed denominator (165) matches official count (165), not total (207)."""
    card = {
        "id": "sv3pt5-198",
        "name": "Venusaur ex",
        "localId": "198",
        "set": {
            "id": "sv3pt5",
            "name": "151",
            "cardCount": {"official": 165, "total": 207},
        },
    }
    match = rank_card_candidate(
        card_data=card,
        query_name="Venusaur ex",
        query_number="198/165",
    )
    assert any(
        "Full number and denominator match (198/165)" in r for r in match.reasons
    )
    assert match.score >= 80


@pytest.mark.asyncio
async def test_retrieve_and_rank_candidates_deterministic_enrichment():
    client = AsyncMock()
    # Initial search returns shallow summary
    client.get_cards_search.return_value = [
        {
            "id": "base1-4",
            "name": "Charizard",
            "localId": "4",
            "image": "https://assets.tcgdex.net/en/base/base1/4",
        }
    ]
    # get_card returns enriched details
    client.get_card.return_value = {
        "id": "base1-4",
        "name": "Charizard",
        "localId": "4",
        "hp": 120,
        "attacks": [{"name": "Fire Spin", "damage": "100"}],
        "abilities": [{"name": "Energy Burn"}],
        "set": {
            "id": "base1",
            "name": "Base Set",
            "cardCount": {"official": 102, "total": 102},
        },
        "releaseDate": "1999-01-09",
    }
    client.get_set.return_value = {
        "id": "base1",
        "name": "Base Set",
        "cardCount": {"official": 102, "total": 102},
    }

    candidates, total = await retrieve_and_rank_candidates(
        client=client,
        name="Charizard",
        number="4/102",
        hp="120",
        attacks=["Fire Spin"],
        abilities=["Energy Burn"],
    )

    assert total == 1
    assert len(candidates) == 1
    c = candidates[0]
    assert c.id == "base1-4"
    assert c.hp == "120"
    assert "Fire Spin" in c.matched_attacks
    assert "Energy Burn" in c.matched_abilities
    assert any("Attack matches ('Fire Spin')" in r for r in c.reasons)
    assert any("Ability matches ('Energy Burn')" in r for r in c.reasons)
    assert any("HP matches (120)" in r for r in c.reasons)
    client.get_card.assert_called_with("base1-4")


@pytest.mark.asyncio
async def test_retrieve_and_rank_candidates_tie_breaking():
    client = AsyncMock()
    client.get_cards_search.return_value = [
        {
            "id": "xy12-11",
            "name": "Charizard",
            "localId": "11",
            "set": {"id": "xy12", "name": "Evolutions"},
            "releaseDate": "2016-11-02",
        },
        {
            "id": "base1-4",
            "name": "Charizard",
            "localId": "4",
            "set": {"id": "base1", "name": "Base Set"},
            "releaseDate": "1999-01-09",
        },
    ]
    client.get_card.return_value = None

    candidates, _ = await retrieve_and_rank_candidates(
        client=client,
        name="Charizard",
        number=None,
    )
    assert len(candidates) == 2
    assert candidates[0].score == candidates[1].score
    # Earlier release date (1999-01-09) must sort before later (2016-11-02)
    assert candidates[0].id == "base1-4"
    assert candidates[1].id == "xy12-11"


@pytest.mark.asyncio
async def test_visual_matcher_artwork_normal_and_180_rotation(tmp_path):
    # Synthetic image with colored artwork in the center
    img = np.zeros((300, 200, 3), dtype=np.uint8)
    img[50:150, 20:180] = [0, 120, 255]

    # Rotate 180 degrees to test orientation handling
    rotated_scan = cv2.rotate(img, cv2.ROTATE_180)
    crop_path = tmp_path / "crop.jpg"
    cv2.imwrite(str(crop_path), rotated_scan)

    cand = CandidateMatch(
        id="base1-4",
        name="Charizard",
        local_id="4",
        set_id="base1",
        set_name="Base Set",
        image_url="https://assets.tcgdex.net/en/base/base1/4/low.webp",
        score=70,
        reasons=["Exact card name match ('Charizard')"],
    )

    # Seed cache with thumbnail
    thumbnail = cv2.resize(img, (150, 210))
    _cache[cand.image_url] = (time.monotonic(), thumbnail)

    reranked = await rerank_by_artwork(crop_path, [cand])
    assert reranked[0].visual_similarity is not None
    assert reranked[0].visual_similarity >= 0.65
    assert reranked[0].score > 70
    assert any("Artwork resembles the scan" in r for r in reranked[0].reasons)


@pytest.mark.asyncio
async def test_visual_matcher_preserves_score_on_network_failure(tmp_path):
    crop_path = tmp_path / "crop.jpg"
    cv2.imwrite(str(crop_path), np.zeros((300, 200, 3), dtype=np.uint8))

    cand = CandidateMatch(
        id="base1-4",
        name="Charizard",
        local_id="4",
        set_id="base1",
        set_name="Base Set",
        image_url="https://assets.tcgdex.net/en/base/base1/4/low.webp",
        score=70,
        reasons=["Exact card name match ('Charizard')"],
    )
    with patch(
        "httpx.AsyncClient.stream",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        reranked = await rerank_by_artwork(crop_path, [cand])
    # Score must be preserved untouched
    assert reranked[0].score == 70


def test_derive_confidence_state_attack_and_visual():
    # Score >= 75 with attack match and visual agreement -> high
    cand_high = [
        CandidateMatch(
            id="base1-4",
            name="Charizard",
            local_id="4",
            set_id="base1",
            set_name="Base Set",
            image_url=None,
            score=80,
            reasons=[
                "Exact card name match ('Charizard')",
                "Attack matches ('Fire Spin')",
                "Artwork resembles the scan; printing still requires confirmation",
            ],
            matched_attacks=["Fire Spin"],
            visual_similarity=0.85,
        )
    ]
    assert derive_confidence_state(cand_high) == "high"

    # Score >= 75 but is_low_res=True -> low
    assert derive_confidence_state(cand_high, is_low_res=True) == "low"

    # Score >= 75 but conflicting fields -> low
    cand_conflict = [
        CandidateMatch(
            id="base1-4",
            name="Charizard",
            local_id="4",
            set_id="base1",
            set_name="Base Set",
            image_url=None,
            score=75,
            reasons=[
                "Exact card name match ('Charizard')",
                "Card number differs from query (4 vs 100)",
            ],
        )
    ]
    assert derive_confidence_state(cand_conflict) == "low"
