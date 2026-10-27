import math
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.commands.cleanup_scans import cleanup_expired_scans, cleanup_orphan_files
from app.core.config import settings
from app.models.scan import Scan
from app.schemas.scan import CropCorners, Point
from app.services.card_detector import (
    POKEMON_CARD_ASPECT_RATIO,
    InvalidCornersError,
    detect_card_corners,
    get_default_corners,
    order_corners,
    validate_corners,
)
from app.services.crop_service import (
    CropProcessingError,
    perform_crop_and_warp,
)


def _create_synthetic_card_image(
    canvas_size: tuple[int, int] = (800, 600),
    card_center: tuple[int, int] = (400, 300),
    card_size: tuple[int, int] = (252, 352),
    angle: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw a synthetic Pokémon card on a dark surface and return corners."""
    # Background: dark wood/mat color
    img = np.full((canvas_size[1], canvas_size[0], 3), (40, 45, 50), dtype=np.uint8)

    w, h = card_size
    cx, cy = card_center

    # Box corners centered around origin
    box = np.array(
        [
            [-w / 2, -h / 2],
            [w / 2, -h / 2],
            [w / 2, h / 2],
            [-w / 2, h / 2],
        ],
        dtype=np.float32,
    )

    # Rotation matrix
    rad = math.radians(angle)
    rot_mat = np.array(
        [
            [math.cos(rad), -math.sin(rad)],
            [math.sin(rad), math.cos(rad)],
        ],
        dtype=np.float32,
    )

    rotated_box = np.dot(box, rot_mat.T) + np.array([cx, cy], dtype=np.float32)

    # Draw card border (yellow Pokémon card border)
    pts_int = rotated_box.astype(np.int32)
    cv2.fillPoly(img, [pts_int], (20, 200, 240))  # BGR yellow

    # Draw card inner artwork / text area (lighter center)
    inner_box = box * 0.88
    rotated_inner = np.dot(inner_box, rot_mat.T) + np.array([cx, cy], dtype=np.float32)
    cv2.fillPoly(img, [rotated_inner.astype(np.int32)], (180, 160, 220))

    return img, rotated_box


def _save_image_to_path(img_bgr: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img_bgr)


# ---------------------------------------------------------------------------
# Unit tests: Geometric validation
# ---------------------------------------------------------------------------


def test_validate_corners_valid() -> None:
    corners = CropCorners(
        top_left=Point(x=0.1, y=0.1),
        top_right=Point(x=0.9, y=0.1),
        bottom_right=Point(x=0.9, y=0.9),
        bottom_left=Point(x=0.1, y=0.9),
    )
    validate_corners(corners)


def test_validate_corners_out_of_bounds() -> None:
    with pytest.raises(ValidationError):
        # Pydantic validates ge=0.0, le=1.0
        CropCorners(
            top_left=Point(x=-0.1, y=0.1),
            top_right=Point(x=0.9, y=0.1),
            bottom_right=Point(x=0.9, y=0.9),
            bottom_left=Point(x=0.1, y=0.9),
        )


def test_validate_corners_duplicate_points() -> None:
    corners = CropCorners(
        top_left=Point(x=0.2, y=0.2),
        top_right=Point(x=0.2001, y=0.2001),  # almost identical
        bottom_right=Point(x=0.8, y=0.8),
        bottom_left=Point(x=0.2, y=0.8),
    )
    with pytest.raises(InvalidCornersError, match="too close"):
        validate_corners(corners)


def test_validate_corners_crossing_edges_bow_tie() -> None:
    # Crossed edges create an invalid non-convex / intersecting quad
    corners = CropCorners(
        top_left=Point(x=0.1, y=0.1),
        top_right=Point(x=0.9, y=0.9),  # crossed
        bottom_right=Point(x=0.9, y=0.1),  # crossed
        bottom_left=Point(x=0.1, y=0.9),
    )
    with pytest.raises(InvalidCornersError, match="intersect|strictly convex"):
        validate_corners(corners)


def test_validate_corners_concave_quad() -> None:
    # One vertex indented inward
    corners = CropCorners(
        top_left=Point(x=0.1, y=0.1),
        top_right=Point(x=0.9, y=0.1),
        bottom_right=Point(x=0.4, y=0.3),  # indented reflex point
        bottom_left=Point(x=0.1, y=0.9),
    )
    with pytest.raises(InvalidCornersError, match="strictly convex"):
        validate_corners(corners)


def test_validate_corners_area_too_small() -> None:
    corners = CropCorners(
        top_left=Point(x=0.1, y=0.1),
        top_right=Point(x=0.12, y=0.1),
        bottom_right=Point(x=0.12, y=0.12),
        bottom_left=Point(x=0.1, y=0.12),
    )
    with pytest.raises(InvalidCornersError, match="too small"):
        validate_corners(corners, min_area=0.01)


def test_order_corners_arbitrary_rotations() -> None:
    # Points in random order
    pts = np.array(
        [
            [100, 500],  # BL
            [400, 100],  # TR
            [100, 100],  # TL
            [400, 500],  # BR
        ],
        dtype=np.float32,
    )

    ordered = order_corners(pts)
    assert np.allclose(ordered[0], [100, 100])  # TL
    assert np.allclose(ordered[1], [400, 100])  # TR
    assert np.allclose(ordered[2], [400, 500])  # BR
    assert np.allclose(ordered[3], [100, 500])  # BL


# ---------------------------------------------------------------------------
# Unit tests: Card detection on synthetic images
# ---------------------------------------------------------------------------


def test_detect_card_on_clean_synthetic_image(tmp_path: Path) -> None:
    img, _ = _create_synthetic_card_image(
        canvas_size=(800, 600),
        card_center=(400, 300),
        card_size=(252, 352),
        angle=0.0,
    )
    test_path = tmp_path / "card_clean.jpg"
    _save_image_to_path(img, test_path)

    detected, corners, msg, score = detect_card_corners(test_path)
    assert detected is True
    assert score > 0.5
    assert "gedetecteerd" in msg.lower()

    # Center of card is around x: 0.34 to 0.65, y: 0.20 to 0.79
    assert 0.30 <= corners.top_left.x <= 0.40
    assert 0.15 <= corners.top_left.y <= 0.25
    assert 0.60 <= corners.bottom_right.x <= 0.70
    assert 0.70 <= corners.bottom_right.y <= 0.85


def test_detect_card_on_rotated_synthetic_image(tmp_path: Path) -> None:
    img, _ = _create_synthetic_card_image(
        canvas_size=(800, 800),
        card_center=(400, 400),
        card_size=(252, 352),
        angle=25.0,  # rotated 25 degrees
    )
    test_path = tmp_path / "card_rotated.jpg"
    _save_image_to_path(img, test_path)

    detected, corners, msg, score = detect_card_corners(test_path)
    assert detected is True
    assert score > 0.5
    validate_corners(corners)


def test_detect_card_no_card_found(tmp_path: Path) -> None:
    # Uniform noise / plain background with no card
    img = np.random.randint(100, 120, (600, 800, 3), dtype=np.uint8)
    test_path = tmp_path / "noise.jpg"
    _save_image_to_path(img, test_path)

    detected, corners, msg, score = detect_card_corners(test_path)
    assert detected is False
    assert score <= 0.5
    assert "geen" in msg.lower()

    # Verify fallback corners are sensible inset rectangle
    default_c = get_default_corners()
    assert corners.top_left.x == pytest.approx(default_c.top_left.x)
    assert corners.bottom_right.y == pytest.approx(default_c.bottom_right.y)


def test_detect_card_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "does_not_exist.jpg"
    detected, corners, msg, score = detect_card_corners(missing_path)
    assert detected is False
    assert score == 0.0


def _create_synthetic_silver_card(
    canvas_size: tuple[int, int] = (800, 600),
    card_center: tuple[int, int] = (400, 300),
    card_size: tuple[int, int] = (252, 352),
    bg_color: tuple[int, int, int] = (40, 70, 110),
    angle: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw a synthetic modern Scarlet & Violet card with silver/gray border."""
    img = np.full((canvas_size[1], canvas_size[0], 3), bg_color, dtype=np.uint8)
    w, h = card_size
    cx, cy = card_center
    box = np.array(
        [
            [-w / 2, -h / 2],
            [w / 2, -h / 2],
            [w / 2, h / 2],
            [-w / 2, h / 2],
        ],
        dtype=np.float32,
    )
    rad = math.radians(angle)
    rot_mat = np.array(
        [
            [math.cos(rad), -math.sin(rad)],
            [math.sin(rad), math.cos(rad)],
        ],
        dtype=np.float32,
    )
    rotated_box = np.dot(box, rot_mat.T) + np.array([cx, cy], dtype=np.float32)

    # Silver/gray card border (BGR ~200, 200, 200)
    cv2.fillPoly(img, [rotated_box.astype(np.int32)], (200, 200, 200))

    # Inner artwork & text areas
    inner_box = box * 0.88
    rotated_inner = np.dot(inner_box, rot_mat.T) + np.array([cx, cy], dtype=np.float32)
    cv2.fillPoly(img, [rotated_inner.astype(np.int32)], (60, 80, 150))
    return img, rotated_box


def _create_synthetic_fullart_closeup(
    canvas_size: tuple[int, int] = (600, 800),
    card_fill_ratio: float = 0.92,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw a synthetic full-art card occupying 80-95% of the frame with
    internal elements.
    """
    w_img, h_img = canvas_size
    img = np.full((h_img, w_img, 3), (220, 220, 220), dtype=np.uint8)
    w = int(w_img * card_fill_ratio)
    h = int(w / POKEMON_CARD_ASPECT_RATIO)
    if h > int(h_img * card_fill_ratio):
        h = int(h_img * card_fill_ratio)
        w = int(h * POKEMON_CARD_ASPECT_RATIO)
    cx, cy = w_img // 2, h_img // 2
    box = np.array(
        [
            [-w / 2, -h / 2],
            [w / 2, -h / 2],
            [w / 2, h / 2],
            [-w / 2, h / 2],
        ],
        dtype=np.float32,
    ) + [cx, cy]

    # Full art outer boundary with colorful artwork
    cv2.fillPoly(img, [box.astype(np.int32)], (50, 70, 140))

    # Upper illustration window (aspect ~0.72)
    art_box = np.array(
        [
            [-w * 0.38, -h * 0.42],
            [w * 0.38, -h * 0.42],
            [w * 0.38, -h * 0.05],
            [-w * 0.38, -h * 0.05],
        ],
        dtype=np.float32,
    ) + [cx, cy]
    cv2.fillPoly(img, [art_box.astype(np.int32)], (90, 170, 210))

    # Lower text / attack block
    text_box = np.array(
        [
            [-w * 0.38, h * 0.02],
            [w * 0.38, h * 0.02],
            [w * 0.38, h * 0.40],
            [-w * 0.38, h * 0.40],
        ],
        dtype=np.float32,
    ) + [cx, cy]
    cv2.fillPoly(img, [text_box.astype(np.int32)], (210, 215, 225))
    return img, box


def test_detect_card_silver_border_on_varied_backgrounds(tmp_path: Path) -> None:
    # Test Scarlet & Violet silver/gray border on 3 distinct surfaces:
    # 1. Dark playmat (30, 30, 30)
    # 2. Light desk (240, 240, 240)
    # 3. Wooden table (40, 70, 110)
    backgrounds = [
        ("dark_mat", (30, 30, 30)),
        ("light_desk", (240, 240, 240)),
        ("wood_table", (40, 70, 110)),
    ]
    for name, bg_color in backgrounds:
        img, _ = _create_synthetic_silver_card(
            canvas_size=(800, 600),
            bg_color=bg_color,
        )
        p = tmp_path / f"silver_{name}.jpg"
        _save_image_to_path(img, p)

        detected, corners, msg, score = detect_card_corners(p)
        assert detected is True, f"Failed detection on {name}"
        assert score > 0.50
        validate_corners(corners)
        # Card is centered around x: 0.34 to 0.66, y: 0.20 to 0.80
        assert 0.30 <= corners.top_left.x <= 0.38
        assert 0.15 <= corners.top_left.y <= 0.25
        assert 0.62 <= corners.bottom_right.x <= 0.70
        assert 0.75 <= corners.bottom_right.y <= 0.85


def test_detect_card_fullart_closeup_selects_outer_card(tmp_path: Path) -> None:
    # Full-art card occupying >85% of frame with internal illustration & rule boxes
    img, _ = _create_synthetic_fullart_closeup(
        canvas_size=(600, 800), card_fill_ratio=0.92
    )
    p = tmp_path / "fullart_closeup.jpg"
    _save_image_to_path(img, p)

    detected, corners, msg, score = detect_card_corners(p)
    assert detected is True
    assert score > 0.80
    validate_corners(corners)

    # Must select outer card (near edges), NOT the internal illustration window!
    assert corners.top_left.x < 0.12
    assert corners.top_left.y < 0.12
    assert corners.bottom_right.x > 0.88
    assert corners.bottom_right.y > 0.88  # Illustration window would be < 0.55!


def test_detect_card_containment_prefers_outer_over_nested_boxes(
    tmp_path: Path,
) -> None:
    # Synthetic card with an prominent internal illustration rectangle (aspect ~0.72)
    # The detector must evaluate containment and pick the outer card contour.
    img, _ = _create_synthetic_card_image(
        canvas_size=(800, 600),
        card_center=(400, 300),
        card_size=(252, 352),
    )
    p = tmp_path / "card_with_illustration.jpg"
    _save_image_to_path(img, p)

    detected, corners, msg, score = detect_card_corners(p)
    assert detected is True
    assert score > 0.70

    # Ensure full card is selected and not just the upper illustration rectangle
    assert corners.bottom_right.y > 0.75


def test_detect_card_rotated_card_90_180_270(tmp_path: Path) -> None:
    for angle in (90.0, 180.0, 270.0):
        img, _ = _create_synthetic_card_image(
            canvas_size=(800, 800),
            card_center=(400, 400),
            card_size=(252, 352),
            angle=angle,
        )
        p = tmp_path / f"rotated_{int(angle)}.jpg"
        _save_image_to_path(img, p)

        detected, corners, msg, score = detect_card_corners(p)
        assert detected is True, f"Failed detection at angle {angle}"
        assert score > 0.50
        validate_corners(corners)


def test_detect_card_uncertainty_fallback_returns_clear_message(
    tmp_path: Path,
) -> None:
    # Low-contrast image with ambiguous non-card shapes below plausibility threshold
    img = np.full((600, 800, 3), 128, dtype=np.uint8)
    # Draw faint non-card blob
    cv2.circle(img, (400, 300), 50, (132, 130, 127), -1)
    p = tmp_path / "ambiguous.jpg"
    _save_image_to_path(img, p)

    detected, corners, msg, score = detect_card_corners(p)
    assert detected is False
    assert score < 0.50
    # Clear user message explaining why detection was uncertain
    assert any(
        term in msg.lower() for term in ("geen", "onzeker", "contrast", "handmatig")
    )

    # Sensible fallback inset rectangle
    default_c = get_default_corners()
    assert corners.top_left.x == pytest.approx(default_c.top_left.x)
    assert corners.bottom_right.y == pytest.approx(default_c.bottom_right.y)


def test_regression_fixtures_detection() -> None:
    fixtures_dir = Path(__file__).parent / "fixtures" / "regression_scans"
    if not fixtures_dir.is_dir():
        pytest.skip("Regression scans fixtures directory not found")

    # 1. charizard-original.jpg: close-up filling ~88% of frame
    p_charizard_orig = fixtures_dir / "charizard-original.jpg"
    if p_charizard_orig.is_file():
        det, c, msg, sc = detect_card_corners(p_charizard_orig)
        assert det is True
        assert sc > 0.85
        assert c.top_left.x < 0.10
        assert c.top_right.x > 0.90
        assert c.bottom_left.y > 0.94
        assert c.bottom_right.y > 0.94

    # 2. steelix.jpg: close-up scan where card fills image
    p_steelix = fixtures_dir / "steelix.jpg"
    if p_steelix.is_file():
        det, c, msg, sc = detect_card_corners(p_steelix)
        assert det is True
        assert sc > 0.80
        # Bottom of detected card must encompass entire card (y > 0.90)
        assert c.bottom_right.y > 0.90
        assert c.bottom_left.y > 0.90

    # 3. gastly.jpg and pikachu.jpg
    for fname in ("gastly.jpg", "pikachu.jpg"):
        pf = fixtures_dir / fname
        if pf.is_file():
            det, c, _, sc = detect_card_corners(pf)
            assert det is True
            assert sc > 0.80
            assert c.bottom_right.y > 0.90


# ---------------------------------------------------------------------------
# Unit tests: Crop and perspective transformation
# ---------------------------------------------------------------------------


def test_perform_crop_and_warp_success(tmp_path: Path) -> None:
    img, _ = _create_synthetic_card_image(
        canvas_size=(800, 600),
        card_center=(400, 300),
        card_size=(252, 352),
        angle=0.0,
    )
    source_path = tmp_path / "source.jpg"
    _save_image_to_path(img, source_path)

    target_path = tmp_path / "target_crop.jpg"
    corners = CropCorners(
        top_left=Point(x=0.34, y=0.20),
        top_right=Point(x=0.66, y=0.20),
        bottom_right=Point(x=0.66, y=0.80),
        bottom_left=Point(x=0.34, y=0.80),
    )

    w, h, size = perform_crop_and_warp(
        source_path=source_path,
        target_path=target_path,
        corners=corners,
        rotation=0,
    )

    assert target_path.is_file()
    assert w > 0 and h > 0
    assert size == target_path.stat().st_size

    # Source must remain completely unmodified
    assert source_path.is_file()

    # Check resulting aspect ratio is close to standard Pokémon card
    ratio = min(w, h) / max(w, h)
    assert abs(ratio - POKEMON_CARD_ASPECT_RATIO) < 0.05


def test_perform_crop_and_warp_with_rotations(tmp_path: Path) -> None:
    img, _ = _create_synthetic_card_image()
    source_path = tmp_path / "source.jpg"
    _save_image_to_path(img, source_path)

    corners = CropCorners(
        top_left=Point(x=0.34, y=0.20),
        top_right=Point(x=0.66, y=0.20),
        bottom_right=Point(x=0.66, y=0.80),
        bottom_left=Point(x=0.34, y=0.80),
    )

    # 0 degrees: portrait (h > w)
    w0, h0, _ = perform_crop_and_warp(
        source_path, tmp_path / "c0.jpg", corners, rotation=0
    )
    assert h0 > w0

    # 90 degrees: rotated landscape (w > h)
    w90, h90, _ = perform_crop_and_warp(
        source_path, tmp_path / "c90.jpg", corners, rotation=90
    )
    assert w90 > h90
    assert w90 == h0
    assert h90 == w0

    # 180 degrees: inverted portrait (h > w)
    w180, h180, _ = perform_crop_and_warp(
        source_path, tmp_path / "c180.jpg", corners, rotation=180
    )
    assert h180 == h0
    assert w180 == w0

    # 270 degrees: rotated landscape (w > h)
    w270, h270, _ = perform_crop_and_warp(
        source_path, tmp_path / "c270.jpg", corners, rotation=270
    )
    assert w270 == h0
    assert h270 == w0


def test_perform_crop_preserves_maximal_resolution_and_clarity(tmp_path: Path) -> None:
    # High-resolution image (e.g. 1500 x 2100)
    w_src, h_src = 1500, 2100
    img = np.full((h_src, w_src, 3), (230, 230, 230), dtype=np.uint8)

    # Draw simulated high-frequency footer text (alternating black/white lines)
    # in the bottom 50 pixels of the card
    cx, cy = w_src // 2, h_src // 2
    cw, ch = 900, 1260
    card_box = np.array(
        [
            [cx - cw // 2, cy - ch // 2],
            [cx + cw // 2, cy - ch // 2],
            [cx + cw // 2, cy + ch // 2],
            [cx - cw // 2, cy + ch // 2],
        ],
        dtype=np.float32,
    )
    cv2.fillPoly(img, [card_box.astype(np.int32)], (20, 200, 240))

    # Add fine collector footer details
    for line_y in range(cy + ch // 2 - 40, cy + ch // 2 - 10, 4):
        cv2.line(img, (cx - 200, line_y), (cx + 200, line_y), (10, 10, 10), 1)

    source_path = tmp_path / "high_res_source.jpg"
    _save_image_to_path(img, source_path)

    corners = CropCorners(
        top_left=Point(x=(cx - cw // 2) / w_src, y=(cy - ch // 2) / h_src),
        top_right=Point(x=(cx + cw // 2) / w_src, y=(cy - ch // 2) / h_src),
        bottom_right=Point(x=(cx + cw // 2) / w_src, y=(cy + ch // 2) / h_src),
        bottom_left=Point(x=(cx - cw // 2) / w_src, y=(cy + ch // 2) / h_src),
    )

    target_path = tmp_path / "high_res_crop.jpg"
    w_out, h_out, size_out = perform_crop_and_warp(
        source_path=source_path,
        target_path=target_path,
        corners=corners,
        rotation=0,
        max_dimension=2500,
    )

    assert target_path.is_file()
    assert size_out > 0

    # Ensure optical resolution is preserved (no downsampling)
    # Measured width was 900, measured height was 1260
    assert h_out >= 1250
    assert w_out >= 895
    aspect = w_out / float(h_out)
    assert abs(aspect - POKEMON_CARD_ASPECT_RATIO) < 0.01

    # Verify output image is readable and sharp
    out_bgr = cv2.imread(str(target_path))
    assert out_bgr is not None
    assert out_bgr.shape[0] == h_out
    assert out_bgr.shape[1] == w_out


def test_perform_crop_invalid_rotation(tmp_path: Path) -> None:
    source_path = tmp_path / "source.jpg"
    source_path.write_bytes(b"dummy")
    corners = get_default_corners()

    with pytest.raises(CropProcessingError, match="Invalid rotation"):
        perform_crop_and_warp(source_path, tmp_path / "out.jpg", corners, rotation=45)


def test_perform_crop_preserves_existing_target_on_failure(tmp_path: Path) -> None:
    source_path = tmp_path / "source.jpg"
    source_path.write_bytes(b"invalid image data")

    target_path = tmp_path / "target.jpg"
    target_path.write_bytes(b"previous valid crop")

    corners = get_default_corners()
    with pytest.raises(CropProcessingError):
        perform_crop_and_warp(source_path, target_path, corners, rotation=0)

    # Previous valid file was not touched!
    assert target_path.read_bytes() == b"previous valid crop"


# ---------------------------------------------------------------------------
# API Integration Tests: /detect, /crop, /confirm, /crop/image
# ---------------------------------------------------------------------------


def _setup_scan_in_db(
    db: Session,
    tmp_path: Path,
    image_bgr: np.ndarray,
    expired: bool = False,
) -> tuple[Scan, Path]:
    scan_id = "11111111-2222-3333-4444-555555555555"
    storage_dir = tmp_path / "uploads"
    storage_dir.mkdir(parents=True, exist_ok=True)
    img_path = storage_dir / f"{scan_id}.jpg"
    _save_image_to_path(image_bgr, img_path)

    now = datetime.now(UTC).replace(tzinfo=None)
    expires = now - timedelta(hours=1) if expired else now + timedelta(hours=24)

    h, w = image_bgr.shape[:2]
    scan = Scan(
        id=scan_id,
        status="uploaded",
        image_path=f"{scan_id}.jpg",
        content_type="image/jpeg",
        width=w,
        height=h,
        file_size=img_path.stat().st_size,
        created_at=now,
        expires_at=expires,
        crop_status="none",
        crop_version=0,
    )
    db.add(scan)
    db.commit()
    return scan, img_path


def test_api_detect_success(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(db, tmp_path, img)

    resp = client.post(f"/api/v1/scans/{scan.id}/detect")
    assert resp.status_code == 200
    data = resp.json()

    assert data["detected"] is True
    assert "corners" in data
    assert data["score"] > 0.5
    assert resp.headers["Cache-Control"] == "no-store"

    # Verify database scan state was updated to 'detected'
    db.refresh(scan)
    assert scan.crop_status == "detected"
    assert scan.corners is not None


def test_api_detect_expired_scan(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    img, _ = _create_synthetic_card_image()
    scan, _ = _setup_scan_in_db(db, tmp_path, img, expired=True)

    resp = client.post(f"/api/v1/scans/{scan.id}/detect")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "SCAN_EXPIRED"


def test_api_crop_and_preview(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(db, tmp_path, img)

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    crop_resp = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 90, "expected_version": 0},
    )
    assert crop_resp.status_code == 200
    crop_data = crop_resp.json()

    assert crop_data["crop_status"] == "preview"
    assert crop_data["rotation"] == 90
    assert crop_data["crop_version"] == 1
    assert (
        crop_data["crop_image_url"]
        == f"/api/v1/scans/{scan.id}/crop/image?v={crop_data['crop_version']}"
    )
    assert crop_data["crop_width"] > 0
    assert crop_data["crop_height"] > 0
    assert crop_resp.headers["Cache-Control"] == "no-store"

    # Verify image retrieval endpoint
    img_resp = client.get(f"/api/v1/scans/{scan.id}/crop/image")
    assert img_resp.status_code == 200
    assert img_resp.headers["Content-Type"] == "image/jpeg"
    assert img_resp.headers["Cache-Control"] == "no-store"
    assert len(img_resp.content) == crop_data["crop_file_size"]


def test_api_crop_invalid_corners(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    img, _ = _create_synthetic_card_image()
    scan, _ = _setup_scan_in_db(db, tmp_path, img)

    # Identical points (area 0)
    bad_corners = {
        "top_left": {"x": 0.5, "y": 0.5},
        "top_right": {"x": 0.5, "y": 0.5},
        "bottom_right": {"x": 0.5, "y": 0.5},
        "bottom_left": {"x": 0.5, "y": 0.5},
    }

    resp = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": bad_corners, "rotation": 0, "expected_version": 0},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "INVALID_CORNERS"


def test_api_confirm_crop_workflow_and_stale_rejection(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(db, tmp_path, img)

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    # 1. Attempt confirm without preview: rejected
    fail_confirm = client.post(
        f"/api/v1/scans/{scan.id}/confirm",
        json={"crop_version": 1},
    )
    assert fail_confirm.status_code == 400
    assert fail_confirm.json()["detail"]["code"] == "NO_PREVIEW_AVAILABLE"

    # 2. Generate crop preview (version 1)
    crop_resp1 = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    assert crop_resp1.status_code == 200
    assert crop_resp1.json()["crop_version"] == 1

    # 3. Generate second crop preview (version 2)
    crop_resp2 = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 180, "expected_version": 1},
    )
    assert crop_resp2.status_code == 200
    assert crop_resp2.json()["crop_version"] == 2

    # 4. Attempt to confirm stale version 1: rejected with 409
    stale_resp = client.post(
        f"/api/v1/scans/{scan.id}/confirm",
        json={"crop_version": 1},
    )
    assert stale_resp.status_code == 409
    assert stale_resp.json()["detail"]["code"] == "STALE_VERSION"

    # 5. Confirm current version 2: succeeds
    ok_resp = client.post(
        f"/api/v1/scans/{scan.id}/confirm",
        json={"crop_version": 2},
    )
    assert ok_resp.status_code == 200
    data = ok_resp.json()
    assert data["crop_status"] == "confirmed"
    assert data["confirmed_at"] is not None

    # 6. GET scan returns confirmed state
    get_resp = client.get(f"/api/v1/scans/{scan.id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["crop_status"] == "confirmed"


# ---------------------------------------------------------------------------
# Cleanup Tests: Expired crops & Orphan safety
# ---------------------------------------------------------------------------


def test_cleanup_expired_scans_deletes_both_source_and_crop(
    db: Session, tmp_path: Path
) -> None:
    storage_root = tmp_path / "uploads"
    storage_root.mkdir(parents=True, exist_ok=True)

    scan_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    source_file = storage_root / f"{scan_id}.jpg"
    crop_file = storage_root / f"{scan_id}_crop.jpg"
    source_file.write_bytes(b"source jpeg")
    crop_file.write_bytes(b"cropped jpeg")

    now = datetime.now(UTC).replace(tzinfo=None)
    expired_time = now - timedelta(hours=2)

    scan = Scan(
        id=scan_id,
        status="uploaded",
        image_path=f"{scan_id}.jpg",
        content_type="image/jpeg",
        width=100,
        height=100,
        file_size=10,
        created_at=expired_time - timedelta(hours=1),
        expires_at=expired_time,
        crop_status="confirmed",
        crop_path=f"{scan_id}_crop.jpg",
    )
    db.add(scan)
    db.commit()

    deleted_rec, deleted_files, missing_files, failed_files = cleanup_expired_scans(
        db, storage_root=storage_root
    )

    assert deleted_rec == 1
    assert deleted_files == 2  # Both source and crop removed!
    assert not source_file.exists()
    assert not crop_file.exists()
    assert db.query(Scan).filter(Scan.id == scan_id).first() is None


def test_orphan_cleanup_preserves_valid_crops(db: Session, tmp_path: Path) -> None:
    storage_root = tmp_path / "uploads"
    storage_root.mkdir(parents=True, exist_ok=True)

    scan_id = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
    source_file = storage_root / f"{scan_id}.jpg"
    crop_file = storage_root / f"{scan_id}_crop.jpg"
    source_file.write_bytes(b"source jpeg")
    crop_file.write_bytes(b"cropped jpeg")

    # Set mtime to 30 hours ago (beyond 24h grace)
    old_time = datetime.now(UTC).timestamp() - 3600 * 30
    import os

    os.utime(source_file, (old_time, old_time))
    os.utime(crop_file, (old_time, old_time))

    now = datetime.now(UTC).replace(tzinfo=None)
    future = now + timedelta(hours=10)

    scan = Scan(
        id=scan_id,
        status="uploaded",
        image_path=f"{scan_id}.jpg",
        content_type="image/jpeg",
        width=100,
        height=100,
        file_size=10,
        created_at=now,
        expires_at=future,
        crop_status="preview",
        crop_path=f"{scan_id}_crop.jpg",
    )
    db.add(scan)
    db.commit()

    # Create an actual orphan file (old unreferenced crop)
    orphan_file = storage_root / "cccccccc-dddd-eeee-ffff-000000000000_crop.jpg"
    orphan_file.write_bytes(b"orphan crop")
    os.utime(orphan_file, (old_time, old_time))

    removed, failed = cleanup_orphan_files(db, storage_root=storage_root)

    # Orphan file is removed, but active scan's crop and source are kept!
    assert removed == 1
    assert failed == 0
    assert not orphan_file.exists()
    assert source_file.exists()
    assert crop_file.exists()


# ---------------------------------------------------------------------------
# Phase 4 Concurrency & Correctness Regression Tests
# ---------------------------------------------------------------------------


def test_regression_database_failure_preserves_valid_crop(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(db, tmp_path, img)

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    # Step 1: Successful initial crop (version 1)
    crop_resp1 = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    assert crop_resp1.status_code == 200
    scan_v1 = db.query(Scan).filter(Scan.id == scan.id).first()
    assert scan_v1 is not None
    assert scan_v1.crop_version == 1
    initial_crop_filename = scan_v1.crop_path
    assert initial_crop_filename is not None
    initial_crop_file = storage_root / initial_crop_filename
    assert initial_crop_file.exists()
    initial_bytes = initial_crop_file.read_bytes()

    # Step 2: Attempt second crop, but simulate DB commit error
    real_commit = db.commit
    fail_called = False

    def mock_commit(self=None):
        nonlocal fail_called
        fail_called = True
        raise SQLAlchemyError("Simulated database failure during crop commit")

    # Monkeypatch commit on the active session used by get_db
    monkeypatch.setattr(Session, "commit", mock_commit)

    crop_resp2 = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 90, "expected_version": 1},
    )
    assert crop_resp2.status_code == 500
    assert crop_resp2.json()["detail"]["code"] == "DATABASE_ERROR"
    assert fail_called

    # Restore commit
    monkeypatch.setattr(Session, "commit", real_commit)

    # Step 3: Verify the initial crop and metadata were preserved intact
    db.expire_all()
    scan_after = db.query(Scan).filter(Scan.id == scan.id).first()
    assert scan_after is not None
    assert scan_after.crop_version == 1
    assert scan_after.crop_path == initial_crop_filename
    assert scan_after.rotation == 0
    assert initial_crop_file.exists()
    assert initial_crop_file.read_bytes() == initial_bytes

    # Step 4: Verify no orphaned candidate file remains in uploads
    all_files = list(storage_root.iterdir())
    assert len(all_files) == 2
    assert set(all_files) == {storage_root / f"{scan.id}.jpg", initial_crop_file}


def test_sequential_stale_crop_rejection(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(db, tmp_path, img)

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    # First crop request with expected_version=0 succeeds
    resp1 = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    assert resp1.status_code == 200
    assert resp1.json()["crop_version"] == 1

    # Second crop request with stale expected_version=0 is rejected with 409
    resp2 = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 90, "expected_version": 0},
    )
    assert resp2.status_code == 409
    assert resp2.json()["detail"]["code"] == "STALE_VERSION"

    # Winning crop version 1 is unchanged
    db.expire_all()
    scan_db = db.query(Scan).filter(Scan.id == scan.id).first()
    assert scan_db is not None
    assert scan_db.crop_version == 1
    assert scan_db.rotation == 0


def test_sequential_crop_race_simulation(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(db, tmp_path, img)

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    scan_id = str(scan.id)

    # Both requests read initial scan at crop_version = 0
    # Request 1 arrives and successfully applies crop preview (version becomes 1)
    r1 = client.post(
        f"/api/v1/scans/{scan_id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    assert r1.status_code == 200
    assert r1.json()["crop_version"] == 1
    winning_crop_path = r1.json()["crop_image_url"]

    # Request 2 (which was in-flight based on expected_version = 0) arrives later
    r2 = client.post(
        f"/api/v1/scans/{scan_id}/crop",
        json={"corners": corners, "rotation": 90, "expected_version": 0},
    )
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "STALE_VERSION"

    # Winning crop version 1 is unchanged
    db.expire_all()
    scan_db = db.query(Scan).filter(Scan.id == scan_id).first()
    assert scan_db is not None
    assert scan_db.crop_version == 1
    assert scan_db.rotation == 0
    assert (
        f"/api/v1/scans/{scan_id}/crop/image?v={scan_db.crop_version}"
        == winning_crop_path
    )


def test_sequential_crop_cannot_overwrite_confirmed_scan(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(db, tmp_path, img)

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    # 1. Generate preview (version 1)
    crop_resp = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    assert crop_resp.status_code == 200

    # 2. Confirm preview (version 1)
    confirm_resp = client.post(
        f"/api/v1/scans/{scan.id}/confirm",
        json={"crop_version": 1},
    )
    assert confirm_resp.status_code == 200
    confirmed_data = confirm_resp.json()
    assert confirmed_data["crop_status"] == "confirmed"

    # 3. Simulate an in-flight crop request that started while scan was unconfirmed
    stale_crop_resp = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 180, "expected_version": 1},
    )
    # Must be rejected with 409 and not overwrite confirmed state
    assert stale_crop_resp.status_code == 409
    assert stale_crop_resp.json()["detail"]["code"] in (
        "CONFIRMED_CONFLICT",
        "STALE_VERSION",
    )

    # 4. Verify scan is still confirmed
    db.expire_all()
    scan_db = db.query(Scan).filter(Scan.id == scan.id).first()
    assert scan_db is not None
    assert scan_db.crop_status == "confirmed"
    assert scan_db.confirmed_at is not None


def test_regression_missing_crop_image_cannot_be_confirmed(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(db, tmp_path, img)

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    # Generate preview (version 1)
    crop_resp = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    assert crop_resp.status_code == 200
    scan_v1 = db.query(Scan).filter(Scan.id == scan.id).first()
    assert scan_v1 is not None
    assert scan_v1.crop_version == 1
    assert scan_v1.crop_status == "preview"
    assert scan_v1.confirmed_at is None
    crop_file = storage_root / scan_v1.crop_path
    assert crop_file.exists()

    # Intentionally remove the crop file from disk
    crop_file.unlink()
    assert not crop_file.exists()

    # Attempt confirmation: must fail with 404 CROP_NOT_FOUND
    confirm_resp = client.post(
        f"/api/v1/scans/{scan.id}/confirm",
        json={"crop_version": 1},
    )
    assert confirm_resp.status_code == 404
    assert confirm_resp.json()["detail"]["code"] == "CROP_NOT_FOUND"

    # Crucial check: verify database state is COMPLETELY UNCHANGED
    db.expire_all()
    scan_after = db.query(Scan).filter(Scan.id == scan.id).first()
    assert scan_after is not None
    assert scan_after.crop_status == "preview"
    assert scan_after.crop_version == 1
    assert scan_after.confirmed_at is None


def test_regression_concurrent_replacement_cannot_confirm_wrong_crop(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(db, tmp_path, img)

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    # 1. Preview 1 created (crop_version 1)
    r1 = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    assert r1.status_code == 200

    # 2. Preview 2 replaces Preview 1 (crop_version 2, new unique crop_path)
    r2 = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 90, "expected_version": 1},
    )
    assert r2.status_code == 200

    # 3. Stale confirmation for Preview 1 (crop_version 1) must be rejected with 409
    confirm_stale = client.post(
        f"/api/v1/scans/{scan.id}/confirm",
        json={"crop_version": 1},
    )
    assert confirm_stale.status_code == 409
    assert confirm_stale.json()["detail"]["code"] == "STALE_VERSION"

    # 4. Preview 2 remains active preview, unconfirmed
    db.expire_all()
    scan_after = db.query(Scan).filter(Scan.id == scan.id).first()
    assert scan_after is not None
    assert scan_after.crop_version == 2
    assert scan_after.crop_status == "preview"
    assert scan_after.confirmed_at is None


def test_regression_expected_version_required_and_validated(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(db, tmp_path, img)

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    # 1. Missing expected_version -> 422
    resp_missing = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0},
    )
    assert resp_missing.status_code == 422

    # 2. Null expected_version -> 422
    resp_null = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": None},
    )
    assert resp_null.status_code == 422

    # 3. Negative expected_version -> 422
    resp_neg = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": -1},
    )
    assert resp_neg.status_code == 422

    # 4. Invalid string expected_version -> 422
    resp_str = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": "invalid"},
    )
    assert resp_str.status_code == 422

    # 5. Stale expected_version (e.g. 99) -> 409 STALE_VERSION without modifying state
    resp_stale = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 99},
    )
    assert resp_stale.status_code == 409
    assert resp_stale.json()["detail"]["code"] == "STALE_VERSION"
    db.expire_all()
    scan_after = db.query(Scan).filter(Scan.id == scan.id).first()
    assert scan_after is not None
    assert scan_after.crop_version == 0
    assert scan_after.crop_status == "none"

    # 6. Valid current expected_version (0) -> 200 OK
    resp_ok = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["crop_version"] == 1
    assert resp_ok.json()["crop_status"] == "preview"


def test_regression_scan_expiration_during_processing(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(db, tmp_path, img)

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    # Manually expire the scan in DB while processing
    scan.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    db.commit()

    # Attempt to crop expired scan
    crop_resp = client.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    assert crop_resp.status_code == 404
    assert crop_resp.json()["detail"]["code"] == "SCAN_EXPIRED"

    # Verify no candidate crop files were left behind
    all_files = list(storage_root.iterdir())
    assert all_files == [storage_root / f"{scan.id}.jpg"]

    # Attempt to detect expired scan
    detect_resp = client.post(f"/api/v1/scans/{scan.id}/detect")
    assert detect_resp.status_code == 404
    assert detect_resp.json()["detail"]["code"] == "SCAN_EXPIRED"

    # Confirm scan was not resurrected/modified
    db.expire_all()
    scan_db = db.query(Scan).filter(Scan.id == scan.id).first()
    assert scan_db is not None
    assert scan_db.crop_status == "none"


def test_regression_cleanup_unique_crop_filenames_and_orphans(
    db: Session, tmp_path: Path
) -> None:
    import os

    storage_root = tmp_path / "uploads"
    storage_root.mkdir(parents=True, exist_ok=True)

    scan_id = "11111111-2222-3333-4444-555555555555"
    source_file = storage_root / f"{scan_id}.jpg"
    valid_crop_file = storage_root / f"{scan_id}_crop_{uuid.uuid4().hex}.jpg"
    source_file.write_bytes(b"source jpeg")
    valid_crop_file.write_bytes(b"valid cropped jpeg")

    now = datetime.now(UTC).replace(tzinfo=None)
    future = now + timedelta(hours=12)

    scan = Scan(
        id=scan_id,
        status="uploaded",
        image_path=f"{scan_id}.jpg",
        content_type="image/jpeg",
        width=100,
        height=100,
        file_size=10,
        created_at=now,
        expires_at=future,
        crop_status="preview",
        crop_path=valid_crop_file.name,
    )
    db.add(scan)
    db.commit()

    # Old abandoned candidate file (>24h old)
    old_abandoned_file = storage_root / f"{scan_id}_crop_{uuid.uuid4().hex}.jpg"
    old_abandoned_file.write_bytes(b"old abandoned crop")
    old_time = datetime.now(UTC).timestamp() - 3600 * 25
    os.utime(old_abandoned_file, (old_time, old_time))

    # Recent in-progress candidate file (<24h old, e.g. 5 minutes old)
    recent_in_progress_file = storage_root / f"{scan_id}_crop_{uuid.uuid4().hex}.jpg"
    recent_in_progress_file.write_bytes(b"recent candidate crop")
    recent_time = datetime.now(UTC).timestamp() - 300
    os.utime(recent_in_progress_file, (recent_time, recent_time))

    removed, failed = cleanup_orphan_files(db, storage_root=storage_root)

    # Only old abandoned file is removed; active crop and recent candidate are preserved
    assert removed == 1
    assert failed == 0
    assert not old_abandoned_file.exists()
    assert valid_crop_file.exists()
    assert recent_in_progress_file.exists()
    assert source_file.exists()
