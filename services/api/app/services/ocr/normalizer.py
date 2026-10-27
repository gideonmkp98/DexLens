import re
from dataclasses import dataclass, field
from typing import Any

from app.services.ocr.engine import OcrResult

# Regexes for card name cleaning
_HP_PATTERN = re.compile(
    r"\b(?:(?:HP|HPD|HEY|HE|HB|HR)\s*\d+|\d+\s*(?:HP|HPD|HEY|HE|HB|HR))\b",
    re.IGNORECASE,
)
_BASIC_STAGE_PATTERN = re.compile(
    r"\b(?:BASIC|STAGE\s*[12]|EVOLVES\s+FROM|VSTAR\s+POWER|V-UNION)\b",
    re.IGNORECASE,
)
_COMMON_NAME_SUFFIXES = [
    "ex",
    "EX",
    "VMAX",
    "VSTAR",
    "V",
    "GX",
    "TAG TEAM",
    "Radiant",
    "Break",
    "Prime",
    "Legend",
    "LV.X",
]

# Patterns for false numbers that must NOT be confused with collector numbers
_YEAR_PATTERN = re.compile(r"\b(?:199[5-9]|20[0-2][0-9]|2030)\b")
_ATTACK_DAMAGE_PATTERN = re.compile(
    r"\b\d{1,3}[\+x×\-](?!\w)",
    re.IGNORECASE,
)
_PREFIX_MODIFIER_PATTERN = re.compile(
    r"[\+x×\-@*]\s*(\d{1,3})\b",
    re.IGNORECASE,
)
_RETREAT_RESIST_PATTERN = re.compile(
    r"\b(?:retreat(?:\s*cost)?|resistance|weakness)\b",
    re.IGNORECASE,
)
_POKEDEX_INFO_PATTERN = re.compile(
    r"\b(?:no\.?\s*\d+|ht:?|wt:?|lv\.?\s*\d+)\b",
    re.IGNORECASE,
)
_REGULATION_MARK_PATTERN = re.compile(r"\b[D-I]\b")

# Number formats:
# 1. Denominator e.g. "199/165", "058/102", "TG01/TG30", "GG01/GG70", "RC1/RC32"
_DENOMINATOR_NUMBER_PATTERN = re.compile(
    r"\b([A-Za-z0-9]{1,8})\s*/\s*([A-Za-z0-9]{1,8})\b"
)

# 2. Promo format e.g. "SVP 001", "SWSH001", "SM01", "XY01", "BW01", "DP01"
_PROMO_NUMBER_PATTERN = re.compile(
    r"\b([A-Za-z]{2,5})\s*[-#]?\s*([A-Za-z0-9]{1,4})\b",
    re.IGNORECASE,
)

# 3. Trainer Gallery / Galarian Gallery / Special subsets e.g. "TG01", "GG25", "RC1"
_GALLERY_PREFIX_PATTERN = re.compile(r"\b([A-Za-z]{1,4}\s*\d{1,4})\b")

# 4. Standalone collector number (e.g. "058", "58", "4", "102")
_STANDALONE_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9])(\d{1,4})(?![A-Za-z0-9])")

# Known gallery/subset alphanumeric prefixes
KNOWN_SUBSET_PREFIXES = {
    "TG",
    "GG",
    "RC",
    "SV",
    "H",
    "SVP",
    "SWSH",
    "SM",
    "XY",
    "BW",
    "DP",
    "HGSS",
    "POP",
    "PR",
}

# Set codes: typically 3-4 capital letters in modern Pokémon cards footer
_SET_CODE_PATTERN = re.compile(
    r"\b(MEW|SVI|PAL|OBF|PAR|PAF|TEF|TWM|SFA|SCR|SSP|PRE|CRZ|SIT|LOR|ASR|BRS|FST|EVS|CRE|BST|VIV|CPA|DAA|RCL|SSH|UNM|UNB|TEU|LOT|CES|FLI|UPR|CIN|BUS|GRI|SUM|EVO|STS|FCO|BKP|BKT|AOR|ROS|PRC|PHF|FFI|FLF|XY|LTR|PLB|PLF|PLS|BCR|DRX|DEX|NDX|NVI|EPO|BLW)\b"
)


@dataclass
class NormalizedNumber:
    raw_number: str
    local_id: str
    denominator: str | None = None
    full_formatted: str = ""
    alternatives: list[str] = field(default_factory=list)
    strength: str = "strong"  # "strong", "moderate", "weak", "none"
    source_region: str | None = None


@dataclass
class CardExtractionResult:
    raw_text: str
    name: str | None
    number: str | None
    local_id: str | None
    printed_denominator: str | None
    set_code: str | None
    confidence: float
    alternatives: list[str] = field(default_factory=list)
    name_hypotheses: list[str] = field(default_factory=list)
    name_confidence: str = "medium"  # "high", "medium", "low"
    number_strength: str = "none"  # "strong", "moderate", "weak", "none"
    source_regions: dict[str, str] = field(default_factory=dict)
    image_quality: dict[str, Any] = field(default_factory=dict)
    hp: str | None = None
    attacks: list[str] = field(default_factory=list)
    abilities: list[str] = field(default_factory=list)


def _disambiguate_numeric_chars(s: str) -> str:
    """Disambiguate common OCR letter/digit misidentifications in numeric contexts."""
    # Single character mappings when in numeric contexts
    if len(s) == 1:
        if s in ("O", "o"):
            return "0"
        if s in ("I", "l", "|", "i"):
            return "1"
        if s in ("S", "s"):
            return "5"
        if s in ("B",):
            return "8"
        if s in ("A",):
            return "4"
        return s

    # O or o -> 0
    s = re.sub(r"(?<=\d)[Oo](?=\d|$)|(?<=^)[Oo](?=\d)", "0", s)
    # I or l -> 1
    s = re.sub(r"(?<=\d)[Il](?=\d|$)|(?<=^)[Il](?=\d)", "1", s)
    # S -> 5
    s = re.sub(r"(?<=\d)[Ss](?=\d|$)|(?<=^)[Ss](?=\d)", "5", s)
    # B -> 8
    s = re.sub(r"(?<=\d)[B](?=\d|$)|(?<=^)[B](?=\d)", "8", s)
    return s


def _validate_slash_structure(clean_num: str, clean_denom: str) -> bool:
    """Validate that slash-separated text conforms to a real collector number pattern.

    Strictly rejects non-numeric or purely alphabetic garbage (e.g. 'thoes/ie').
    """
    # 1. Purely numeric numerator and denominator: 58/102, 199/165, 058/102
    if clean_num.isdigit() and clean_denom.isdigit():
        num_val = int(clean_num)
        denom_val = int(clean_denom)
        # Avoid zero denominators or absurdly large numbers
        if 1 <= denom_val <= 999 and 1 <= num_val <= 999:
            return True
        return False

    # 2. Known subset prefix + digits: TG01/TG30, GG01/GG70, RC1/RC32, SV01/SV100
    pfx_match = re.match(r"^([A-Za-z]{1,4})(\d{1,4})$", clean_num)
    if pfx_match:
        pfx, num_digits = pfx_match.groups()
        if pfx.upper() in KNOWN_SUBSET_PREFIXES:
            # Denominator may be digits or same prefix + digits
            denom_match = re.match(r"^([A-Za-z]{0,4})(\d{1,4})$", clean_denom)
            if denom_match:
                return True

    return False


def normalize_collector_number(
    raw_text: str, source_region: str | None = None
) -> NormalizedNumber | None:
    """Extract and normalize collector numbers from OCR text without destroying meaning.

    Supports:
    - Slash/denominator formats: 199/165, 058/102, TG01/TG30, GG01/GG70
    - Secret rares: numbers higher than denominator (199/165)
    - Promo identifiers: SVP 001, SWSH001, SM01
    - Standalone collector numbers: '058', '58', '4' with strict context checks
    - Rejects pure alphabetic or nonsensical patterns such as 'thoes/ie'
    - Classifies evidence strength: 'strong', 'moderate', 'weak'
    """
    if not raw_text or not raw_text.strip():
        return None

    cleaned_text = raw_text.strip()

    # Pass 1: Try denominator pattern (e.g. 199/165 or 058/102 or TG01/TG30)
    for match in _DENOMINATOR_NUMBER_PATTERN.finditer(cleaned_text):
        raw_num = match.group(1).strip()
        raw_denom = match.group(2).strip()

        # Disambiguate leading trademark or OCR T/TM artifacts attached to number
        raw_num = re.sub(
            r"^[™\u2122]*(?:TM|T)(?=[0-9]|A(?:\b|\d))",
            "",
            raw_num,
            flags=re.IGNORECASE,
        )

        # Disambiguate characters
        clean_num = _disambiguate_numeric_chars(raw_num).replace(" ", "")
        clean_denom = _disambiguate_numeric_chars(raw_denom).replace(" ", "")

        # Strict structural validation: must not be pure words like 'thoes/ie'
        if not _validate_slash_structure(clean_num, clean_denom):
            continue

        # Skip if either is a copyright year
        if _YEAR_PATTERN.fullmatch(clean_num) or _YEAR_PATTERN.fullmatch(clean_denom):
            continue

        # Standardize representation
        full_formatted = f"{clean_num}/{clean_denom}"
        alternatives: list[str] = [full_formatted]

        # Handle leading zeros in numerator: "058" -> also note "58" and "58/102"
        if clean_num.isdigit():
            stripped = str(int(clean_num))
            if stripped != clean_num:
                alternatives.append(stripped)
                alternatives.append(f"{stripped}/{clean_denom}")

        # In case the prefix was separated: e.g. TG 01 -> TG01
        alternatives.append(clean_num)

        return NormalizedNumber(
            raw_number=match.group(0),
            local_id=clean_num,
            denominator=clean_denom,
            full_formatted=full_formatted,
            alternatives=list(dict.fromkeys(alternatives)),
            strength="strong",
            source_region=source_region,
        )

    # Pass 2: Try promo pattern (e.g. SVP 001, SWSH 001)
    for promo_match in _PROMO_NUMBER_PATTERN.finditer(cleaned_text):
        raw_prefix = promo_match.group(1).upper()
        if raw_prefix in {
            "SVP",
            "SWSH",
            "SM",
            "XY",
            "BW",
            "DP",
            "HGSS",
            "POP",
            "PR",
        }:
            digits = _disambiguate_numeric_chars(promo_match.group(2))
            if not digits.isdigit():
                continue
            full_formatted = f"{raw_prefix} {digits}"
            compact_formatted = f"{raw_prefix}{digits}"
            alternatives = [full_formatted, compact_formatted]

            if digits.isdigit():
                stripped_digits = str(int(digits))
                if stripped_digits != digits:
                    alternatives.append(f"{raw_prefix} {stripped_digits}")
                    alternatives.append(f"{raw_prefix}{stripped_digits}")

            return NormalizedNumber(
                raw_number=promo_match.group(0),
                local_id=full_formatted,
                denominator=None,
                full_formatted=full_formatted,
                alternatives=list(dict.fromkeys(alternatives)),
                strength="strong",
                source_region=source_region,
            )

    # Pass 3: Trainer / Galarian Gallery / Special subsets (TG01, GG05, RC1)
    for match in _GALLERY_PREFIX_PATTERN.finditer(cleaned_text):
        candidate = match.group(1).strip().replace(" ", "")
        # Filter false positives: HP, Attack damage, Copyright years
        if _YEAR_PATTERN.fullmatch(candidate):
            continue
        if candidate.upper().startswith("HP"):
            continue
        if candidate.endswith(("+", "x", "X", "-")):
            continue

        cand_upper = candidate.upper()
        if cand_upper.startswith(("TG", "GG", "SV", "RC")):
            return NormalizedNumber(
                raw_number=candidate,
                local_id=cand_upper,
                denominator=None,
                full_formatted=cand_upper,
                alternatives=[cand_upper],
                strength="strong",
                source_region=source_region,
            )

    # Pass 4: Standalone collector number (e.g. "058", "58", "4", "102")
    # Must reject HP, damage, copyright years, retreat lines, and regulation marks
    for match in _STANDALONE_NUMBER_PATTERN.finditer(cleaned_text):
        raw_val = match.group(1)
        start_idx = match.start()
        end_idx = match.end()

        # Check immediate prefix for damage/retreat/weakness modifiers:
        # (+, -, x, ×, @, *)
        prefix_window = cleaned_text[max(0, start_idx - 5) : start_idx]
        if _PREFIX_MODIFIER_PATTERN.search(
            prefix_window + raw_val
        ) or prefix_window.rstrip().endswith(("+", "x", "X", "×", "-", "@", "*")):
            continue

        # Check immediate suffix for damage modifiers
        if end_idx < len(cleaned_text) and cleaned_text[end_idx] in (
            "+",
            "x",
            "X",
            "×",
            "-",
            "%",
        ):
            continue

        # Check surrounding text context for false positive indicators
        context_window = cleaned_text[
            max(0, start_idx - 15) : min(len(cleaned_text), end_idx + 15)
        ]
        if _HP_PATTERN.search(context_window):
            continue
        if _ATTACK_DAMAGE_PATTERN.search(context_window):
            continue
        if _RETREAT_RESIST_PATTERN.search(context_window):
            continue
        if _POKEDEX_INFO_PATTERN.search(context_window):
            continue
        if _YEAR_PATTERN.fullmatch(raw_val) or _YEAR_PATTERN.search(context_window):
            continue

        val = int(raw_val)
        if 1 <= val <= 999:
            alts = [raw_val]
            stripped = str(val)
            if stripped != raw_val:
                alts.append(stripped)

            # Evidence strength classification:
            # Single-digit numbers (1-9) in footer text have high false-positive
            # rates and are classified as "weak" evidence unless in strong context.
            # Multi-digit numbers (10-999) have lower random chance ("moderate").
            evidence_strength = "weak" if val < 10 else "moderate"

            return NormalizedNumber(
                raw_number=match.group(0),
                local_id=raw_val,
                denominator=None,
                full_formatted=raw_val,
                alternatives=list(dict.fromkeys(alts)),
                strength=evidence_strength,
                source_region=source_region,
            )

    return None


def generate_name_hypotheses(raw_name: str) -> list[str]:
    """Generate ordered, bounded name hypotheses from cleaned card name text.

    Distinguishes core names from edge OCR noise (e.g. 'Gastly se' -> 'Gastly',
    'ad Steelix eee 4' -> 'Steelix'), while preserving multiword names and suffixes.
    """
    if not raw_name or not raw_name.strip():
        return []

    cleaned = raw_name.strip()
    words = cleaned.split()
    if not words:
        return []

    hypotheses: list[str] = [cleaned]

    # Check for vintage evolution instruction pattern: "Put <Name> on the..."
    put_match = re.search(r"\bput\s+([A-Za-z]+)\s+on\s+the\b", cleaned, re.IGNORECASE)
    if put_match:
        cand = put_match.group(1).strip()
        if len(cand) >= 3 and cand.lower() not in {"the", "stage", "basic", "card"}:
            hypotheses.insert(0, cand)

    # Pattern for isolated edge noise words:
    # 1-2 char noise, repeats ('eee'), trailing numbers ('4'), or stage remnants
    noise_pattern = re.compile(
        r"^(ad|se|eee|the|a|an|basic|stage|asic|sasic|put|on|card|\d+|"
        r"[a-z]{1,2}|[a-z]\d|\d[a-z])$",
        re.IGNORECASE,
    )

    # Prune noise words from edges
    start = 0
    while (
        start < len(words)
        and noise_pattern.match(words[start])
        and words[start].lower() not in {"ex", "gx", "v"}
    ):
        start += 1
    end = len(words)
    while (
        end > start
        and noise_pattern.match(words[end - 1])
        and words[end - 1].lower() not in {"ex", "gx", "v"}
    ):
        end -= 1

    core_words = words[start:end]
    if core_words and core_words != words:
        core_name = " ".join(core_words)
        if len(core_name) >= 2:
            hypotheses.insert(0, core_name)  # Core name is preferred

    # If suffix is present (e.g. 'Charizard ex'), also provide base Pokémon name
    for sfx in _COMMON_NAME_SUFFIXES:
        pattern = re.compile(rf"\b{re.escape(sfx)}\b", re.IGNORECASE)
        base = pattern.sub("", hypotheses[0]).strip()
        if base and base != hypotheses[0] and len(base) >= 3:
            hypotheses.append(base)
            break

    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for h in hypotheses:
        if h and h.lower() not in seen:
            seen.add(h.lower())
            result.append(h)

    return result[:3]  # Bound to max 3 hypotheses


def normalize_card_name(raw_text: str) -> str | None:
    """Normalize OCR text for a card name header.

    Preserves meaningful suffixes like ex, V, VMAX, GX while removing HP, stage,
    and OCR noise artifacts. Keeps line boundaries so categories like 'Basic Pokémon'
    are not mistaken for the card name.
    """
    if not raw_text or not raw_text.strip():
        return None

    # Keep line boundaries: vintage headers put "Basic Pokémon" above the
    # actual name. Flattening these lines makes the category look like a name.
    lines = []
    for line in raw_text.splitlines():
        # Evolution instructions are a separate, smaller line above the title.
        # Removing fragments can leave plausible-looking OCR garbage behind.
        if re.search(
            r"(?:e?volves?)\s+fro[mn]|put\s+.+\s+on\s+the", line, re.IGNORECASE
        ):
            continue
        line = re.sub(r"^\W*\d\s*[/|]\s*", "", line)
        line = re.sub(r"\b(?:s?asic)\s+pok[eé]mon\b", "", line, flags=re.IGNORECASE)
        line = re.sub(r"\bbasic\s+pok[eé]mon\b", "", line, flags=re.IGNORECASE)
        line = re.sub(
            r"\b(?:evolves\s+from\s+[A-Za-z]+|put\s+[A-Za-z]+\s+on\s+the\s+[A-Za-z0-9\s]+(?:card|pok[eé]mon))\b",
            "",
            line,
            flags=re.IGNORECASE,
        )
        line = _HP_PATTERN.sub("", line)
        line = _BASIC_STAGE_PATTERN.sub("", line).strip(" |.-")
        if not line or re.fullmatch(
            r"pok[eé]mon|trainer|supporter|item|energy|hp|evolves\s+from.*",
            line,
            re.IGNORECASE,
        ):
            continue
        if re.match(r"^[^\w]*\d", line) or not re.search(r"[A-Za-z]{2}", line):
            continue
        lines.append(line)
    if not lines:
        return None
    text = " ".join(lines[0].split()).strip()

    # Strip HP text (e.g. "Pikachu HP 60", "120 HP Mewtwo")
    text = _HP_PATTERN.sub("", text).strip()

    # Strip Stage indicators (e.g. "STAGE 1", "BASIC")
    text = _BASIC_STAGE_PATTERN.sub("", text).strip()

    # Clean characters: preserve letters, numbers, hyphens, apostrophes, spaces
    # and common suffix markers
    cleaned_words: list[str] = []
    for word in text.split():
        # Remove stray punctuation like pipes, commas, copyright symbols
        cleaned_word = re.sub(r"[^\w\-\'\.]", "", word).strip(".-'")
        if not cleaned_word:
            continue
        # Strip OCR-fused basic prefix e.g. "sasicWeedle" -> "Weedle"
        if len(cleaned_word) > 5 and re.match(
            r"^(?:basic|sasic|asic)[A-Z]", cleaned_word, re.IGNORECASE
        ):
            cleaned_word = re.sub(
                r"^(?:basic|sasic|asic)", "", cleaned_word, flags=re.IGNORECASE
            )
        # Avoid standalone energy symbols or numbers in name
        if cleaned_word.isdigit() and int(cleaned_word) > 10:
            continue
        cleaned_words.append(cleaned_word)

    if not cleaned_words:
        return None

    normalized_name = " ".join(cleaned_words).strip()

    # Check for suffix capitalization (e.g. "V", "VMAX", "GX")
    for suffix in [
        "VMAX",
        "VSTAR",
        "TAG TEAM",
        "Radiant",
        "Break",
        "Prime",
        "Legend",
        "LV.X",
        "GX",
        "V",
    ]:
        pattern = re.compile(rf"\b{re.escape(suffix)}\b", re.IGNORECASE)
        normalized_name = pattern.sub(suffix, normalized_name)

    # Specific check for 'ex' vs 'EX':
    # If raw input had 'EX', preserve 'EX'; if it had 'ex', preserve 'ex'
    if re.search(r"\bEX\b", text):
        normalized_name = re.sub(r"\bex\b", "EX", normalized_name, flags=re.IGNORECASE)
    elif re.search(r"\bex\b", text, re.IGNORECASE):
        normalized_name = re.sub(r"\bex\b", "ex", normalized_name, flags=re.IGNORECASE)

    return normalized_name if len(normalized_name) >= 2 else None


_HP_EXPLICIT_PATTERN = re.compile(
    r"\b(?:HP\s*(\d{2,3})|(\d{2,3})\s*HP)\b",
    re.IGNORECASE,
)
_HP_FUZZY_PATTERN = re.compile(
    r"\b(?:(?:HP|HPD|HEY|HE|HB|HR)\s*(\d{2,3})|(\d{2,3})\s*(?:HP|HPD|HEY|HE|HB|HR))\b",
    re.IGNORECASE,
)


def normalize_hp(raw_text: str, is_header_or_hp_roi: bool = True) -> str | None:
    """Extract and normalize Pokémon HP value from OCR text.

    Supports:
    - Standard explicit: '190 HP', 'HP 120', 'HP60', '330 HP'
    - Minor OCR letter distortions: '120 HE', '50 HPD', '120 HB'
    - Multiple-of-10 values in dedicated header/HP ROI: '190', '120'
    - Rejects invalid numbers (copyright years, stages, levels, Pokédex numbers,
      slash formats).
    - Returns None if unreadable. Never hallucinates.
    """
    if not raw_text or not raw_text.strip():
        return None

    cleaned = raw_text.strip()

    # 1. Standard explicit HP
    m_exp = _HP_EXPLICIT_PATTERN.search(cleaned)
    if m_exp:
        digits = m_exp.group(1) or m_exp.group(2)
        val = int(digits)
        if 30 <= val <= 350:
            return digits

    # 2. Minor OCR fuzzy HP (HPD, HE, HB)
    m_fuz = _HP_FUZZY_PATTERN.search(cleaned)
    if m_fuz:
        digits = m_fuz.group(1) or m_fuz.group(2)
        val = int(digits)
        if 30 <= val <= 350:
            return digits

    # 3. Dedicated header or HP ROI search for multiple-of-10
    if is_header_or_hp_roi:
        for match in re.finditer(
            r"(?<![A-Za-z0-9/])([3-9]0|[1-3]\d0)(?![A-Za-z0-9/])", cleaned
        ):
            start = match.start()
            prefix = cleaned[max(0, start - 15) : start].lower()
            if any(
                p in prefix
                for p in [
                    "lv.",
                    "lv",
                    "no.",
                    "no",
                    "stage",
                    "evolves",
                    "©",
                    "199",
                    "200",
                    "/",
                    "illus",
                ]
            ):
                continue
            val = int(match.group(1))
            if 30 <= val <= 340 and val % 10 == 0:
                return match.group(1)

    return None


_ABILITY_INLINE_PATTERN = re.compile(
    r"(?:pok[eé]mon\s*power|pok[eé]\s*[\-\–]?\s*(?:power|body)|ability|vstar\s*power|ancient\s*trait)"
    r"[:\-\–\s]+"
    r"([A-Z][A-Za-z0-9\s\-\'\’]{2,30}?)"
    r"(?:\s+(?:as\s+often|once\s+during|when\s+you|if\s+|during\s+|you\s+may|this\s+|each\s+time|any\s+|all\s+|prevent\s+|whenever\s+|at\s+any\s+time|\(before)|\.|\n|$)",
    re.IGNORECASE,
)
_ABILITY_LINE_HEADER = re.compile(
    r"^(?:pok[eé]mon\s*power|pok[eé]\s*[\-\–]?\s*(?:power|body)|ability|vstar\s*power)$",
    re.IGNORECASE,
)
_NON_ATTACK_LINES = re.compile(
    r"(?:pok[eé]mon\s*power|pok[eé]\s*[\-\–]?\s*(?:power|body)|ability|vstar\s*power|"
    r"pok[eé]mon\.\s*length|length:|weight:|weakness|resistance|retreat|illus\.|©\s*\d|wizards|gamefreak|nintendo)",
    re.IGNORECASE,
)
_RULE_CLAUSE_STARTERS = re.compile(
    r"^(?:flip\s+a\s+coin|if\s+|this\s+attack|discard\s+|does\s+|choose\s+|during\s+|"
    r"attach\s+|search\s+|you\s+may|don\'t\s+apply|benched\s+|damage\s+to|all\s+energy|"
    r"like\s+during|rest\s+of|asleep|attached\s+to|put\s+|switch\s+|heal\s+|prevent\s+|"
    r"draw\s+|shuffle\s+|look\s+at|each\s+|both\s+|the\s+defending|your\s+opponent|unless|between\s+turns)",
    re.IGNORECASE,
)


def extract_attacks_and_abilities(body_text: str) -> tuple[list[str], list[str]]:
    """Extract attack and ability names from Pokémon card body text.

    Distinguishes ability names (modern Ability, vintage Pokémon Power/Poké-Power)
    from attack names with leading energy symbols and optional damage indicators.
    """
    if not body_text or not body_text.strip():
        return [], []

    abilities: list[str] = []
    attacks: list[str] = []

    # 1. Ability extraction
    # 1a. Inline pattern
    for m in _ABILITY_INLINE_PATTERN.finditer(body_text):
        cand = m.group(1).strip()
        if len(cand) >= 3 and cand not in abilities:
            abilities.append(cand)

    # 1b. Multiline header pattern (Ability / <Name> on next line)
    lines = [ln.strip() for ln in body_text.splitlines() if ln.strip()]
    for i, line in enumerate(lines[:-1]):
        if _ABILITY_LINE_HEADER.match(line):
            next_line = lines[i + 1]
            if re.match(r"^[A-Z][A-Za-z0-9\s\-\'\’]{2,30}$", next_line):
                if next_line not in abilities:
                    abilities.append(next_line)

    # 2. Attack extraction
    for line in lines:
        if _NON_ATTACK_LINES.search(line) or _RULE_CLAUSE_STARTERS.search(line):
            continue

        # Strip energy symbols / noise at start of attack line: e.g. [C], (), **, 22+, ©
        cleaned_start = re.sub(
            r"^(?:\[[A-Za-z0-9\s]*\]|\([A-Za-z0-9\s]*\)|[^\w\s]|[\d+x×*@©®¢\s])+",
            "",
            line,
        ).strip()
        if not cleaned_start or _RULE_CLAUSE_STARTERS.search(cleaned_start):
            continue

        # Skip if line belongs to an already recognized ability
        if any(ab.lower() in cleaned_start.lower() for ab in abilities):
            continue

        # Pattern A: Name followed by damage at end of line:
        # e.g. 'Surprise Attack 30', 'Earthquake 180'
        m_dmg = re.match(
            r"^([A-Z][A-Za-z\s\-\'\’]{2,25}?)\s+(\d{1,3}[\+x×\-]?)$", cleaned_start
        )
        if m_dmg:
            cand = m_dmg.group(1).strip()
            if len(cand) >= 3 and cand not in attacks:
                attacks.append(cand)
            continue

        # Pattern B: Name followed by rule text / description on same line:
        # e.g. 'Spark If your opponent...', 'Fire Spin Discard 2...'
        m_rule = re.match(
            r"^([A-Z][A-Za-z\s\-\'\’]{2,25}?)\s+(?:Discard|If|Flip|Does|This|Choose|Attach|Search|You|During|When|Put|\d{1,3}\b)",
            cleaned_start,
        )
        if m_rule:
            cand = m_rule.group(1).strip()
            if (
                len(cand) >= 3
                and cand not in attacks
                and not _RULE_CLAUSE_STARTERS.match(cand)
            ):
                attacks.append(cand)
            continue

        # Pattern C: Standalone clean attack name when preceded by energy symbols
        m_standalone = re.match(r"^([A-Z][A-Za-z\s\-\'\’]{2,25})$", cleaned_start)
        if m_standalone:
            cand = m_standalone.group(1).strip()
            filler = {
                "weakness",
                "resistance",
                "retreat cost",
                "flame pokémon",
                "gas pokémon",
                "stage",
                "basic",
            }
            if cand.lower() not in filler and len(cand) >= 3 and cand not in attacks:
                if len(line) > len(cleaned_start):
                    attacks.append(cand)

    return attacks, abilities


def extract_attacks(body_text: str) -> list[str]:
    """Convenience helper to extract attack names from body text."""
    attacks, _ = extract_attacks_and_abilities(body_text)
    return attacks


def extract_abilities(body_text: str) -> list[str]:
    """Convenience helper to extract ability names from body text."""
    _, abilities = extract_attacks_and_abilities(body_text)
    return abilities


def extract_card_info(
    header_ocr: OcrResult,
    footer_ocr: OcrResult,
    full_ocr: OcrResult | None = None,
    bottom_right_ocr: OcrResult | None = None,
    bottom_left_ocr: OcrResult | None = None,
    body_ocr: OcrResult | None = None,
    hp_ocr: OcrResult | None = None,
    header_full_ocr: OcrResult | None = None,
) -> CardExtractionResult:
    """Extract structured, evidence-aware card info from multiple OCR passes."""
    source_regions: dict[str, str] = {}

    # 1. Card Name from Header
    name = normalize_card_name(header_ocr.raw_text)
    if name:
        source_regions["name"] = "header"

    # Fallback for name from full card if header missed it
    if name is None and full_ocr is not None:
        for line in full_ocr.raw_text.splitlines():
            cand_name = normalize_card_name(line)
            if cand_name:
                name = cand_name
                source_regions["name"] = "full"
                break

    name_hypotheses = generate_name_hypotheses(name) if name else []
    name_confidence = (
        "high"
        if name and header_ocr.confidence >= 80
        else "medium"
        if name and header_ocr.confidence >= 45
        else "low"
    )

    # 2. HP from dedicated HP region, header, or full card
    hp: str | None = None
    if hp_ocr and hp_ocr.raw_text:
        cand_hp = normalize_hp(hp_ocr.raw_text, is_header_or_hp_roi=True)
        if cand_hp:
            hp = cand_hp
            source_regions["hp"] = "hp_roi"
    if hp is None and header_ocr and header_ocr.raw_text:
        cand_hp = normalize_hp(header_ocr.raw_text, is_header_or_hp_roi=True)
        if cand_hp:
            hp = cand_hp
            source_regions["hp"] = "header"
    if hp is None and header_full_ocr and header_full_ocr.raw_text:
        cand_hp = normalize_hp(header_full_ocr.raw_text, is_header_or_hp_roi=True)
        if cand_hp:
            hp = cand_hp
            source_regions["hp"] = "header_full"
    if hp is None and full_ocr and full_ocr.raw_text:
        cand_hp = normalize_hp(full_ocr.raw_text, is_header_or_hp_roi=False)
        if cand_hp:
            hp = cand_hp
            source_regions["hp"] = "full"

    # 3. Attacks and Abilities from Body
    attacks: list[str] = []
    abilities: list[str] = []
    if body_ocr and body_ocr.raw_text:
        attacks, abilities = extract_attacks_and_abilities(body_ocr.raw_text)
        if attacks:
            source_regions["attacks"] = "body"
        if abilities:
            source_regions["abilities"] = "body"
    if (not attacks or not abilities) and full_ocr and full_ocr.raw_text:
        f_attacks, f_abilities = extract_attacks_and_abilities(full_ocr.raw_text)
        if not attacks and f_attacks:
            attacks = f_attacks
            source_regions["attacks"] = "full"
        if not abilities and f_abilities:
            abilities = f_abilities
            source_regions["abilities"] = "full"

    # 4. Collector Number from targeted regions
    # (priority: bottom_right/bottom_left with slash, then footer)
    num_result = None
    for label, ocr_candidate in [
        ("bottom_right", bottom_right_ocr),
        ("bottom_left", bottom_left_ocr),
        ("footer", footer_ocr),
    ]:
        if ocr_candidate and ocr_candidate.raw_text:
            cand = normalize_collector_number(
                ocr_candidate.raw_text, source_region=label
            )
            if cand:
                if num_result is None or (
                    cand.strength == "strong" and num_result.strength != "strong"
                ):
                    num_result = cand
                    source_regions["number"] = label
                    if cand.strength == "strong":
                        break

    # Fallback to full card text if no number found yet
    if num_result is None and full_ocr is not None:
        cand = normalize_collector_number(full_ocr.raw_text, source_region="full")
        if cand:
            num_result = cand
            source_regions["number"] = "full"

    # Set Code detection from footer or number line
    number_line = ""
    target_footer = footer_ocr.raw_text if footer_ocr else ""
    if num_result:
        for line in target_footer.splitlines():
            if num_result.raw_number in line:
                number_line = line
                break
    set_code_match = _SET_CODE_PATTERN.search(number_line or target_footer)
    set_code = set_code_match.group(1) if set_code_match else None
    if set_code:
        source_regions["set_code"] = "footer"

    # Overall raw text combined
    combined_raw_parts = [
        f"[Header]: {header_ocr.raw_text.strip()}" if header_ocr.raw_text else "",
        f"[Footer]: {footer_ocr.raw_text.strip()}" if footer_ocr.raw_text else "",
    ]
    if bottom_right_ocr and bottom_right_ocr.raw_text:
        combined_raw_parts.append(
            f"[Bottom right]: {bottom_right_ocr.raw_text.strip()}"
        )
    if bottom_left_ocr and bottom_left_ocr.raw_text:
        combined_raw_parts.append(f"[Bottom left]: {bottom_left_ocr.raw_text.strip()}")
    if body_ocr and body_ocr.raw_text:
        combined_raw_parts.append(f"[Body]: {body_ocr.raw_text.strip()}")
    if hp_ocr and hp_ocr.raw_text:
        combined_raw_parts.append(f"[HP]: {hp_ocr.raw_text.strip()}")
    if full_ocr and full_ocr.raw_text:
        combined_raw_parts.append(f"[Full]: {full_ocr.raw_text.strip()}")
    combined_raw = "\n".join(p for p in combined_raw_parts if p)

    # Average confidence calculation
    confs = [c for c in [header_ocr.confidence, footer_ocr.confidence] if c > 0]
    avg_conf = round(sum(confs) / len(confs), 2) if confs else 0.0

    return CardExtractionResult(
        raw_text=combined_raw[:2000],  # Bound text size
        name=name,
        name_hypotheses=name_hypotheses,
        name_confidence=name_confidence,
        number=num_result.full_formatted if num_result else None,
        local_id=num_result.local_id if num_result else None,
        printed_denominator=num_result.denominator if num_result else None,
        number_strength=num_result.strength if num_result else "none",
        set_code=set_code,
        confidence=avg_conf,
        alternatives=num_result.alternatives if num_result else [],
        source_regions=source_regions,
        hp=hp,
        attacks=attacks,
        abilities=abilities,
    )
