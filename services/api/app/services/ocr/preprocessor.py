from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np


@dataclass
class CardImageQuality:
    """Assessment of the crop dimensions and readability detail."""

    width: int
    height: int
    is_low_res: bool = False
    warning: str | None = None
    guidance: str | None = None


@dataclass
class CardRegions:
    """Preprocessed regions of interest (ROIs) extracted from a confirmed card crop."""

    header_clean: np.ndarray
    header_enhanced: np.ndarray
    footer_clean: np.ndarray
    footer_enhanced: np.ndarray
    bottom_left_enhanced: np.ndarray
    bottom_right_enhanced: np.ndarray
    full_image_gray: np.ndarray
    image_quality: CardImageQuality
    header_sparse: np.ndarray
    footer_line: np.ndarray
    footer_number_left: np.ndarray
    body_clean: np.ndarray = field(default_factory=lambda: np.empty(0))
    body_enhanced: np.ndarray = field(default_factory=lambda: np.empty(0))
    hp_crop: np.ndarray = field(default_factory=lambda: np.empty(0))
    header_full: np.ndarray = field(default_factory=lambda: np.empty(0))
    title_variants: list[np.ndarray] = field(default_factory=list)
    number_variants: list[np.ndarray] = field(default_factory=list)
    footer_validation: list[np.ndarray] = field(default_factory=list)
    title_wide: np.ndarray = field(default_factory=lambda: np.empty(0))


def assess_crop_quality(width: int, height: int) -> CardImageQuality:
    """Evaluate whether the cropped card has sufficient resolution for reliable OCR."""
    is_low_res = width < 400 or height < 550
    warning = None
    guidance = None
    if is_low_res:
        warning = (
            f"Lage uitsnederesolutie ({width}x{height}px). "
            f"Fijne details van verzamelnummers kunnen onduidelijk zijn."
        )
        guidance = (
            "Upload een scherpere foto waarbij de kaart meer van het beeld vult, "
            "met minimale reflectie of schaduw."
        )
    return CardImageQuality(
        width=width,
        height=height,
        is_low_res=is_low_res,
        warning=warning,
        guidance=guidance,
    )


def _enhance_roi(gray: np.ndarray, min_height: int = 120) -> np.ndarray:
    """Upscale and apply adaptive contrast enhancement (CLAHE) to a grayscale ROI."""
    h, w = gray.shape[:2]
    if h == 0 or w == 0:
        return gray

    # Upscale small ROIs to improve OCR character definition
    if h < min_height:
        scale = min_height / float(h)
        new_w = int(w * scale)
        gray = cv2.resize(gray, (new_w, min_height), interpolation=cv2.INTER_CUBIC)

    # Apply CLAHE to equalize contrast while minimizing noise amplification
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return enhanced


def prepare_card_regions(image_or_path: str | Path | np.ndarray) -> CardRegions:
    """Load and partition a confirmed card crop into targeted regions for OCR.

    The original source crop is never modified. All processed variants
    are held temporarily in memory.
    """
    if isinstance(image_or_path, (str, Path)):
        img = cv2.imread(str(image_or_path), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Could not read image from {image_or_path}")
    else:
        img = image_or_path.copy()

    h, w = img.shape[:2]
    if h < 50 or w < 50:
        raise ValueError(f"Card image is too small ({w}x{h}) for OCR processing.")

    image_quality = assess_crop_quality(width=w, height=h)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1. Header Region (Card Name, omitting top-right HP and elemental symbol)
    # y: 2% to 16%, x: 4% to 80%
    y1_h, y2_h = int(0.02 * h), int(0.16 * h)
    x1_h, x2_h = int(0.04 * w), int(0.80 * w)
    header_crop = gray[y1_h:y2_h, x1_h:x2_h]
    header_enhanced = _enhance_roi(header_crop, min_height=140)

    # 2. Footer Region (Entire bottom band across width)
    # y: 82% to 98%, x: 2% to 98%
    y1_f, y2_f = int(0.82 * h), int(0.98 * h)
    x1_f, x2_f = int(0.02 * w), int(0.98 * w)
    footer_crop = gray[y1_f:y2_f, x1_f:x2_f]
    footer_enhanced = _enhance_roi(footer_crop, min_height=120)

    # 3. Bottom-Left ROI (Modern SV / SWSH numbers & set marks)
    # y: 83% to 98%, x: 2% to 54%
    y1_bl, y2_bl = int(0.83 * h), int(0.98 * h)
    x1_bl, x2_bl = int(0.02 * w), int(0.54 * w)
    bl_crop = gray[y1_bl:y2_bl, x1_bl:x2_bl]
    bl_enhanced = _enhance_roi(bl_crop, min_height=120)

    # 4. Bottom-Right ROI (Classic numbers e.g. Base, Neo, EX, XY, SM)
    # y: 83% to 98%, x: 48% to 98%
    y1_br, y2_br = int(0.83 * h), int(0.98 * h)
    x1_br, x2_br = int(0.48 * w), int(0.98 * w)
    br_crop = gray[y1_br:y2_br, x1_br:x2_br]
    br_enhanced = _enhance_roi(br_crop, min_height=120)

    # 5. Body Region (y ~ 0.42 to 0.85, x ~ 0.04 to 0.96)
    # Captures attacks, abilities, and rules text
    y1_b, y2_b = int(0.42 * h), int(0.85 * h)
    x1_b, x2_b = int(0.04 * w), int(0.96 * w)
    body_crop = gray[y1_b:y2_b, x1_b:x2_b]
    body_enhanced = _enhance_roi(body_crop, min_height=200)

    # 6. Dedicated HP Region (top-right of card: y: 0.02 to 0.18, x: 0.50 to 0.98)
    y1_hp, y2_hp = int(0.02 * h), int(0.18 * h)
    x1_hp, x2_hp = int(0.50 * w), int(0.98 * w)
    hp_crop = gray[y1_hp:y2_hp, x1_hp:x2_hp]

    # 7. Full Header Region across card width (y: 0.01 to 0.20, x: 0 to 1.0)
    # Preserves foil/color contrast for difficult silver/holographic cards
    header_full = gray[: int(0.18 * h), :]

    # Keep title-sized letters separate from the illustration and evolution text.
    # Two horizontal bounds cover basic and evolved layouts without assuming a
    # particular Pokémon. Padding prevents edge glyphs being treated as borders.
    title_variants = []
    for left in (0.10, 0.18):
        roi = gray[int(0.025 * h) : int(0.095 * h), int(left * w) : int(0.74 * w)]
        roi = cv2.resize(roi, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
        title_variants.append(
            cv2.copyMakeBorder(roi, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
        )
    # Global Otsu/CLAHE often turns textured foil backgrounds into solid ink.
    # Dark-ink masks provide independent footer evidence; keep the original
    # grayscale passes too, since white lettering needs a different treatment.
    number_variants = []
    for threshold in (60, 120):
        roi = cv2.threshold(gray[int(0.94 * h) :], threshold, 255, cv2.THRESH_BINARY)[1]
        roi = cv2.resize(roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        number_variants.append(
            cv2.copyMakeBorder(roi, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        )

    footer_validation = []
    bottom = gray[int(0.93 * h) :]
    for roi in (bottom, 255 - bottom):
        roi = cv2.resize(roi, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
        footer_validation.append(
            cv2.copyMakeBorder(roi, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)
        )

    return CardRegions(
        header_clean=header_crop,
        header_enhanced=header_enhanced,
        footer_clean=footer_crop,
        footer_enhanced=footer_enhanced,
        bottom_left_enhanced=bl_enhanced,
        bottom_right_enhanced=br_enhanced,
        full_image_gray=gray,
        image_quality=image_quality,
        header_sparse=cv2.resize(
            img[int(0.02 * h) : int(0.14 * h), int(0.10 * w) : int(0.78 * w)],
            None,
            fx=3,
            fy=3,
            interpolation=cv2.INTER_CUBIC,
        ),
        footer_line=cv2.resize(
            img[int(0.94 * h) : int(0.98 * h), int(0.02 * w) : int(0.98 * w)],
            None,
            fx=4,
            fy=4,
            interpolation=cv2.INTER_CUBIC,
        ),
        footer_number_left=cv2.resize(
            img[int(0.92 * h) : h, int(0.02 * w) : int(0.44 * w)],
            None,
            fx=3,
            fy=3,
            interpolation=cv2.INTER_CUBIC,
        ),
        body_clean=body_crop,
        body_enhanced=body_enhanced,
        hp_crop=hp_crop,
        header_full=header_full,
        title_wide=cv2.copyMakeBorder(
            cv2.resize(header_crop, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR),
            12,
            12,
            12,
            12,
            cv2.BORDER_CONSTANT,
            value=255,
        ),
        title_variants=title_variants,
        number_variants=number_variants,
        footer_validation=footer_validation,
    )
