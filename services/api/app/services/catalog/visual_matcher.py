"""Bounded, optional artwork comparison for ambiguous OCR candidates.

Only catalog thumbnails are downloaded; the user's photograph stays local.
Visual agreement helps ordering but is not proof of a particular printing.
"""

import asyncio
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlsplit

import cv2
import httpx
import numpy as np

from app.services.catalog.ranker import CandidateMatch

_cache: OrderedDict[str, tuple[float, np.ndarray]] = OrderedDict()


def artwork(image: np.ndarray) -> np.ndarray:
    normalized = cv2.resize(image, (150, 210), interpolation=cv2.INTER_AREA)
    # Exclude the frame, title, rules and footer; these repeat across printings.
    return normalized[32:125, 12:138].astype(np.float32)


def artwork_similarity(left: np.ndarray, right: np.ndarray) -> float:
    a, b = artwork(left), artwork(right)
    # Spatial correlation is insensitive to moderate exposure differences.
    a_gray = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    b_gray = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    if a_gray.std() < 4 or b_gray.std() < 4:
        return 0.0
    correlation = float(np.corrcoef(a_gray.ravel(), b_gray.ravel())[0, 1])
    colour_error = float(np.mean(np.abs(a / 255 - b / 255)))
    return max(0.0, min(1.0, 0.8 * correlation + 0.2 * (1 - colour_error)))


async def rerank_by_artwork(
    crop_path: Path,
    candidates: list[CandidateMatch],
) -> list[CandidateMatch]:
    source = await asyncio.to_thread(cv2.imread, str(crop_path))
    if source is None:
        return candidates
    semaphore = asyncio.Semaphore(8)

    async with httpx.AsyncClient(timeout=3.0, follow_redirects=False) as client:

        async def compare(candidate: CandidateMatch) -> None:
            url = candidate.image_url
            if not url or candidate.score < 10:
                return
            parts = urlsplit(url)
            if parts.scheme != "https" or parts.netloc != "assets.tcgdex.net":
                return
            async with semaphore:
                cached = _cache.get(url)
                if cached and time.monotonic() - cached[0] < 600:
                    thumbnail = cached[1]
                    _cache.move_to_end(url)
                else:
                    try:
                        async with client.stream("GET", url) as response:
                            response.raise_for_status()
                            data = bytearray()
                            async for chunk in response.aiter_bytes():
                                data.extend(chunk)
                                if len(data) > 2_000_000:
                                    return
                        thumbnail = cv2.imdecode(
                            np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR
                        )
                        if thumbnail is None:
                            return
                        thumbnail = cv2.resize(thumbnail, (150, 210))
                    except (httpx.HTTPError, cv2.error):
                        return  # Optional evidence must not break OCR/search.
                    _cache[url] = (time.monotonic(), thumbnail)
                    while len(_cache) > 256:
                        _cache.popitem(last=False)

                similarity = artwork_similarity(source, thumbnail)
                # Orientation handling: if score is low, test 180-degree rotation
                if similarity < 0.65:
                    source_rot180 = cv2.rotate(source, cv2.ROTATE_180)
                    rot_sim = artwork_similarity(source_rot180, thumbnail)
                    if rot_sim > similarity:
                        similarity = rot_sim

                candidate.visual_similarity = round(float(similarity), 3)
                if similarity >= 0.65:
                    candidate.score = min(100, candidate.score + round(25 * similarity))
                    if similarity >= 0.9:
                        # Near-identical artwork can rescue a printing whose
                        # missing OCR suffix kept it below older name matches.
                        # Confidence still requires independent textual evidence
                        # and a margin; shared artwork alone cannot confirm it.
                        candidate.score = max(candidate.score, 85)
                    if any("conflicts" in r for r in candidate.reasons):
                        candidate.score = min(candidate.score, 59)
                    candidate.reasons.append(
                        "Artwork resembles the scan; "
                        "printing still requires confirmation"
                    )

        # Keep provider work bounded even for common names with many printings.
        try:
            async with asyncio.timeout(10):
                await asyncio.gather(*(compare(c) for c in candidates[:128]))
        except TimeoutError:
            pass
    return sorted(candidates, key=lambda c: (-c.score, c.id))
