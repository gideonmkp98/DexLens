"""Evaluation benchmark and recognition quality assessment for Pokemon TCG scanner.

Measures evidence-aware recognition quality across:
1. Real Photographs (dev set + held-out evaluation set):
   vintage/modern, close-up, low-res.
2. Clean Catalog Scans (never described as real photographs).
3. Synthetic Distortions (rotated, noisy, blurred).
4. Cropping Quality (corner detection & whole-card retention of title and number).
5. Held-Out Evaluation Set Coverage & Gap Analysis.

Metrics computed:
- Exact printing match at rank 1 (count and %)
- Exact printing match in top 5 (count and %)
- False high-confidence rate (incorrect predictions labeled high confidence)
- Abstention / no-match rate
- Card name extraction accuracy
- Collector-number extraction accuracy (numerator and full number)
- Cropping quality (corner boundaries, title/footer preservation)
- End-to-end latency: mean, p50 (median), and p95
"""

import asyncio
import json
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.services.card_detector import detect_card_corners
from app.services.catalog.matcher import retrieve_and_rank_candidates
from app.services.catalog.ranker import derive_confidence_state
from app.services.catalog.visual_matcher import rerank_by_artwork
from app.services.crop_service import perform_crop_and_warp
from app.services.ocr.engine import get_ocr_engine
from app.services.ocr.pipeline import recognize_card_image
from app.services.tcgdex import TcgdexClient

# Deterministic seed for reproducible synthetic image generation
np.random.seed(42)

BASE_DIR = Path(__file__).parent
FIXTURES_DIR = BASE_DIR / "fixtures"
EVAL_CARDS_DIR = FIXTURES_DIR / "eval_cards"
REGRESSION_SCANS_DIR = FIXTURES_DIR / "regression_scans"
MANIFEST_PATH = FIXTURES_DIR / "eval_manifest.json"

EVAL_CARDS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ItemEvalResult:
    item_id: str
    category: str
    expected_card_id: str | None
    expected_name: str | None
    expected_number: str | None
    expected_local_id: str | None
    ocr_name: str | None
    ocr_number: str | None
    ocr_local_id: str | None
    name_matched: bool
    numerator_matched: bool
    full_number_matched: bool
    rank_1_exact: bool
    top_5_exact: bool
    top_5_name_recall: bool
    confidence_state: str
    is_false_high_confidence: bool
    no_result: bool
    latency_ms: float
    rank_1_card_id: str | None = None
    rank_1_card_name: str | None = None
    rank_1_score: int = 0
    negative_assertion_passed: bool = True
    error_note: str | None = None


@dataclass
class CroppingEvalResult:
    item_id: str
    file_name: str
    detection_found: bool
    corners_enclosing: bool
    title_preserved: bool
    footer_preserved: bool
    extracted_name: str | None
    extracted_number: str | None
    rank_1_card_id: str | None
    rank_1_matched: bool
    latency_ms: float
    details: str


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"Manifest not found at {MANIFEST_PATH}")
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def prepare_clean_catalog_fixtures(
    catalog_items: list[dict[str, Any]],
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for item in catalog_items:
        cid = item["id"]
        dest = EVAL_CARDS_DIR / f"{cid}_clean.webp"
        if not dest.is_file() or dest.stat().st_size == 0:
            url = item.get("url")
            if url:
                print(f"Downloading clean catalog image {cid} from {url}...")
                try:
                    urllib.request.urlretrieve(url, dest)
                except Exception as e:
                    print(f"  Warning: failed to download {cid}: {e}")
                    continue
        if dest.is_file() and dest.stat().st_size > 0:
            paths[cid] = dest
    return paths


def prepare_synthetic_distortions(
    catalog_items: list[dict[str, Any]], clean_paths: dict[str, Path]
) -> dict[str, Path]:
    synthetic_paths: dict[str, Path] = {}
    for item in catalog_items:
        cid = item["id"]
        if cid not in clean_paths:
            continue
        dest = EVAL_CARDS_DIR / f"{cid}_synthetic.jpg"
        if dest.is_file() and dest.stat().st_size > 0:
            synthetic_paths[cid] = dest
            continue

        src = cv2.imread(str(clean_paths[cid]))
        if src is None:
            continue
        h, w = src.shape[:2]

        # Transformation: +3 degree rotation, Gaussian noise, Gaussian blur
        m = cv2.getRotationMatrix2D((w / 2, h / 2), 3.0, 1.0)
        rotated = cv2.warpAffine(src, m, (w, h), borderMode=cv2.BORDER_REPLICATE)
        noise = np.random.normal(0, 4.0, rotated.shape).astype(np.float32)
        noisy = np.clip(rotated.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        blurred = cv2.GaussianBlur(noisy, (3, 3), 0.5)

        cv2.imwrite(str(dest), blurred)
        synthetic_paths[cid] = dest
    return synthetic_paths


async def evaluate_single_image(
    client: TcgdexClient,
    engine: Any,
    img_path: Path,
    item_id: str,
    category: str,
    expected_card_id: str | None,
    expected_name: str | None,
    expected_number: str | None,
    expected_local_id: str | None,
    negative_assertions: list[str] | None = None,
) -> ItemEvalResult:
    t0 = time.perf_counter()
    extracted = recognize_card_image(img_path, engine)

    # Higher candidate pool limit when denominator is absent
    limit = 32 if extracted.printed_denominator else 128
    candidates, total_found = await retrieve_and_rank_candidates(
        client=client,
        name=extracted.name,
        number=extracted.number,
        set_code=extracted.set_code,
        alternatives=extracted.alternatives,
        name_hypotheses=extracted.name_hypotheses,
        name_confidence=extracted.name_confidence,
        number_strength=extracted.number_strength,
        extraction=extracted,
        limit=limit,
    )

    # When denominator is absent or unverified, visual matching reranks candidates
    if candidates:
        candidates = await rerank_by_artwork(img_path, candidates)

    candidates = candidates[:5]
    t1 = time.perf_counter()
    latency_ms = (t1 - t0) * 1000

    # Text extraction metrics
    exp_name = (expected_name or "").lower().strip()
    got_name = (extracted.name or "").lower().strip()
    name_matched = bool(
        exp_name
        and (
            exp_name in got_name
            or any(exp_name in h.lower() for h in extracted.name_hypotheses)
        )
    )

    exp_num = (expected_number or "").lower().strip()
    exp_loc = (expected_local_id or "").lower().strip()
    got_num = (extracted.number or "").lower().strip()
    got_loc = (extracted.local_id or "").lower().strip()

    full_num_matched = bool(exp_num and got_num == exp_num)
    numerator_matched = bool(
        exp_loc
        and (
            got_loc == exp_loc
            or any(
                a.split("/")[0].strip().lower() == exp_loc
                for a in extracted.alternatives
            )
        )
    )

    # Candidate ranking metrics
    exp_cid = (expected_card_id or "").lower().strip()
    rank_1_exact = bool(candidates and candidates[0].id.lower() == exp_cid)
    top_5_exact = bool(any(c.id.lower() == exp_cid for c in candidates))
    top_5_name = bool(exp_name and any(exp_name in c.name.lower() for c in candidates))

    conf_state = derive_confidence_state(
        candidates,
        is_low_res=extracted.image_quality.get("is_low_res", False),
    )

    # QA metric: False high-confidence occurs when high confidence is on wrong card
    is_false_high_conf = bool(conf_state == "high" and not rank_1_exact)

    # Negative assertions (e.g. Steelix must NOT be labeled ex7-10)
    neg_passed = True
    if negative_assertions:
        for forbidden in negative_assertions:
            if candidates and candidates[0].id.lower() == forbidden.lower():
                neg_passed = False

    r1_id = candidates[0].id if candidates else None
    r1_name = candidates[0].name if candidates else None
    r1_score = candidates[0].score if candidates else 0

    return ItemEvalResult(
        item_id=item_id,
        category=category,
        expected_card_id=expected_card_id,
        expected_name=expected_name,
        expected_number=expected_number,
        expected_local_id=expected_local_id,
        ocr_name=extracted.name,
        ocr_number=extracted.number,
        ocr_local_id=extracted.local_id,
        name_matched=name_matched,
        numerator_matched=numerator_matched,
        full_number_matched=full_num_matched,
        rank_1_exact=rank_1_exact,
        top_5_exact=top_5_exact,
        top_5_name_recall=top_5_name,
        confidence_state=conf_state,
        is_false_high_confidence=is_false_high_conf,
        no_result=len(candidates) == 0,
        latency_ms=latency_ms,
        rank_1_card_id=r1_id,
        rank_1_card_name=r1_name,
        rank_1_score=r1_score,
        negative_assertion_passed=neg_passed,
    )


async def evaluate_cropping_quality(
    client: TcgdexClient, engine: Any, item: dict[str, Any]
) -> CroppingEvalResult:
    rel_file = item["file"]
    path = FIXTURES_DIR / rel_file
    t0 = time.perf_counter()

    found, corners, score, method = detect_card_corners(path)
    if not found:
        t1 = time.perf_counter()
        return CroppingEvalResult(
            item_id=item["id"],
            file_name=rel_file,
            detection_found=False,
            corners_enclosing=False,
            title_preserved=False,
            footer_preserved=False,
            extracted_name=None,
            extracted_number=None,
            rank_1_card_id=None,
            rank_1_matched=False,
            latency_ms=(t1 - t0) * 1000,
            details="Card detection failed to locate corners.",
        )

    # Check that corners retain full card geometry without clipping headers/footers
    criteria = item.get("expected_corners_criteria", {})
    tl_max = criteria.get("top_left_x_max", 0.10)
    tr_min = criteria.get("top_right_x_min", 0.90)
    bl_min = criteria.get("bottom_left_y_min", 0.90)
    br_min = criteria.get("bottom_right_y_min", 0.90)

    corners_ok = (
        corners.top_left.x <= tl_max
        and corners.top_right.x >= tr_min
        and corners.bottom_left.y >= bl_min
        and corners.bottom_right.y >= br_min
    )

    tmp_crop = Path(f"/tmp/{item['id']}_eval_crop.jpg")
    try:
        w, h, sz = perform_crop_and_warp(path, tmp_crop, corners)
        extracted = recognize_card_image(tmp_crop, engine)
        candidates, _ = await retrieve_and_rank_candidates(
            client=client,
            name=extracted.name,
            number=extracted.number,
            set_code=extracted.set_code,
            alternatives=extracted.alternatives,
            name_hypotheses=extracted.name_hypotheses,
            name_confidence=extracted.name_confidence,
            number_strength=extracted.number_strength,
            limit=5,
        )
    finally:
        if tmp_crop.is_file():
            tmp_crop.unlink()

    t1 = time.perf_counter()
    latency_ms = (t1 - t0) * 1000

    exp_name = (item.get("expected_name") or "").lower()
    title_ok = bool(
        exp_name
        and (
            exp_name in (extracted.name or "").lower()
            or any(exp_name in h.lower() for h in extracted.name_hypotheses)
        )
    )
    footer_ok = bool(extracted.number == item.get("expected_number"))
    r1_id = candidates[0].id if candidates else None
    r1_matched = bool(r1_id and r1_id.lower() == str(item.get("card_id")).lower())

    details = (
        f"Corners ({corners.top_left.x:.2f},{corners.top_left.y:.2f}) to "
        f"({corners.bottom_right.x:.2f},{corners.bottom_right.y:.2f}) -> "
        f"Crop {w}x{h}px | Name: '{extracted.name}' | Number: '{extracted.number}'"
    )

    return CroppingEvalResult(
        item_id=item["id"],
        file_name=rel_file,
        detection_found=True,
        corners_enclosing=corners_ok,
        title_preserved=title_ok,
        footer_preserved=footer_ok,
        extracted_name=extracted.name,
        extracted_number=extracted.number,
        rank_1_card_id=r1_id,
        rank_1_matched=r1_matched,
        latency_ms=latency_ms,
        details=details,
    )


def print_category_summary(
    cat_name: str, results: list[ItemEvalResult], note: str | None = None
) -> None:
    count = len(results)
    print("\n===============================================================")
    print(f"CATEGORY: {cat_name} (n={count})")
    if note:
        print(f"NOTE: {note}")
    print("===============================================================")

    if count == 0:
        print("  No samples evaluated in this category.")
        return

    rank1_acc = sum(1 for r in results if r.rank_1_exact)
    top5_acc = sum(1 for r in results if r.top_5_exact)
    name_acc = sum(1 for r in results if r.name_matched)
    numer_acc = sum(1 for r in results if r.numerator_matched)
    full_num_acc = sum(1 for r in results if r.full_number_matched)
    false_high = sum(1 for r in results if r.is_false_high_confidence)
    no_res = sum(1 for r in results if r.no_result)
    neg_failures = sum(1 for r in results if not r.negative_assertion_passed)

    latencies = sorted(r.latency_ms for r in results)
    avg_lat = sum(latencies) / count
    p50 = latencies[count // 2]
    p95 = latencies[min(int(count * 0.95), count - 1)]

    p_r1 = rank1_acc / count * 100
    p_t5 = top5_acc / count * 100
    p_nm = name_acc / count * 100
    p_nu = numer_acc / count * 100
    p_fn = full_num_acc / count * 100
    p_fh = false_high / count * 100
    p_nr = no_res / count * 100
    print(f"  Exact Card Printing @ Rank 1:  {rank1_acc}/{count} ({p_r1:.1f}%)")
    print(f"  Exact Card Printing in Top 5:  {top5_acc}/{count} ({p_t5:.1f}%)")
    print(f"  Name Extraction Accuracy:      {name_acc}/{count} ({p_nm:.1f}%)")
    print(f"  Numerator (Local ID) Accuracy: {numer_acc}/{count} ({p_nu:.1f}%)")
    print(f"  Full Number Accuracy:          {full_num_acc}/{count} ({p_fn:.1f}%)")
    print(f"  False High-Confidence Rate:    {false_high}/{count} ({p_fh:.1f}%)")
    print(f"  Abstention / No-Result Rate:   {no_res}/{count} ({p_nr:.1f}%)")
    print(f"  Negative Assertions Failed:    {neg_failures}/{count}")
    print(
        f"  Latency (Mean / p50 / p95):    {avg_lat:.0f}ms / {p50:.0f}ms / {p95:.0f}ms"
    )

    # Item details
    print("\n  Per-Item Results:")
    for r in results:
        status_flag = (
            "PASS" if r.rank_1_exact else ("TOP5" if r.top_5_exact else "FAIL")
        )
        exp_str = f"{r.expected_card_id} '{r.expected_name}' #{r.expected_number}"
        got_str = f"{r.rank_1_card_id} '{r.rank_1_card_name}' ({r.rank_1_score:.0f})"
        ocr_str = f"'{r.ocr_name}' #{r.ocr_number}"
        print(
            f"    [{status_flag}] {r.item_id:20} | Exp: {exp_str}\n"
            f"         Got: {got_str} [{r.confidence_state}] | OCR: {ocr_str} | "
            f"{r.latency_ms:.0f}ms"
        )

    # Failures list
    failures = [r for r in results if not r.rank_1_exact]
    if failures:
        print("\n  Failures & Discrepancies (Exact Printing @ Rank 1):")
        for f in failures:
            print(
                f"    - Item {f.item_id}: Expected {f.expected_card_id} "
                f"({f.expected_name} #{f.expected_number}), Got Rank 1: "
                f"{f.rank_1_card_id} ({f.rank_1_card_name}), "
                f"OCR: '{f.ocr_name}' #{f.ocr_number}"
            )


def print_cropping_summary(crop_results: list[CroppingEvalResult]) -> None:
    count = len(crop_results)
    print("\n===============================================================")
    print(f"CATEGORY: Cropping Quality (Uncropped Photos) (n={count})")
    print("===============================================================")

    if count == 0:
        print("  No uncropped photos evaluated.")
        return

    det_found = sum(1 for c in crop_results if c.detection_found)
    corners_ok = sum(1 for c in crop_results if c.corners_enclosing)
    title_ok = sum(1 for c in crop_results if c.title_preserved)
    footer_ok = sum(1 for c in crop_results if c.footer_preserved)
    r1_matched = sum(1 for c in crop_results if c.rank_1_matched)

    p_det = det_found / count * 100
    p_cor = corners_ok / count * 100
    p_tit = title_ok / count * 100
    p_foo = footer_ok / count * 100
    p_r1m = r1_matched / count * 100
    print(f"  Card Detection Success:        {det_found}/{count} ({p_det:.1f}%)")
    print(f"  Corners Enclose Whole Card:    {corners_ok}/{count} ({p_cor:.1f}%)")
    print(f"  Header/Title Preserved:        {title_ok}/{count} ({p_tit:.1f}%)")
    print(f"  Footer/Collector No Preserved: {footer_ok}/{count} ({p_foo:.1f}%)")
    print(f"  Crop End-to-End Exact Rank 1:  {r1_matched}/{count} ({p_r1m:.1f}%)")

    for c in crop_results:
        print(f"    - {c.item_id}: {c.details} ({c.latency_ms:.0f}ms)")


def print_coverage_gaps(held_out_items: list[dict[str, Any]]) -> None:
    print("\n===============================================================")
    print("HELD-OUT EVALUATION SET & COVERAGE GAPS")
    print("===============================================================")
    print("  Policy: Never report clean catalog images as real photos.")
    print("  Policy: Report missing representative scenarios; do not invent results.\n")

    missing = [item for item in held_out_items if not item.get("has_fixture")]
    available = [item for item in held_out_items if item.get("has_fixture")]

    print(f"  Evaluated Samples in Held-Out Set: {len(available)}")
    print(
        f"  Identified Coverage Gaps ({len(missing)} missing representative scenarios):"
    )
    for gap in missing:
        gcat = gap.get("gap_category")
        gid = gap.get("id")
        gdesc = gap.get("gap_description")
        print(f"    - [{gcat}] {gid}: {gdesc}")


async def run_evaluation() -> None:
    print("===============================================================")
    print("PHASE 5: RECOGNITION QUALITY BENCHMARK & EVALUATION REPORT")
    print("===============================================================")

    manifest = load_manifest()
    categories = manifest["categories"]

    real_photo_cfg = categories["real_photographs"]
    dev_set_items = real_photo_cfg["dev_set"]
    held_out_items = real_photo_cfg["held_out_evaluation_set"]

    catalog_cfg = categories["clean_catalog_scans"]
    catalog_items = catalog_cfg["items"]

    # Prepare fixtures
    print("\n1. Preparing clean catalog scans (never described as real photographs)...")
    clean_paths = prepare_clean_catalog_fixtures(catalog_items)
    print(f"   Available clean catalog assets: {len(clean_paths)}/{len(catalog_items)}")

    print("\n2. Generating synthetic distortion fixtures (rotation, noise, blur)...")
    synthetic_paths = prepare_synthetic_distortions(catalog_items, clean_paths)
    print(
        f"   Generated synthetic distortions: "
        f"{len(synthetic_paths)}/{len(catalog_items)}"
    )

    engine = get_ocr_engine()

    real_results: list[ItemEvalResult] = []
    crop_results: list[CroppingEvalResult] = []
    catalog_results: list[ItemEvalResult] = []
    synthetic_results: list[ItemEvalResult] = []

    async with TcgdexClient() as client:
        # 1. Real Photographs (Dev Set)
        print("\n--- Evaluating: Real Photographs (Dev Set) ---")
        for item in dev_set_items:
            rel_path = item["file"]
            full_path = FIXTURES_DIR / rel_path
            if not full_path.is_file():
                print(f"  Warning: missing fixture {rel_path}")
                continue

            # If uncropped photo, evaluate cropping quality
            if item.get("is_uncropped"):
                crop_res = await evaluate_cropping_quality(client, engine, item)
                crop_results.append(crop_res)
            else:
                res = await evaluate_single_image(
                    client=client,
                    engine=engine,
                    img_path=full_path,
                    item_id=item["id"],
                    category="Real Photographs (Dev Set)",
                    expected_card_id=item["card_id"],
                    expected_name=item["expected_name"],
                    expected_number=item["expected_number"],
                    expected_local_id=item["expected_local_id"],
                    negative_assertions=item.get("negative_assertions"),
                )
                real_results.append(res)
                print(
                    f"  Processed {item['id']}: "
                    f"rank1={res.rank_1_exact} ({res.latency_ms:.0f}ms)"
                )

        # 2. Clean Catalog Scans
        print("\n--- Evaluating: Clean Catalog Scans (Digital Reference) ---")
        for item in catalog_items:
            cid = item["id"]
            if cid not in clean_paths:
                continue
            res = await evaluate_single_image(
                client=client,
                engine=engine,
                img_path=clean_paths[cid],
                item_id=cid,
                category="Clean Catalog Scans",
                expected_card_id=cid,
                expected_name=item["expected_name"],
                expected_number=item["expected_number"],
                expected_local_id=item["expected_local_id"],
            )
            catalog_results.append(res)
            print(
                f"  Processed {cid}: rank1={res.rank_1_exact} ({res.latency_ms:.0f}ms)"
            )

        # 3. Synthetic Distortions
        print("\n--- Evaluating: Synthetic Distortions ---")
        for item in catalog_items:
            cid = item["id"]
            if cid not in synthetic_paths:
                continue
            res = await evaluate_single_image(
                client=client,
                engine=engine,
                img_path=synthetic_paths[cid],
                item_id=f"{cid}_synthetic",
                category="Synthetic Distortions",
                expected_card_id=cid,
                expected_name=item["expected_name"],
                expected_number=item["expected_number"],
                expected_local_id=item["expected_local_id"],
            )
            synthetic_results.append(res)
            print(
                f"  Processed {cid}_synthetic: "
                f"rank1={res.rank_1_exact} ({res.latency_ms:.0f}ms)"
            )

    # Print Full Structured Reports
    print_category_summary(
        "Real Photographs (Dev Set)",
        real_results,
        note="Real camera photographs under varied crop resolutions and lighting.",
    )

    print_cropping_summary(crop_results)

    print_category_summary(
        "Clean Catalog Scans",
        catalog_results,
        note=(
            "Clean digital card images from catalog provider. "
            "Never labeled real photos."
        ),
    )

    print_category_summary(
        "Synthetic Distortions (Rotated 3deg, Gaussian Noise, Blur)",
        synthetic_results,
        note="Clean catalog scans with affine rotation, sensor noise, and defocus.",
    )

    print_coverage_gaps(held_out_items)

    print("\n===============================================================")
    print("EVALUATION BENCHMARK RUN COMPLETED")
    print("===============================================================\n")


def test_manifest_schema_and_fixtures_exist() -> None:
    """Validate eval_manifest.json schema and fixture existence."""
    manifest = load_manifest()
    assert manifest["manifest_version"] == "1.0.0"
    categories = manifest["categories"]
    assert "real_photographs" in categories
    assert "clean_catalog_scans" in categories
    assert "synthetic_distortions" in categories

    dev_set = categories["real_photographs"]["dev_set"]
    assert len(dev_set) >= 4
    for item in dev_set:
        file_path = FIXTURES_DIR / item["file"]
        assert file_path.is_file(), f"Real photograph fixture missing: {file_path}"
        assert item.get("card_id"), f"Item {item['id']} missing card_id"

    # Verify steelix negative assertion
    steelix_item = next(i for i in dev_set if "steelix" in i["id"])
    assert steelix_item["card_id"] == "swsh8-139"
    assert "ex7-10" in steelix_item.get("negative_assertions", [])

    # Verify held-out coverage gaps
    held_out = categories["real_photographs"]["held_out_evaluation_set"]
    assert len(held_out) >= 4
    assert any(g.get("gap_category") == "reflective_glare" for g in held_out)
    assert any(g.get("gap_category") == "non_card" for g in held_out)


if __name__ == "__main__":
    asyncio.run(run_evaluation())
