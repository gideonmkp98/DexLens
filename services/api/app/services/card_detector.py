import logging
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Standard Pokémon card dimensions: 63 mm x 88 mm => ~0.7159 aspect ratio (portrait)
POKEMON_CARD_ASPECT_RATIO = 63.0 / 88.0  # ~0.7159
INVERSE_ASPECT_RATIO = 88.0 / 63.0  # ~1.3968
# Allow perspective distortion, but never accept an almost-square playmat or
# image boundary as a card. The previous 0.28 tolerance admitted ratios up to
# ~0.996 and caused large background contours to outrank the actual card.
MAX_CARD_ASPECT_DEVIATION = 0.18


class Point(BaseModel):
    x: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized X coordinate in range [0.0, 1.0]",
    )
    y: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized Y coordinate in range [0.0, 1.0]",
    )


class CropCorners(BaseModel):
    top_left: Point
    top_right: Point
    bottom_right: Point
    bottom_left: Point

    def as_list(self) -> list[Point]:
        return [self.top_left, self.top_right, self.bottom_right, self.bottom_left]

    def as_dict(self) -> dict[str, dict[str, float]]:
        return {
            "top_left": {"x": self.top_left.x, "y": self.top_left.y},
            "top_right": {"x": self.top_right.x, "y": self.top_right.y},
            "bottom_right": {"x": self.bottom_right.x, "y": self.bottom_right.y},
            "bottom_left": {"x": self.bottom_left.x, "y": self.bottom_left.y},
        }


class InvalidCornersError(ValueError):
    """Raised when provided corner coordinates violate geometric constraints."""

    def __init__(self, message: str, code: str = "INVALID_CORNERS"):
        self.message = message
        self.code = code
        super().__init__(message)


def _cross_product_2d(
    p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float]
) -> float:
    """Compute the 2D cross product of vector (p2 - p1) and (p3 - p2)."""
    v1_x = p2[0] - p1[0]
    v1_y = p2[1] - p1[1]
    v2_x = p3[0] - p2[0]
    v2_y = p3[1] - p2[1]
    return v1_x * v2_y - v1_y * v2_x


def _segments_intersect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    """Check if segment (p1-p2) strictly intersects segment (p3-p4)."""

    def ccw(
        a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
    ) -> bool:
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    return (ccw(p1, p3, p4) != ccw(p2, p3, p4)) and (ccw(p1, p2, p3) != ccw(p1, p2, p4))


def calculate_polygon_area(
    points: list[tuple[float, float]] | list[list[float]] | np.ndarray,
) -> float:
    """Calculate the area of a polygon using the Shoelace formula."""
    pts = list(points)
    n = len(pts)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return abs(area) / 2.0


def validate_corners(corners: CropCorners, min_area: float = 0.005) -> None:
    """Validate that corners satisfy all geometric and server-side constraints.

    Constraints:
      1. Exactly 4 points (enforced by schema).
      2. Coordinates are finite numbers between 0.0 and 1.0.
      3. No duplicate or overly close points (minimum distance threshold).
      4. No crossing or self-intersecting edges.
      5. Strictly convex quadrilateral.
      6. Minimum surface area.
    """
    pts = [
        (corners.top_left.x, corners.top_left.y),
        (corners.top_right.x, corners.top_right.y),
        (corners.bottom_right.x, corners.bottom_right.y),
        (corners.bottom_left.x, corners.bottom_left.y),
    ]

    # 1. Finite checks
    for idx, (x, y) in enumerate(pts):
        if not (math.isfinite(x) and math.isfinite(y)):
            raise InvalidCornersError(
                f"Corner coordinate at index {idx} is not a finite number."
            )
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise InvalidCornersError(
                f"Corner coordinate ({x:.4f}, {y:.4f}) is out of bounds [0.0, 1.0]."
            )

    # 2. Distinct points
    min_dist = 0.01  # At least 1% of normalized dimension
    for i in range(4):
        for j in range(i + 1, 4):
            dx = pts[i][0] - pts[j][0]
            dy = pts[i][1] - pts[j][1]
            dist = math.hypot(dx, dy)
            if dist < min_dist:
                raise InvalidCornersError(
                    f"Corners {i} and {j} are too close (distance: {dist:.4f})."
                )

    # 3. Non-self-intersecting edges
    # Opposite edges: (p0-p1) vs (p2-p3), and (p1-p2) vs (p3-p0)
    if _segments_intersect(pts[0], pts[1], pts[2], pts[3]):
        raise InvalidCornersError(
            "Opposite edges intersect; corners do not form a valid quad."
        )
    if _segments_intersect(pts[1], pts[2], pts[3], pts[0]):
        raise InvalidCornersError(
            "Opposite edges intersect; corners do not form a valid quad."
        )

    # 4. Strict convexity & consistent winding (clockwise or counter-clockwise)
    cross_products = []
    for i in range(4):
        p_prev = pts[i]
        p_curr = pts[(i + 1) % 4]
        p_next = pts[(i + 2) % 4]
        cp = _cross_product_2d(p_prev, p_curr, p_next)
        cross_products.append(cp)

    signs = [cp > 1e-7 for cp in cross_products]
    all_positive = all(signs)
    all_negative = all(not s for s in signs)

    if not (all_positive or all_negative):
        raise InvalidCornersError(
            "Corners must form a strictly convex quadrilateral with no reflex angles."
        )

    # 5. Sufficient area
    area = calculate_polygon_area(pts)
    if area < min_area:
        raise InvalidCornersError(
            f"Quad area ({area:.4f}) is too small (minimum: {min_area})."
        )


def get_default_corners(inset: float = 0.12) -> CropCorners:
    """Return a standard fallback rectangular selection inset from image edges."""
    return CropCorners(
        top_left=Point(x=inset, y=inset),
        top_right=Point(x=1.0 - inset, y=inset),
        bottom_right=Point(x=1.0 - inset, y=1.0 - inset),
        bottom_left=Point(x=inset, y=1.0 - inset),
    )


def order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 (x, y) points into [top-left, top-right, bottom-right, bottom-left].

    Handles arbitrary rotation by calculating the centroid and sorting points
    in circular clockwise order starting from the top-left quadrant.
    """
    pts = pts.reshape(4, 2).astype(np.float32)

    # Calculate centroid
    center = np.mean(pts, axis=0)

    # Calculate angles from center to each point
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])

    # Sort clockwise
    sort_idx = np.argsort(angles)
    pts_sorted = pts[sort_idx]

    # Find the top-left point (smallest x + y, or closest to origin)
    sum_coords = pts_sorted[:, 0] + pts_sorted[:, 1]
    tl_idx = int(np.argmin(sum_coords))

    # Roll array so top-left is first
    ordered = np.roll(pts_sorted, -tl_idx, axis=0)

    # Ensure clockwise orientation: cross product of (p1 - p0) and (p2 - p1)
    cp = (ordered[1, 0] - ordered[0, 0]) * (ordered[2, 1] - ordered[1, 1]) - (
        ordered[1, 1] - ordered[0, 1]
    ) * (ordered[2, 0] - ordered[0, 0])
    if cp < 0:
        # Counter-clockwise: swap top-right and bottom-left to maintain [TL, TR, BR, BL]
        ordered = ordered[[0, 3, 2, 1]]

    return ordered


def detect_card_corners(
    image_path: str | Path,
) -> tuple[bool, CropCorners, str, float]:
    """Detect a single Pokémon card in the stored normalized image.

    Features:
      - Multi-cue edge and gradient detection supporting vintage yellow borders,
        modern Scarlet & Violet gray/silver borders, and full-art cards.
      - Evaluates multiple plausible quadrilaterals across geometry, edge support,
        border gradients, and containment.
      - Distinguishes outer card boundary from internal illustration windows,
        rule boxes, or text blocks using containment graph analysis.
      - Fully supports close-up images occupying 80-98% of the frame.
      - Sensible fallback with explanatory user message when detection is uncertain.

    Returns:
        tuple of (detected, corners, message, heuristic_score)
        - detected: bool indicating if a plausible card contour was found.
        - corners: CropCorners with either detected coordinates or sensible defaults.
        - message: human-readable explanation of detection outcome.
        - heuristic_score: heuristic quality score (0.0 to 1.0, not a probability).
    """
    path = Path(image_path)
    if not path.is_file():
        logger.warning("Image file %s does not exist for card detection", path)
        return (
            False,
            get_default_corners(),
            "Scan image not found.",
            0.0,
        )

    # Load image
    img = cv2.imread(str(path))
    if img is None:
        logger.warning("Could not read image %s with OpenCV", path)
        return (
            False,
            get_default_corners(),
            "Could not decode image file.",
            0.0,
        )

    orig_h, orig_w = img.shape[:2]

    # Work on a resized copy for fast and clean edge detection if very large
    max_proc_dim = 1200
    scale = 1.0
    if max(orig_w, orig_h) > max_proc_dim:
        scale = max_proc_dim / max(orig_w, orig_h)
        proc_w = max(1, int(round(orig_w * scale)))
        proc_h = max(1, int(round(orig_h * scale)))
        proc_img = cv2.resize(img, (proc_w, proc_h), interpolation=cv2.INTER_AREA)
    else:
        proc_img = img

    h, w = proc_img.shape[:2]
    proc_area = float(w * h)

    gray = cv2.cvtColor(proc_img, cv2.COLOR_BGR2GRAY)
    if float(np.std(gray)) < 12.0:
        logger.info("Image %s has insufficient contrast (std < 12.0)", path.name)
        return (
            False,
            get_default_corners(),
            "Geen kaartcontour gedetecteerd. Pas de selectie handmatig aan.",
            0.0,
        )

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    blurred_proc = cv2.GaussianBlur(proc_img, (5, 5), 0)

    # 1. Multi-channel color gradient:
    # Computes gradient magnitude across all 3 color channels (BGR) to detect
    # edges regardless of whether the contrast is in luminance, hue, or saturation
    # (crucial for silver/gray borders and full-art cards).
    gx = cv2.Sobel(blurred_proc, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred_proc, cv2.CV_32F, 0, 1, ksize=3)
    mag_bgr = cv2.magnitude(gx, gy)
    max_grad_mag = np.max(mag_bgr, axis=2)
    norm_grad = np.clip(max_grad_mag, 0, 255).astype(np.uint8)

    # 2. HSV channels for saturation and brightness (value) separation
    hsv = cv2.cvtColor(proc_img, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    # Morphological kernel to bridge small gaps and rounded card corners
    morph_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    # Build complementary edge & segmentation maps
    edge_maps: list[np.ndarray] = []

    # Strategy A: Multi-channel color Canny (catches gray, full-art, and color borders)
    edge_maps.append(cv2.Canny(norm_grad, 40, 120))

    # Strategy B: Grayscale Canny with median-adaptive & fixed threshold pairs
    median_val = float(np.median(gray))
    edge_maps.append(
        cv2.Canny(
            blurred,
            int(max(0, 0.5 * median_val)),
            int(min(255, 1.5 * median_val)),
        )
    )
    edge_maps.append(cv2.Canny(blurred, 30, 100))
    edge_maps.append(cv2.Canny(blurred, 50, 160))

    # Strategy C: Adaptive thresholding (handles non-uniform lighting / shadows)
    adaptive = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
    )
    edge_maps.append(adaptive)

    # Strategy D: Otsu thresholding on grayscale
    _, otsu_gray = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    edge_maps.append(otsu_gray)

    # Strategy E: Otsu on Saturation (separates saturated yellow borders / mats)
    _, otsu_sat = cv2.threshold(sat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    edge_maps.append(otsu_sat)

    # Strategy F: Otsu thresholding on Value / Brightness channel
    _, otsu_val = cv2.threshold(val, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    edge_maps.append(otsu_val)

    raw_candidates: list[dict[str, Any]] = []
    seen_polys: list[np.ndarray] = []

    # If the input image is already closely cropped to standard Pokémon card
    # aspect ratio, evaluate the full image boundary as a baseline candidate.
    img_aspect = min(orig_w, orig_h) / max(orig_w, orig_h)
    if abs(img_aspect - POKEMON_CARD_ASPECT_RATIO) <= 0.025:
        full_pts = np.array(
            [
                [0.0, 0.0],
                [float(w - 1), 0.0],
                [float(w - 1), float(h - 1)],
                [0.0, float(h - 1)],
            ],
            dtype=np.float32,
        )
        seen_polys.append(full_pts)
        raw_candidates.append(
            {
                "pts": full_pts,
                "area": 1.0,
                "aspect_score": 1.0,
                "area_score": 1.0,
                "parallel_score": 1.0,
                "angles_score": 1.0,
                "center_score": 1.0,
                "edge_score": 0.85,
                "contains_count": 0,
                "is_contained": False,
            }
        )

    for em in edge_maps:
        closed = cv2.morphologyEx(em, cv2.MORPH_CLOSE, morph_kernel)
        contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            # Area must be between 4% and 99.5% of frame (accommodates close-ups)
            if area < 0.04 * proc_area or area > 0.995 * proc_area:
                continue

            peri = cv2.arcLength(cnt, True)
            if peri <= 0:
                continue

            quads_to_test: list[np.ndarray] = []

            # Multi-epsilon polygon approximations
            approx_found = False
            for eps_factor in (0.012, 0.018, 0.025, 0.035, 0.05):
                approx = cv2.approxPolyDP(cnt, eps_factor * peri, True)
                if len(approx) == 4 and cv2.isContourConvex(approx):
                    quads_to_test.append(approx.reshape(4, 2))
                    approx_found = True
                    break

            # If polygon has 5-10 vertices (due to rounded corners or noisy edges),
            # fit minimum area bounding box to extract a valid 4-corner quad.
            if not approx_found and 5 <= len(approx) <= 10 and area > 0.08 * proc_area:
                min_rect = cv2.minAreaRect(cnt)
                box_pts = cv2.boxPoints(min_rect)
                quads_to_test.append(box_pts)

            for quad_pts in quads_to_test:
                ordered_pts = order_corners(quad_pts.astype(np.float32))

                # Side lengths
                s0 = float(np.linalg.norm(ordered_pts[1] - ordered_pts[0]))  # Top
                s1 = float(np.linalg.norm(ordered_pts[2] - ordered_pts[1]))  # Right
                s2 = float(np.linalg.norm(ordered_pts[3] - ordered_pts[2]))  # Bottom
                s3 = float(np.linalg.norm(ordered_pts[0] - ordered_pts[3]))  # Left

                if min(s0, s1, s2, s3) < 20:
                    continue

                # Aspect ratio check
                w_est = (s0 + s2) / 2.0
                h_est = (s1 + s3) / 2.0
                aspect = min(w_est, h_est) / max(w_est, h_est)

                ratio_diff = abs(aspect - POKEMON_CARD_ASPECT_RATIO)
                if ratio_diff > MAX_CARD_ASPECT_DEVIATION:
                    continue

                # Parallelism of opposite edges
                opp_ratio_w = min(s0, s2) / max(s0, s2)
                opp_ratio_h = min(s1, s3) / max(s1, s3)
                if opp_ratio_w < 0.60 or opp_ratio_h < 0.60:
                    continue

                # Polygon area
                quad_area = calculate_polygon_area(ordered_pts)
                norm_area = quad_area / proc_area
                if norm_area < 0.04 or norm_area > 0.995:
                    continue

                # For quads filling >95% frame, require close aspect ratio match
                # to prevent accepting the camera sensor frame on non-card photos
                if norm_area > 0.95 and ratio_diff > 0.06:
                    continue

                # Corner angles check: ensure quad is near-rectangular (55° to 125°)
                angles = []
                for idx in range(4):
                    p_prev = ordered_pts[(idx - 1) % 4]
                    p_curr = ordered_pts[idx]
                    p_next = ordered_pts[(idx + 1) % 4]
                    v1 = p_prev - p_curr
                    v2 = p_next - p_curr
                    dot = float(np.dot(v1, v2))
                    norm1 = float(np.linalg.norm(v1))
                    norm2 = float(np.linalg.norm(v2))
                    cos_val = dot / (norm1 * norm2 + 1e-7)
                    angle_deg = float(
                        np.degrees(np.arccos(np.clip(cos_val, -1.0, 1.0)))
                    )
                    angles.append(angle_deg)

                if any(ang < 55.0 or ang > 125.0 for ang in angles):
                    continue

                # Spatial deduplication: avoid adding near-duplicate polygons
                is_duplicate = False
                for prev_pts in seen_polys:
                    if np.max(np.abs(prev_pts - ordered_pts)) < 15:
                        is_duplicate = True
                        break
                if is_duplicate:
                    continue
                seen_polys.append(ordered_pts)

                # 1. Aspect score (0 to 1, higher is closer to ~0.716)
                aspect_score = max(0.0, 1.0 - (ratio_diff / MAX_CARD_ASPECT_DEVIATION))

                # 2. Area score (monotonic sqrt favors larger outer card boundary)
                area_score = math.sqrt(norm_area)

                # 3. Parallelism & right-angles score
                parallel_score = (opp_ratio_w + opp_ratio_h) / 2.0
                angles_score = 1.0 - float(
                    np.mean([abs(ang - 90.0) / 45.0 for ang in angles])
                )

                # 4. Center proximity score
                cx = float(np.mean(ordered_pts[:, 0])) / w
                cy = float(np.mean(ordered_pts[:, 1])) / h
                dist_to_center = math.hypot(cx - 0.5, cy - 0.5)
                center_score = max(0.0, 1.0 - (dist_to_center / 0.55))

                # 5. Boundary edge support score: sample gradient along the 4 edges
                edge_supports = []
                for idx in range(4):
                    p1 = ordered_pts[idx]
                    p2 = ordered_pts[(idx + 1) % 4]
                    t_vals = np.linspace(0.08, 0.92, 25)
                    xs = np.clip(
                        np.round(p1[0] + t_vals * (p2[0] - p1[0])).astype(int),
                        0,
                        w - 1,
                    )
                    ys = np.clip(
                        np.round(p1[1] + t_vals * (p2[1] - p1[1])).astype(int),
                        0,
                        h - 1,
                    )
                    # Sample 3x3 local neighborhood in multi-channel gradient map
                    sampled_vals = [
                        np.max(
                            norm_grad[
                                max(0, y - 1) : min(h, y + 2),
                                max(0, x - 1) : min(w, x + 2),
                            ]
                        )
                        for x, y in zip(xs, ys, strict=False)
                    ]
                    edge_supports.append(np.mean(np.array(sampled_vals) > 20))
                edge_score = float(np.mean(edge_supports))

                raw_candidates.append(
                    {
                        "pts": ordered_pts,
                        "area": norm_area,
                        "aspect_score": aspect_score,
                        "area_score": area_score,
                        "parallel_score": parallel_score,
                        "angles_score": angles_score,
                        "center_score": center_score,
                        "edge_score": edge_score,
                        "contains_count": 0,
                        "is_contained": False,
                    }
                )

    # Containment Analysis:
    # Identify whether a candidate contains other smaller candidates (e.g. outer card
    # containing illustration or text box) or is contained inside a larger candidate.
    num_candidates = len(raw_candidates)
    for i in range(num_candidates):
        pts_i = raw_candidates[i]["pts"]
        area_i = raw_candidates[i]["area"]
        for j in range(num_candidates):
            if i == j:
                continue
            pts_j = raw_candidates[j]["pts"]
            area_j = raw_candidates[j]["area"]
            # Candidate i contains candidate j if area is larger and centroid is inside
            if area_i >= 1.15 * area_j:
                cj = (
                    float(np.mean(pts_j[:, 0])),
                    float(np.mean(pts_j[:, 1])),
                )
                inside = cv2.pointPolygonTest(pts_i.astype(np.float32), cj, False) >= 0
                if inside:
                    raw_candidates[i]["contains_count"] += 1
                    raw_candidates[j]["is_contained"] = True

    # Calculate final composite scores
    for cand in raw_candidates:
        geom_score = 0.5 * cand["parallel_score"] + 0.5 * cand["angles_score"]
        base_score = (
            0.30 * cand["aspect_score"]
            + 0.25 * cand["area_score"]
            + 0.20 * cand["edge_score"]
            + 0.15 * geom_score
            + 0.10 * cand["center_score"]
        )
        # Enclosing card boost
        if cand["contains_count"] > 0:
            base_score += min(0.20, 0.10 * cand["contains_count"])
        # Contained internal box penalty (illustration/rule box cannot beat outer card)
        if cand["is_contained"]:
            base_score -= 0.35

        cand["score"] = float(np.clip(base_score, 0.0, 1.0))

    if not raw_candidates:
        logger.info("No plausible card quad candidates detected for %s", path.name)
        return (
            False,
            get_default_corners(),
            "Geen kaartcontour gedetecteerd. Pas de selectie handmatig aan.",
            0.0,
        )

    # Sort candidates by score descending
    raw_candidates.sort(key=lambda c: c["score"], reverse=True)
    best = raw_candidates[0]

    # Uncertainty handling:
    # 1. If best score is below plausibility threshold
    if best["score"] < 0.50:
        logger.info(
            "Best candidate score %.2f is below plausibility threshold for %s",
            best["score"],
            path.name,
        )
        return (
            False,
            get_default_corners(),
            (
                "Kaartranden zijn onzeker of hebben laag contrast met de"
                " achtergrond. Pas de selectie handmatig aan."
            ),
            round(float(best["score"]), 3),
        )

    # 2. If best candidate is marked as contained (only internal feature found)
    if best["is_contained"]:
        logger.info(
            "Best candidate is an internal card region (illustration/rule box) for %s",
            path.name,
        )
        return (
            False,
            get_default_corners(),
            (
                "Alleen interne kaartdetails gevonden, geen volledige"
                " kaartcontour. Pas de selectie handmatig aan."
            ),
            round(float(best["score"]), 3),
        )

    # Convert coordinates back to normalized [0.0, 1.0] relative to original image
    pts_proc = best["pts"]
    pts_orig = pts_proc / scale

    norm_pts = np.zeros_like(pts_orig, dtype=np.float64)
    norm_pts[:, 0] = np.clip(pts_orig[:, 0] / float(orig_w), 0.0, 1.0)
    norm_pts[:, 1] = np.clip(pts_orig[:, 1] / float(orig_h), 0.0, 1.0)

    detected_corners = CropCorners(
        top_left=Point(
            x=round(float(norm_pts[0, 0]), 5), y=round(float(norm_pts[0, 1]), 5)
        ),
        top_right=Point(
            x=round(float(norm_pts[1, 0]), 5), y=round(float(norm_pts[1, 1]), 5)
        ),
        bottom_right=Point(
            x=round(float(norm_pts[2, 0]), 5), y=round(float(norm_pts[2, 1]), 5)
        ),
        bottom_left=Point(
            x=round(float(norm_pts[3, 0]), 5), y=round(float(norm_pts[3, 1]), 5)
        ),
    )

    try:
        validate_corners(detected_corners)
    except InvalidCornersError as err:
        logger.warning("Detected corners failed validation: %s", err)
        return (
            False,
            get_default_corners(),
            "Gedetecteerde contouren zijn ongeldig. Pas de hoeken handmatig aan.",
            0.0,
        )

    logger.info(
        "Card detected successfully with score %.2f for %s",
        best["score"],
        path.name,
    )
    return (
        True,
        detected_corners,
        "Kaart automatisch gedetecteerd. Controleer en pas de hoeken aan indien nodig.",
        round(float(best["score"]), 3),
    )
