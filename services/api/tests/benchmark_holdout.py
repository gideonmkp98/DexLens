"""Independent deterministic catalog sample; never described as real photos.

Run once after freezing recognition changes. Subsequent runs are regressions,
not new evidence of generalization. Does not write to the application's DB.
"""

import asyncio
import json
import random
from dataclasses import asdict
from pathlib import Path

import httpx

from app.services.ocr.engine import TesseractOcrEngine
from app.services.tcgdex import TcgdexClient
from tests.evaluate_recognition_quality import evaluate_single_image


async def main():
    rng = random.Random(20261027)
    results = []
    root = Path("/tmp/recognition-holdout")
    root.mkdir(exist_ok=True)
    async with TcgdexClient() as client, httpx.AsyncClient(timeout=15) as http:
        for sid in [
            "base1",
            "hgss2",
            "bw1",
            "xy7",
            "sm12",
            "swsh7",
            "sv02",
            "sv04",
            "sv09",
            "svp",
        ]:
            set_data = await client.get_set(sid)
            summaries = [c for c in set_data["cards"] if c.get("image")]
            summary = rng.choice(summaries)
            card = await client.get_card(summary["id"])
            path = root / (card["id"] + ".webp")
            response = await http.get(card["image"] + "/high.webp")
            response.raise_for_status()
            path.write_bytes(response.content)
            result = await evaluate_single_image(
                client,
                TesseractOcrEngine(),
                path,
                card["id"],
                "heldout_catalog",
                card["id"],
                card["name"],
                str(card["localId"]) + "/" + str(set_data["cardCount"]["official"]),
                str(card["localId"]),
            )
            results.append(asdict(result))
            print(json.dumps(asdict(result)), flush=True)
            Path("/tmp/recognition-holdout.json").write_text(
                json.dumps(results, indent=2)
            )


if __name__ == "__main__":
    asyncio.run(main())
