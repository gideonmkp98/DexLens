"""Bounded region selection shared by the API and OCR regression tests."""

import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from app.core.config import settings
from app.services.ocr.engine import OcrEngineProtocol, OcrResult, OcrTimeoutError
from app.services.ocr.normalizer import (
    CardExtractionResult,
    extract_attacks_and_abilities,
    extract_card_info,
    normalize_card_name,
    normalize_collector_number,
    normalize_hp,
)
from app.services.ocr.preprocessor import prepare_card_regions
from app.services.ocr.title import title_from_words


def _needs_number_retry(number):
    if number is None or number.denominator is None:
        return True
    # A severely disproportionate pair can be a clipped denominator. Do not
    # reject secret rares; just seek another independent reading before using it.
    return (
        number.local_id.isdigit()
        and number.denominator.isdigit()
        and int(number.local_id) > 10 * int(number.denominator)
    )


def recognize_card_image(path: Path, engine: OcrEngineProtocol) -> CardExtractionResult:
    deadline = time.monotonic() + settings.OCR_TIMEOUT_SECONDS
    regions = prepare_card_regions(path)
    header = engine.recognize(regions.header_enhanced, psm=6, deadline=deadline)
    footer = engine.recognize(regions.footer_enhanced, psm=6, deadline=deadline)
    attempts = [("Header", header), ("Footer", footer)]
    budget_exhausted = False

    def optional_recognize(image, **kwargs):
        nonlocal budget_exhausted
        if budget_exhausted or time.monotonic() >= deadline - 0.1:
            budget_exhausted = True
            return OcrResult("", 0)
        try:
            return engine.recognize(image, **kwargs)
        except OcrTimeoutError:
            # The primary header/footer have already succeeded. An optional
            # refinement must not discard their usable evidence.
            budget_exhausted = True
            return OcrResult("", 0)

    # Validate tiny collector pairs in an unclipped bottom band. Independent
    # light/dark readings can outvote a plausible but wrong digit (101 vs 001).
    footer_reads = [footer]
    for roi in regions.footer_validation if regions.footer_clean.std() >= 5 else []:
        if roi.std() >= 5:
            result = optional_recognize(roi, psm=11, deadline=deadline)
            attempts.append(("Footer validation", result))
            footer_reads.append(result)
    pairs = [(r, normalize_collector_number(r.raw_text)) for r in footer_reads]
    pairs = [(r, n) for r, n in pairs if n and n.denominator]
    # A clipped reading such as 157/2 must not outvote the observed 157/264.
    pairs = [
        (r, n)
        for r, n in pairs
        if not any(
            other.local_id == n.local_id
            and other.denominator != n.denominator
            and other.denominator.startswith(n.denominator)
            for _, other in pairs
        )
    ]
    votes = Counter(n.full_formatted for _, n in pairs)
    if pairs:

        def pair_confidence(item):
            result, number = item
            word_conf = [
                w.confidence for w in result.words if number.raw_number in w.text
            ]
            return (
                votes[number.full_formatted],
                max(word_conf, default=result.confidence),
            )

        footer = max(pairs, key=pair_confidence)[0]

    # Sparse text on the unenhanced header avoids amplifying textured artwork.
    if normalize_card_name(header.raw_text) is None or header.confidence < 75:
        alternate = optional_recognize(regions.header_clean, psm=11, deadline=deadline)
        attempts.append(("Header sparse", alternate))
        if normalize_card_name(alternate.raw_text) is not None and (
            normalize_card_name(header.raw_text) is None
            or alternate.confidence > header.confidence
        ):
            header = alternate

        header_name = normalize_card_name(header.raw_text)
        if header.confidence < 65 and (
            not header_name or len(header_name.split()) > 2 or header.confidence < 35
        ):
            alternate = optional_recognize(
                regions.header_sparse, psm=11, deadline=deadline
            )
            attempts.append(("Header enlarged", alternate))
            if normalize_card_name(alternate.raw_text) and (
                normalize_card_name(header.raw_text) is None
                or alternate.confidence > header.confidence
            ):
                header = alternate

    title_choices = []
    # Retain readable primary title words: a refinement must compete with them,
    # rather than unconditionally replacing them with a clipped fragment.
    primary_title = title_from_words(header)
    if primary_title:
        title_choices.append(primary_title)
    if (
        header.confidence < 85
        and regions.title_wide.size
        and regions.title_wide.std() >= 5
    ):
        alternate = optional_recognize(regions.title_wide, psm=6, deadline=deadline)
        attempts.append(("Wide title", alternate))
        choice = title_from_words(alternate)
        if choice:
            title_choices.append(choice)
    if (
        header.confidence < 85
        and regions.header_full.size
        and regions.header_full.std() >= 5
    ):
        alternate = optional_recognize(regions.header_full, psm=11, deadline=deadline)
        attempts.append(("Full title", alternate))
        choice = title_from_words(alternate)
        if choice:
            title_choices.append(choice)
    for roi in regions.title_variants if header.confidence < 75 else []:
        if roi.std() < 5:
            continue
        alternate = optional_recognize(roi, psm=6, deadline=deadline)
        attempts.append(("Title", alternate))
        choice = title_from_words(alternate)
        if choice:
            title_choices.append(choice)
    if title_choices:
        # Compare confidence of title words, not background/evolution noise.
        # A clipped fragment can have slightly higher confidence than the full
        # word. Prefer completeness when confidence differs only marginally.
        header = max(
            title_choices, key=lambda c: c.confidence + 3 * min(12, len(c.raw_text))
        )

    bottom_right = None
    bottom_left = None
    number = normalize_collector_number(footer.raw_text)
    # A loose number in card-description text is weaker than a collector pair.
    if _needs_number_retry(number):
        br_ocr = optional_recognize(
            regions.bottom_right_enhanced, psm=6, deadline=deadline
        )
        attempts.append(("Bottom right", br_ocr))
        bottom_right = br_ocr
        cand_br = normalize_collector_number(br_ocr.raw_text)
        if cand_br and (number is None or cand_br.denominator is not None):
            footer, number = br_ocr, cand_br

        if _needs_number_retry(number):
            bl_ocr = optional_recognize(
                regions.bottom_left_enhanced, psm=6, deadline=deadline
            )
            attempts.append(("Bottom left", bl_ocr))
            bottom_left = bl_ocr
            cand_bl = normalize_collector_number(bl_ocr.raw_text)
            if cand_bl and (number is None or cand_bl.denominator is not None):
                footer, number = bl_ocr, cand_bl

    # Narrow, unenhanced strips preserve tiny collector digits that are lost
    # among rules/retreat text in the larger footer regions.
    if _needs_number_retry(number):
        for label, roi, psm in [
            ("Footer line", regions.footer_line, 6),
            ("Footer number left", regions.footer_number_left, 11),
        ]:
            attempt = optional_recognize(roi, psm=psm, deadline=deadline)
            attempts.append((label, attempt))
            candidate = normalize_collector_number(attempt.raw_text)
            if candidate and candidate.denominator:
                footer, number = attempt, candidate
                bottom_right = bottom_left = None
                break

    if _needs_number_retry(number):
        for roi in regions.number_variants:
            if roi.std() < 5:
                continue
            attempt = optional_recognize(roi, psm=11, deadline=deadline)
            attempts.append(("Footer dark ink", attempt))
            candidate = normalize_collector_number(attempt.raw_text)
            if candidate and candidate.denominator:
                footer, number = attempt, candidate
                bottom_right = bottom_left = None
                break

    # Body OCR: attacks, abilities, rules text
    body = None
    if regions.body_clean.size > 0:
        body = optional_recognize(regions.body_clean, psm=6, deadline=deadline)
        attempts.append(("Body", body))
        cand_attacks, cand_abilities = extract_attacks_and_abilities(body.raw_text)
        if (
            not cand_attacks
            and not cand_abilities
            and regions.body_enhanced.size > 0
            and (deadline - time.monotonic() > 0.5)
        ):
            body_enh = optional_recognize(
                regions.body_enhanced, psm=6, deadline=deadline
            )
            cand_at2, cand_ab2 = extract_attacks_and_abilities(body_enh.raw_text)
            if cand_at2 or cand_ab2:
                body = body_enh
                attempts.append(("Body enhanced", body_enh))

    # HP OCR: header or dedicated HP region
    hp_ocr = None
    header_full_ocr = None
    hp_val = normalize_hp(header.raw_text, is_header_or_hp_roi=True)
    if hp_val is None and (deadline - time.monotonic() > 0.5):
        if regions.hp_crop.size > 0:
            hp_ocr = optional_recognize(regions.hp_crop, psm=6, deadline=deadline)
            attempts.append(("HP", hp_ocr))
            hp_val = normalize_hp(hp_ocr.raw_text, is_header_or_hp_roi=True)
        if (
            hp_val is None
            and regions.header_full.size > 0
            and (deadline - time.monotonic() > 0.5)
        ):
            header_full_ocr = optional_recognize(
                regions.header_full, psm=6, deadline=deadline
            )
            attempts.append(("Header full", header_full_ocr))

    full = None
    if normalize_card_name(header.raw_text) is None or number is None:
        full = optional_recognize(regions.full_image_gray, psm=11, deadline=deadline)
        attempts.append(("Full", full))

    extracted = extract_card_info(
        header_ocr=header,
        footer_ocr=footer,
        full_ocr=full,
        bottom_right_ocr=bottom_right,
        bottom_left_ocr=bottom_left,
        body_ocr=body,
        hp_ocr=hp_ocr,
        header_full_ocr=header_full_ocr,
    )
    extracted.image_quality = asdict(regions.image_quality)
    if budget_exhausted:
        extracted.image_quality["warning"] = (
            (extracted.image_quality.get("warning") or "")
            + " Extra tekstcontrole bereikte de tijdslimiet. "
            "Controleer het resultaat of voer OCR opnieuw uit."
        ).strip()
    # Keep selected evidence first so diagnostics cannot push useful body text
    # beyond the storage limit when difficult headers require several retries.
    selected = [("Selected header", header), ("Selected footer", footer)]
    if body:
        selected.append(("Selected body", body))
    extracted.raw_text = "\n".join(
        f"[{label}]: {result.raw_text}" for label, result in selected + attempts
    )[:2000]
    return extracted
