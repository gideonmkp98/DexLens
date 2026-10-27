import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any

from app.services.ocr.normalizer import normalize_card_name


@dataclass
class CandidateMatch:
    id: str
    name: str
    local_id: str
    set_id: str
    set_name: str
    image_url: str | None
    score: int
    reasons: list[str]
    hp: str | None = None
    matched_attacks: list[str] = field(default_factory=list)
    matched_abilities: list[str] = field(default_factory=list)
    visual_similarity: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _derive_image_urls(base_url: str | None) -> tuple[str | None, str | None]:
    if not base_url:
        return None, None
    clean = base_url.rstrip("/")
    if clean.endswith("/low.webp") or clean.endswith("/high.webp"):
        clean = clean.rsplit("/", 1)[0]
    return f"{clean}/low.webp", f"{clean}/high.webp"


def _strip_leading_zeros(val: str) -> str:
    parts = val.split("/")
    clean_parts = [str(int(p)) if p.isdigit() else p for p in parts]
    return "/".join(clean_parts)


def _normalize_token_str(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


# Suffix list ordered from longest to shortest to prevent sub-token collisions
NAME_SUFFIXES = ["VMAX", "VSTAR", "TAG TEAM", "Radiant", "ex", "EX", "GX", "V"]


def rank_card_candidate(
    card_data: dict[str, Any],
    query_name: str | None,
    query_number: str | None,
    query_alternatives: list[str] | None = None,
    set_evidence: str | None = None,
    name_hypotheses: list[str] | None = None,
    name_confidence: str = "medium",
    number_strength: str = "strong",
    extracted_hp: str | None = None,
    extracted_attacks: list[str] | None = None,
    extracted_abilities: list[str] | None = None,
    raw_text: str | None = None,
) -> CandidateMatch:
    """Score a candidate with evidence-aware rules and honest explanations."""
    card_id = str(card_data.get("id", ""))
    card_name = str(card_data.get("name", ""))
    local_id = str(card_data.get("localId", ""))

    # Extract set info
    set_obj = card_data.get("set")
    card_count: dict[str, Any] = {}
    if isinstance(set_obj, dict) and set_obj.get("id"):
        set_id = str(set_obj.get("id", ""))
        set_name = str(set_obj.get("name") or set_id)
        if isinstance(set_obj.get("cardCount"), dict):
            card_count = set_obj.get("cardCount", {})
    else:
        # Fallback to ID prefix
        set_id = card_id.rsplit("-", 1)[0] if "-" in card_id else ""
        set_name = set_id

    # Derive thumbnail image
    raw_img = card_data.get("image")
    small_img, _ = _derive_image_urls(raw_img) if raw_img else (None, None)

    score = 0
    reasons: list[str] = []

    clean_card_name = card_name.strip()
    clean_query_name = normalize_card_name(query_name) if query_name else None

    clean_card_num = local_id.strip()
    clean_query_num = query_number.strip() if query_number else None
    alts = [a.strip() for a in (query_alternatives or [])]

    # --- 1. Collector Number Evaluation ---
    number_matched = False
    if clean_query_num and number_strength != "none":
        has_slash = "/" in clean_query_num
        query_numerator = clean_query_num.split("/")[0].strip()
        query_denom = clean_query_num.split("/")[-1].strip() if has_slash else None

        # Verify candidate set denominator if available (official set count only)
        official_denom = None
        if card_count:
            official_denom = str(card_count.get("official") or "")

        # Check numerator agreement
        num_agree = (
            clean_card_num == clean_query_num
            or clean_card_num == query_numerator
            or _strip_leading_zeros(clean_card_num)
            == _strip_leading_zeros(query_numerator)
            or any(
                clean_card_num == a or clean_card_num == a.split("/")[0].strip()
                for a in alts
            )
        )

        if num_agree:
            number_matched = True
            if has_slash and query_denom:
                denominator_agrees = bool(official_denom) and (
                    _strip_leading_zeros(official_denom)
                    == _strip_leading_zeros(query_denom)
                )
                if denominator_agrees:
                    # Verified full number and denominator match
                    score += 50
                    reasons.append(
                        f"Full number and denominator match "
                        f"({clean_card_num}/{query_denom})"
                    )
                elif official_denom:
                    # Verified denominator mismatch!
                    score += 15
                    reasons.append(
                        f"Numerator matches ({clean_card_num}), but denominator "
                        f"conflicts ({query_denom} vs {official_denom})"
                    )
                else:
                    # Denominator unverified from provider set metadata
                    score += 42
                    reasons.append(
                        f"Collector number numerator matches ({clean_card_num}), "
                        f"printed denominator unverified"
                    )
            else:
                # Query was standalone number
                if number_strength == "weak":
                    score += 15
                    reasons.append(f"Weak standalone number match ({clean_card_num})")
                else:
                    if clean_card_num == clean_query_num:
                        score += 45
                        reasons.append(
                            f"Exact collector number match ({clean_card_num})"
                        )
                    else:
                        score += 40
                        reasons.append(
                            f"Collector number match without leading zero "
                            f"({clean_card_num})"
                        )
        else:
            # Check prefix agreement (e.g. TG01 / TG)
            cand_prefix = re.match(r"^[A-Za-z]+", clean_card_num)
            query_prefix = re.match(r"^[A-Za-z]+", clean_query_num)
            if (
                cand_prefix
                and query_prefix
                and cand_prefix.group(0).upper() == query_prefix.group(0).upper()
            ):
                score += 15
                reasons.append(
                    f"Matching number prefix ({cand_prefix.group(0).upper()})"
                )
    else:
        reasons.append("Collector number could not be read reliably")

    # --- 2. Card Name Evaluation ---
    name_matched = False
    hypotheses: list[str] = [h.lower() for h in (name_hypotheses or [])]
    if clean_query_name and clean_query_name.lower() not in hypotheses:
        hypotheses.insert(0, clean_query_name.lower())

    if hypotheses:
        c_lower = clean_card_name.lower()
        q_lower = hypotheses[0]

        if c_lower == q_lower:
            score += 45
            reasons.append(f"Exact card name match ('{card_name}')")
            name_matched = True
        elif any(c_lower == h for h in hypotheses):
            score += 40
            reasons.append(f"Name matches hypothesis ('{card_name}')")
            name_matched = True
        elif any(h in c_lower or c_lower in h for h in hypotheses if len(h) >= 3):
            score += 35
            reasons.append(f"Name closely matches ('{card_name}')")
            name_matched = True
        else:
            # Word overlap check
            q_words = set(re.findall(r"\w+", q_lower))
            c_words = set(re.findall(r"\w+", c_lower))
            common = q_words.intersection(c_words)
            if common and any(len(w) >= 3 for w in common):
                score += 20
                reasons.append(f"Name shares words ({', '.join(common)})")
                name_matched = True

        # Fallback check against raw_text when name didn't match header hypotheses
        if not name_matched:
            # Approximate OCR text has less weight than an exact name.
            query_tokens = [t for h in hypotheses for t in re.findall(r"[a-z]{4,}", h)]
            card_tokens = re.findall(r"[a-z]{4,}", c_lower)
            if any(
                SequenceMatcher(None, q, c).ratio() >= 0.8
                for q in query_tokens
                for c in card_tokens
            ):
                score += 30
                reasons.append(f"OCR name approximately matches ('{card_name}')")
                name_matched = True

        if not name_matched and raw_text:
            c_name_norm = clean_card_name.lower().strip()
            if len(c_name_norm) >= 3 and re.search(
                rf"\b{re.escape(c_name_norm)}\b", raw_text, re.IGNORECASE
            ):
                score += 35
                reasons.append(f"Name found in scanned card text ('{card_name}')")
                name_matched = True

        # Suffix agreement check with word boundary isolation
        for sfx in NAME_SUFFIXES:
            sfx_pat = re.compile(rf"\b{re.escape(sfx)}\b", re.IGNORECASE)
            q_has_sfx = any(bool(sfx_pat.search(h)) for h in hypotheses)
            c_has_sfx = bool(sfx_pat.search(clean_card_name))

            if q_has_sfx and c_has_sfx:
                score += 12
                reasons.append(f"Matching '{sfx}' designation")
                break
            elif q_has_sfx and not c_has_sfx:
                score -= 15
                reasons.append(f"Missing expected '{sfx}' designation")
                break
            elif not q_has_sfx and c_has_sfx:
                score -= 10
                break

        # Name mismatch penalty when name queried but neither name nor number matched
        if not name_matched and not number_matched:
            score -= 15
            reasons.append(f"Card name does not match query ('{card_name}')")

    # --- 3. Set Evidence Evaluation ---
    if set_evidence:
        clean_set_ev = set_evidence.strip().lower()
        if (
            clean_set_ev == set_id.lower()
            or clean_set_ev in set_name.lower()
            or set_name.lower() in clean_set_ev
        ):
            score += 20
            reasons.append(f"Set matches '{set_name}'")

    # --- 4. Conflict Penalties ---
    # Conflicting number when name matches:
    # ONLY penalize if the query number is credible/strong.
    if name_matched and clean_query_num and not number_matched:
        if number_strength == "strong":
            score -= 20
            reasons.append(
                f"Card number differs from query "
                f"({clean_card_num} vs {clean_query_num})"
            )
        else:
            reasons.append(
                f"Card number unverified ({clean_card_num} vs query {clean_query_num})"
            )

    # Conflicting name when number matches:
    # Matching number alone must NOT outrank credible name matches (-45 pts).
    if number_matched and hypotheses and not name_matched:
        if name_confidence in ("high", "medium"):
            verified_pair = any(
                "Full number and denominator match" in r for r in reasons
            )
            score -= 25 if verified_pair else 45
            reasons.append(f"Card name differs from query ('{card_name}')")
        else:
            score -= 25
            reasons.append(f"Card name differs from query ('{card_name}')")

    primary_score = score
    # --- 5. Attacks, Abilities, and HP Evaluation ---
    cand_hp = card_data.get("hp")
    cand_hp_str = str(cand_hp).strip() if cand_hp is not None else None
    if cand_hp_str and extracted_hp:
        cand_hp_digits = re.search(r"\d+", cand_hp_str)
        ext_hp_digits = re.search(r"\d+", str(extracted_hp))
        if (
            cand_hp_digits
            and ext_hp_digits
            and cand_hp_digits.group(0) == ext_hp_digits.group(0)
        ):
            score += 10
            reasons.append(f"HP matches ({cand_hp_digits.group(0)})")

    matched_attacks: list[str] = []
    cand_attacks = card_data.get("attacks") or []
    ext_attacks_list = [a.strip() for a in (extracted_attacks or []) if a and a.strip()]
    for att in cand_attacks:
        att_name = att.get("name") if isinstance(att, dict) else str(att)
        if not att_name:
            continue
        att_norm = _normalize_token_str(att_name)
        if not att_norm:
            continue
        matched = False
        for ext_att in ext_attacks_list:
            ext_norm = _normalize_token_str(ext_att)
            if att_norm == ext_norm or (
                len(ext_norm) >= 4 and (ext_norm in att_norm or att_norm in ext_norm)
            ):
                matched = True
                break
        if not matched and raw_text and len(att_name) >= 4:
            if re.search(
                rf"\b{re.escape(att_name.lower())}\b", raw_text, re.IGNORECASE
            ):
                matched = True

        if matched and att_name not in matched_attacks:
            score += 20
            matched_attacks.append(att_name)
            reasons.append(f"Attack matches ('{att_name}')")

    matched_abilities: list[str] = []
    cand_abilities = card_data.get("abilities") or []
    ext_abilities_list = [
        a.strip() for a in (extracted_abilities or []) if a and a.strip()
    ]
    for abil in cand_abilities:
        abil_name = abil.get("name") if isinstance(abil, dict) else str(abil)
        if not abil_name:
            continue
        abil_norm = _normalize_token_str(abil_name)
        if not abil_norm:
            continue
        matched = False
        for ext_abil in ext_abilities_list:
            ext_norm = _normalize_token_str(ext_abil)
            if abil_norm == ext_norm or (
                len(ext_norm) >= 4 and (ext_norm in abil_norm or abil_norm in ext_norm)
            ):
                matched = True
                break
        if not matched and raw_text and len(abil_name) >= 4:
            if re.search(
                rf"\b{re.escape(abil_name.lower())}\b", raw_text, re.IGNORECASE
            ):
                matched = True

        if matched and abil_name not in matched_abilities:
            score += 20
            matched_abilities.append(abil_name)
            reasons.append(f"Ability matches ('{abil_name}')")

    # Bound final score between 0 and 100
    # Secondary text repeats across reprints. It cannot erase contradictory
    # collector evidence or saturate every printing at 100.
    score = primary_score + min(25, score - primary_score)
    final_score = max(0, min(100, score))
    if any("conflicts" in reason for reason in reasons):
        final_score = min(final_score, 59)

    return CandidateMatch(
        id=card_id,
        name=card_name,
        local_id=local_id,
        set_id=set_id,
        set_name=set_name,
        image_url=small_img,
        score=final_score,
        reasons=reasons,
        hp=cand_hp_str,
        matched_attacks=matched_attacks,
        matched_abilities=matched_abilities,
        visual_similarity=None,
    )


def derive_confidence_state(
    candidates: list[CandidateMatch],
    is_low_res: bool = False,
) -> str:
    """Classify the recognition confidence state as 'high', 'medium', or 'low'."""
    if not candidates:
        return "low"
    if is_low_res:
        return "low"

    top = candidates[0]
    top_score = top.score
    if len(candidates) > 1 and top_score - candidates[1].score < 8:
        return "low"  # Shared artwork/text cannot distinguish tied printings.

    # Conflicting fields or score < 35 -> low confidence
    has_conflicts = any(
        "conflicts" in r.lower() or "differs from query" in r.lower()
        for r in top.reasons
    )
    if has_conflicts or top_score < 35:
        return "low"

    has_strong_number = any(
        "denominator match" in r.lower()
        or "exact collector number" in r.lower()
        or "full number" in r.lower()
        for r in top.reasons
    )
    has_attack_or_ability = bool(top.matched_attacks or top.matched_abilities) or any(
        "attack matches" in r.lower() or "ability matches" in r.lower()
        for r in top.reasons
    )
    has_visual_agreement = (
        top.visual_similarity is not None and top.visual_similarity >= 0.65
    ) or any("artwork resembles" in r.lower() for r in top.reasons)

    if top_score >= 75 and (
        has_strong_number or (has_attack_or_ability and has_visual_agreement)
    ):
        return "high"

    if 35 <= top_score:
        return "medium"

    return "low"
