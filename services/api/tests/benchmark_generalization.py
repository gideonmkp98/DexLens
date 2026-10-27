"""Opt-in live benchmark: python -m tests.benchmark_generalization.

Downloads only the listed catalog cards. No database writes. Catalog scans and
synthetic images are explicitly not evidence of camera-photo accuracy.
"""

import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path

import httpx

from app.services.catalog.matcher import retrieve_and_rank_candidates
from app.services.catalog.ranker import derive_confidence_state
from app.services.catalog.visual_matcher import rerank_by_artwork
from app.services.ocr.engine import TesseractOcrEngine
from app.services.ocr.pipeline import recognize_card_image
from app.services.tcgdex import TcgdexClient

NEW_IDS = [
    "base1-53",
    "base1-62",
    "base1-49",
    "base1-88",
    "base1-96",
    "base3-54",
    "hgss1-110",
    "sm8-18",
    "swsh8-157",
    "swsh8-225",
    "sv03.5-006",
    "sv03.5-183",
    "sv01-198",
    "swsh12.5-GG44",
    "ex7-10",
    "dp1-1",
    "ecard1-1",
    "xy1-141",
    "xy12-101",
    "sm3.5-73",
    "swshp-SWSH020",
]


async def main():
    root = Path(__file__).parent / "fixtures"
    downloads = root / "additional_catalog"
    downloads.mkdir(exist_ok=True)
    cases = []
    results = []
    engine = TesseractOcrEngine()
    async with TcgdexClient() as client, httpx.AsyncClient(timeout=15) as http:
        for cid in NEW_IDS:
            card = await client.get_card(cid)
            if not card or not card.get("image"):
                results.append(
                    {
                        "id": cid,
                        "category": "additional_catalog",
                        "error": "No provider image",
                    }
                )
                continue
            path = downloads / f"{cid}.webp"
            if not path.exists():
                response = await http.get(card["image"] + "/high.webp")
                response.raise_for_status()
                path.write_bytes(response.content)
            cases.append((cid, "additional_catalog", path))
        for path in sorted((root / "eval_cards").glob("*")):
            if path.suffix in {".jpg", ".webp"}:
                cid, kind = path.stem.rsplit("_", 1)
                cases.append((cid, kind, path))
        for file, cid in [
            ("geodude-fossil.jpg", "base3-47"),
            ("meganium-prime.jpg", "hgss1-109"),
            ("meganium-lost-thunder.jpg", "sm8-8"),
            ("charizard.jpg", "base4-4"),
            ("pikachu.jpg", "base2-60"),
            ("gastly.jpg", "me03-048"),
            ("steelix.jpg", "swsh8-139"),
        ]:
            cases.append(
                (cid, "user_scan_regression", root / "regression_scans" / file)
            )
        for cid, category, path in cases:
            start = time.monotonic()
            try:
                extraction = recognize_card_image(path, engine)
                candidates, total = await retrieve_and_rank_candidates(
                    client,
                    name=extraction.name,
                    number=extraction.number,
                    set_code=extraction.set_code,
                    alternatives=extraction.alternatives,
                    name_hypotheses=extraction.name_hypotheses,
                    name_confidence=extraction.name_confidence,
                    number_strength=extraction.number_strength,
                    extraction=extraction,
                    limit=32 if extraction.printed_denominator else 128,
                )
                candidates = (await rerank_by_artwork(path, candidates))[:5]
                confidence = derive_confidence_state(
                    candidates,
                    is_low_res=extraction.image_quality.get("is_low_res", False),
                )
                correct = bool(candidates and candidates[0].id == cid)
                result = {
                    "id": cid,
                    "category": category,
                    "name": extraction.name,
                    "number": extraction.number,
                    "rank1": correct,
                    "top5": any(c.id == cid for c in candidates),
                    "false_high": not correct and confidence == "high",
                    "confidence": confidence,
                    "pool_size": total,
                    "seconds": round(time.monotonic() - start, 2),
                    "candidates": [asdict(c) for c in candidates],
                }
            except Exception as exc:
                result = {"id": cid, "category": category, "error": str(exc)}
            results.append(result)
            print(
                json.dumps({k: v for k, v in result.items() if k != "candidates"}),
                flush=True,
            )
            Path("/tmp/recognition-generalization.json").write_text(
                json.dumps(results, indent=2)
            )


if __name__ == "__main__":
    asyncio.run(main())
