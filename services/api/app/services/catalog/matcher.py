import asyncio
import logging
import re
from typing import Any

from app.services.catalog.provider_cache import CachedRecognitionCatalog
from app.services.catalog.ranker import CandidateMatch, rank_card_candidate
from app.services.catalog.set_resolver import resolve_printed_set_code
from app.services.ocr.normalizer import generate_name_hypotheses, normalize_card_name
from app.services.tcgdex import (
    TcgdexClient,
    TcgdexConnectionError,
    TcgdexError,
    is_digital_card,
    is_digital_set,
)

logger = logging.getLogger(__name__)


class CatalogUnavailableError(Exception):
    """Raised when the catalog provider is unavailable or all queries fail."""


async def retrieve_and_rank_candidates(
    client: TcgdexClient | CachedRecognitionCatalog,
    name: str | None = None,
    number: str | None = None,
    set_code: str | None = None,
    set_id: str | None = None,
    alternatives: list[str] | None = None,
    name_hypotheses: list[str] | None = None,
    name_confidence: str = "medium",
    number_strength: str = "strong",
    limit: int = 5,
    hp: str | None = None,
    attacks: list[str] | None = None,
    abilities: list[str] | None = None,
    raw_text: str | None = None,
    extraction: Any = None,
    **kwargs: Any,
) -> tuple[list[CandidateMatch], int]:
    """Retrieve catalog cards via bounded TCGdex queries and return ranked candidates.

    Uses independent retrieval strategies (name hypotheses, verified number,
    targeted name+number intersection, set queries) to ensure weak numbers
    never prevent valid name candidates from entering the pool.
    Enriches top candidates with full card details (attacks, abilities, HP)
    and set metadata for verified scoring and deterministic tie-breaking.

    Returns:
        (top_candidates, total_found_count)
    """
    if extraction is not None:
        if hp is None:
            hp = getattr(extraction, "hp", None)
        if attacks is None:
            attacks = getattr(extraction, "attacks", None)
        if abilities is None:
            abilities = getattr(extraction, "abilities", None)
        if raw_text is None:
            raw_text = getattr(extraction, "raw_text", None)
    if hp is None and "extracted_hp" in kwargs:
        hp = kwargs["extracted_hp"]
    if attacks is None and "extracted_attacks" in kwargs:
        attacks = kwargs["extracted_attacks"]
    if abilities is None and "extracted_abilities" in kwargs:
        abilities = kwargs["extracted_abilities"]

    clean_name = normalize_card_name(name) if name else None
    category_labels = {
        "mega",
        "vmax",
        "vstar",
        "basic",
        "stage",
        "evolves",
        "trainer",
        "pokemon",
        "pokémon",
    }
    if clean_name and (
        len(clean_name) < 3 or clean_name.lower().strip("_ ") in category_labels
    ):
        clean_name = None
    clean_number = number.strip() if number and number.strip() else None
    clean_set_id = set_id.strip() if set_id and set_id.strip() else None
    clean_set_code = set_code.strip() if set_code and set_code.strip() else None

    # Nothing to search
    if not clean_name and not clean_number and not clean_set_id and not clean_set_code:
        return [], 0

    candidate_cards: dict[str, dict[str, Any]] = {}

    # 1. Resolve printed set code to provider set ID if explicit set_id was not passed
    effective_set_id = clean_set_id
    if not effective_set_id and clean_set_code:
        resolved = resolve_printed_set_code(clean_set_code)
        if resolved:
            effective_set_id = resolved

    # Prepare name hypotheses (up to 3)
    hypotheses = list(name_hypotheses) if name_hypotheses else []
    if clean_name:
        generated = generate_name_hypotheses(clean_name)
        for h in generated:
            if h not in hypotheses:
                hypotheses.append(h)
    hypotheses = [
        h
        for h in hypotheses
        if len(h) >= 3 and h.lower().strip("_ ") not in category_labels
    ][:3]

    async def search_name(hypothesis: str) -> list[dict[str, Any]]:
        # Popular Pokémon have more than one provider page of printings.
        # A bounded continuation prevents alphabetical first-page bias.
        cards = []
        for page in range(1, 4):
            batch = await client.get_cards_search(
                name=hypothesis, page=page, page_size=100
            )
            cards.extend(batch)
            if len(batch) < 100:
                break
        return cards

    set_index: dict[str, dict[str, Any]] = {}

    try:
        queries: list[Any] = []

        # Set summaries include the PRINTED count. This small metadata list
        # lets us find 8/214 even if the OCR name is damaged; no full catalog
        # download and no number-only first-page lottery are necessary.
        try:
            summaries = await client.get_sets()
            if isinstance(summaries, list):
                set_index = {
                    s["id"]: s
                    for s in summaries
                    if isinstance(s, dict) and s.get("id") and not is_digital_set(s)
                }
            if clean_number and "/" in clean_number and number_strength == "strong":
                numerator, denominator = clean_number.split("/", 1)
                matching_sets = [
                    sid
                    for sid, s in set_index.items()
                    if str(s.get("cardCount", {}).get("official"))
                    == denominator.lstrip("0")
                ]
                details = await asyncio.gather(
                    *(client.get_set(sid) for sid in matching_sets[:8]),
                    return_exceptions=True,
                )
                for detail in details:
                    if isinstance(detail, dict):
                        for card in detail.get("cards", []):
                            if str(card.get("localId", "")).lstrip(
                                "0"
                            ) == numerator.lstrip("0"):
                                candidate_cards[card["id"]] = dict(
                                    card, set=set_index[detail["id"]]
                                )
        except (TcgdexError, AttributeError) as err:
            logger.warning(
                "Set index unavailable; using independent name/number searches: %s", err
            )

        # Strategy 1: Filter by Set if set_id is provided or resolved
        if effective_set_id:
            try:
                set_data = await client.get_set(effective_set_id)
                if set_data and isinstance(set_data, dict) and "cards" in set_data:
                    for c in set_data.get("cards", []):
                        cid = c.get("id")
                        if cid and not is_digital_card(c):
                            c_copy = dict(c)
                            c_copy["set"] = {
                                "id": set_data.get("id"),
                                "name": set_data.get("name"),
                                "cardCount": set_data.get("cardCount"),
                            }
                            if "releaseDate" in set_data:
                                c_copy["releaseDate"] = set_data["releaseDate"]
                            candidate_cards[str(cid)] = c_copy
            except (TcgdexConnectionError, TcgdexError) as err:
                logger.warning(
                    "Set lookup for '%s' failed: %s; falling back.",
                    effective_set_id,
                    err,
                )

        # Strategy 2: Search by Name Hypotheses
        for hyp in hypotheses:
            queries.append(search_name(hyp))

        # Strategy 3: Search by Local ID / Number
        if clean_number:
            local_num = clean_number.split("/")[0].strip()

            # Targeted combination of name token + number is always safe
            if hypotheses:
                first_name_token = hypotheses[0].split()[0]
                queries.append(
                    client.get_cards_search(
                        name=first_name_token,
                        local_id=local_num,
                        page_size=24,
                    )
                )

            # Unconstrained number-only queries are run if number evidence
            # is credible (i.e. NOT weak single digits from retreat/damage/noise)
            if number_strength in {"strong", "moderate"}:
                page_sz = 100 if number_strength == "strong" else 24
                queries.append(
                    client.get_cards_search(local_id=local_num, page_size=page_sz)
                )

                # Also try stripped leading zero if different (e.g. 58 vs 058)
                if local_num.isdigit():
                    stripped = str(int(local_num))
                    if stripped != local_num:
                        queries.append(
                            client.get_cards_search(
                                local_id=stripped, page_size=page_sz
                            )
                        )

                # Search by alternative numbers if provided
                for alt in (alternatives or [])[:4]:
                    alt_clean = alt.split("/")[0].strip()
                    if alt_clean and alt_clean != local_num:
                        queries.append(
                            client.get_cards_search(local_id=alt_clean, page_size=24)
                        )

        if queries:
            results = await asyncio.gather(*queries, return_exceptions=True)
            non_exceptions = 0
            last_err: Exception | None = None
            for res in results:
                if isinstance(res, Exception):
                    last_err = res
                    if isinstance(res, (TcgdexConnectionError, TcgdexError)):
                        logger.warning("TCGdex query error: %s", res)
                    continue
                non_exceptions += 1
                if isinstance(res, list):
                    for card in res:
                        if isinstance(card, dict):
                            cid = card.get("id")
                            if cid and not is_digital_card(card):
                                existing = candidate_cards.get(str(cid), {})
                                candidate_cards[str(cid)] = {**card, **existing}

            if (
                non_exceptions == 0
                and len(candidate_cards) == 0
                and last_err is not None
            ):
                raise CatalogUnavailableError(
                    f"Card catalog queries failed: {last_err}"
                ) from last_err

    except CatalogUnavailableError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during candidate retrieval")
        raise CatalogUnavailableError(f"Catalog retrieval error: {exc}") from exc

    # Retry damaged multiword OCR with individual name tokens. Prefix
    # searches are bounded fallbacks, never proof of identity; ranking and
    # artwork must still corroborate the resulting catalog names.
    if hypotheses and not any(
        any(h.casefold() == str(c.get("name", "")).casefold() for h in hypotheses)
        for c in candidate_cards.values()
    ):
        stop = {
            "basic",
            "stage",
            "evolves",
            "from",
            "trainer",
            "pokemon",
            "mega",
            "vmax",
            "vstar",
        }
        tokens = sorted(
            {
                t
                for h in hypotheses
                for t in re.findall(r"[A-Za-z]{4,}", h)
                if t.lower() not in stop
            },
            key=lambda t: (-len(t), t),
        )[:2]
        fallbacks = []
        for token in tokens:
            fallbacks.append(token)
            if len(token) >= 6:
                fallbacks.append(token[:4])
                fallbacks.append(token[1:5])
        fallbacks = list(dict.fromkeys(fallbacks))[:6]
        results = await asyncio.gather(
            *(client.get_cards_search(name=h, page_size=100) for h in fallbacks),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, list):
                for card in result:
                    if (
                        isinstance(card, dict)
                        and card.get("id")
                        and not is_digital_card(card)
                    ):
                        candidate_cards.setdefault(card["id"], card)

    # Verify denominators for every candidate before selecting an enrichment
    # budget. Otherwise older sets consume that budget and hide the right card.
    for cid, card in candidate_cards.items():
        sid = (card.get("set") or {}).get("id") or cid.rsplit("-", 1)[0]
        if sid in set_index:
            card["set"] = set_index[sid]

    # Preliminary score to identify top candidates for deterministic enrichment
    def score_card(card: dict[str, Any]) -> CandidateMatch:
        return rank_card_candidate(
            card_data=card,
            query_name=clean_name,
            query_number=clean_number,
            query_alternatives=alternatives,
            set_evidence=effective_set_id or clean_set_code,
            name_hypotheses=hypotheses,
            name_confidence=name_confidence,
            number_strength=number_strength,
            extracted_hp=hp,
            extracted_attacks=attacks,
            extracted_abilities=abilities,
            raw_text=raw_text,
        )

    def enrichment_key(card):
        match = score_card(card)
        verified_pair = any(
            r.startswith("Full number and denominator match") for r in match.reasons
        )
        return (not verified_pair, -match.score, match.id)

    preliminary = sorted(candidate_cards.values(), key=enrichment_key)
    top_candidates_to_enrich = preliminary[:32]

    # Deterministic card enrichment: Fetch full details (attacks, abilities, HP)
    detail_semaphore = asyncio.Semaphore(4)

    async def fetch_detail(cid: str) -> dict[str, Any] | None:
        async with detail_semaphore:
            return await client.get_card(cid)

    card_enrich_tasks = []
    cards_being_enriched = []
    for card in top_candidates_to_enrich:
        cid = card.get("id")
        if cid:
            has_details = "attacks" in card or "abilities" in card or "hp" in card
            if not has_details:
                card_enrich_tasks.append(fetch_detail(cid))
                cards_being_enriched.append(str(cid))

    if card_enrich_tasks:
        card_details_results = await asyncio.gather(
            *card_enrich_tasks, return_exceptions=True
        )
        for cid, cres in zip(cards_being_enriched, card_details_results, strict=False):
            if isinstance(cres, dict) and cres.get("id"):
                existing = candidate_cards.get(cid, {})
                if "hp" in cres:
                    existing["hp"] = cres["hp"]
                if "attacks" in cres:
                    existing["attacks"] = cres["attacks"]
                if "abilities" in cres:
                    existing["abilities"] = cres["abilities"]
                if "releaseDate" in cres and not existing.get("releaseDate"):
                    existing["releaseDate"] = cres["releaseDate"]
                if isinstance(cres.get("set"), dict):
                    c_set = cres["set"]
                    if not existing.get("set"):
                        existing["set"] = c_set
                    elif isinstance(existing.get("set"), dict) and "cardCount" in c_set:
                        existing["set"]["cardCount"] = c_set["cardCount"]
                        if "name" in c_set and not existing["set"].get("name"):
                            existing["set"]["name"] = c_set["name"]

    # Enrich top candidates with set metadata for official denominator verification
    unresolved_set_ids: list[str] = []
    for card in top_candidates_to_enrich:
        set_obj = card.get("set")
        if not (
            isinstance(set_obj, dict)
            and "cardCount" in set_obj
            and set_obj["cardCount"].get("official") is not None
        ):
            sid = (
                set_obj.get("id")
                if isinstance(set_obj, dict)
                else (
                    card.get("id", "").rsplit("-", 1)[0]
                    if "-" in card.get("id", "")
                    else None
                )
            )
            if sid and sid not in unresolved_set_ids:
                unresolved_set_ids.append(sid)
            if len(unresolved_set_ids) == 10:
                break

    if unresolved_set_ids:
        set_tasks = [client.get_set(sid) for sid in unresolved_set_ids]
        set_results = await asyncio.gather(*set_tasks, return_exceptions=True)
        set_map: dict[str, dict[str, Any]] = {}
        for sres in set_results:
            if isinstance(sres, dict) and sres.get("id"):
                set_map[str(sres["id"])] = sres

        for _cid, card in candidate_cards.items():
            set_obj = card.get("set")
            sid = (
                set_obj.get("id")
                if isinstance(set_obj, dict)
                else (
                    card.get("id", "").rsplit("-", 1)[0]
                    if "-" in card.get("id", "")
                    else None
                )
            )
            if sid and sid in set_map:
                sinfo = set_map[sid]
                card["set"] = {
                    "id": sinfo.get("id", sid),
                    "name": sinfo.get("name", sid),
                    "cardCount": sinfo.get("cardCount", {}),
                }
                if "releaseDate" in sinfo and not card.get("releaseDate"):
                    card["releaseDate"] = sinfo["releaseDate"]

    # Rank all candidate cards using evidence-aware ranking rules
    ranked: list[CandidateMatch] = []
    for card in candidate_cards.values():
        match = rank_card_candidate(
            card_data=card,
            query_name=clean_name,
            query_number=clean_number,
            query_alternatives=alternatives,
            set_evidence=effective_set_id or clean_set_code,
            name_hypotheses=hypotheses,
            name_confidence=name_confidence,
            number_strength=number_strength,
            extracted_hp=hp,
            extracted_attacks=attacks,
            extracted_abilities=abilities,
            raw_text=raw_text,
        )
        if match.score > 0:
            ranked.append(match)

    # Deterministic tie-breaking: sort by (-score, release_date/set_id, id)
    def tie_break_key(m: CandidateMatch) -> tuple[int, str, str]:
        cdata = candidate_cards.get(m.id, {})
        rel_date = str(cdata.get("releaseDate") or "")
        set_key = rel_date if rel_date else (m.set_id or "")
        return (-m.score, set_key, m.id)

    ranked.sort(key=tie_break_key)
    protected = [
        m
        for m in ranked
        if any(r.startswith("Full number and denominator match") for r in m.reasons)
    ][: min(8, limit)]
    protected_ids = {m.id for m in protected}
    selected = (
        protected
        + [m for m in ranked if m.id not in protected_ids][
            : max(0, limit - len(protected))
        ]
    )
    return sorted(selected, key=tie_break_key), len(ranked)
