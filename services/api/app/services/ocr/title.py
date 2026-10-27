"""Select title text by word geometry rather than confidence of the whole ROI."""

import re

from app.services.ocr.engine import OcrResult
from app.services.ocr.normalizer import normalize_card_name

_LABELS = {
    "basic",
    "sasic",
    "stage",
    "stage1",
    "stage2",
    "pokemon",
    "pokémon",
    "hp",
    "evolves",
    "from",
    "trainer",
    "supporter",
    "item",
    "energy",
}


def title_from_words(result: OcrResult) -> OcrResult | None:
    words = [
        w
        for w in result.words
        if w.bbox
        and w.confidence >= 40
        and re.search(r"[A-Za-z]{3}", w.text)
        and w.text.lower().strip("().:") not in _LABELS
    ]
    if not words:
        return None
    # The title is larger than evolution instructions. Confidence alone often
    # prefers the small 'Basic Pokémon' label over the actual name.
    anchor = max(words, key=lambda w: w.bbox[3] * (0.5 + w.confidence / 200))
    ax, ay, aw, ah = anchor.bbox
    line = []
    for word in result.words:
        if not word.bbox:
            continue
        x, y, width, height = word.bbox
        token = word.text.strip("()|.,:'\"")
        is_suffix = token.lower() in {"ex", "gx", "v", "vmax", "vstar", "lv.x"}
        if (
            abs(y + height / 2 - ay - ah / 2) <= ah * 0.45
            and height >= ah * 0.5
            and (word.confidence >= 40 or is_suffix)
            and (re.search(r"[A-Za-z]{3}", token) or is_suffix)
            and token.lower() not in _LABELS
        ):
            line.append(word)
    line.sort(key=lambda w: w.bbox[0])
    # Follow neighboring words across a multiword title. Measuring every word's
    # distance from the anchor clips titles such as 'Battle VIP Pass'. A large
    # gap still separates the title from HP/type labels.
    anchor_index = line.index(anchor) if anchor in line else None
    if anchor_index is None:
        return None
    left = right = anchor_index
    while left > 0:
        previous, current = line[left - 1], line[left]
        if current.bbox[0] - previous.bbox[0] - previous.bbox[2] > ah * 1.5:
            break
        left -= 1
    while right < len(line) - 1:
        current, following = line[right], line[right + 1]
        if following.bbox[0] - current.bbox[0] - current.bbox[2] > ah * 1.5:
            break
        right += 1
    line = line[left : right + 1]
    if any(w.text.lower().strip(".,:") in {"put", "evolves", "from"} for w in line):
        return None
    name = normalize_card_name(" ".join(w.text for w in line))
    if not name or not line:
        return None
    confidence = sum(w.confidence for w in line) / len(line)
    if confidence < 55:
        return None
    return OcrResult(raw_text=name, confidence=confidence, words=line)
