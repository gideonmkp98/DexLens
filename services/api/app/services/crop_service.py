import logging
import os
import uuid
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings
from app.services.card_detector import (
    POKEMON_CARD_ASPECT_RATIO,
    CropCorners,
    validate_corners,
)

logger = logging.getLogger(__name__)


class CropProcessingError(Exception):
    """Raised when crop or perspective warping fails."""

    def __init__(self, message: str, code: str = "CROP_FAILED"):
        self.message = message
        self.code = code
        super().__init__(message)


def perform_crop_and_warp(
    source_path: Path,
    target_path: Path,
    corners: CropCorners,
    rotation: int = 0,
    max_dimension: int = 2000,
    jpeg_quality: int | None = None,
) -> tuple[int, int, int]:
    """Execute perspective warp and rotation, atomically saving the result as JPEG.

    Args:
        source_path: Path to existing normalized scan image.
        target_path: Destination path for cropped image.
        corners: Validated CropCorners with normalized coordinates.
        rotation: Clockwise rotation in degrees (must be 0, 90, 180, or 270).
        max_dimension: Upper ceiling on long edge to prevent excessive memory/storage.
        jpeg_quality: JPEG compression quality (defaults to config setting).

    Returns:
        tuple of (final_width, final_height, file_size_bytes)
    """
    if rotation not in (0, 90, 180, 270):
        raise CropProcessingError(
            f"Invalid rotation {rotation}. Allowed values: 0, 90, 180, 270.",
            code="INVALID_ROTATION",
        )

    # Validate corners geometrically
    validate_corners(corners)

    if jpeg_quality is None:
        jpeg_quality = settings.UPLOAD_JPEG_QUALITY

    if not source_path.is_file():
        raise CropProcessingError(
            "Source scan image does not exist on disk.",
            code="IMAGE_NOT_FOUND",
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = target_path.with_suffix(f".tmp_{uuid.uuid4().hex}")

    try:
        # Load source image using OpenCV
        src_bgr = cv2.imread(str(source_path))
        if src_bgr is None:
            raise CropProcessingError(
                "Failed to decode source scan image.",
                code="IMAGE_DECODE_ERROR",
            )

        src_h, src_w = src_bgr.shape[:2]

        # Convert normalized coordinates to source pixel coordinates
        tl = np.array(
            [corners.top_left.x * src_w, corners.top_left.y * src_h], dtype=np.float32
        )
        tr = np.array(
            [corners.top_right.x * src_w, corners.top_right.y * src_h], dtype=np.float32
        )
        br = np.array(
            [corners.bottom_right.x * src_w, corners.bottom_right.y * src_h],
            dtype=np.float32,
        )
        bl = np.array(
            [corners.bottom_left.x * src_w, corners.bottom_left.y * src_h],
            dtype=np.float32,
        )

        # Compute edge lengths
        width_top = float(np.linalg.norm(tr - tl))
        width_bottom = float(np.linalg.norm(br - bl))
        height_left = float(np.linalg.norm(bl - tl))
        height_right = float(np.linalg.norm(br - tr))

        max_w = max(width_top, width_bottom)
        max_h = max(height_left, height_right)

        if max_w < 10 or max_h < 10:
            raise CropProcessingError(
                "Selected crop region is too small to extract.",
                code="CROP_TOO_SMALL",
            )

        # Regularize to standard card aspect ratio preserving maximal optical resolution
        dst_w = int(round(max_w))
        dst_h = int(round(max_h))

        is_portrait = dst_h >= dst_w
        measured_aspect = (dst_w / dst_h) if is_portrait else (dst_h / dst_w)

        if 0.58 <= measured_aspect <= 0.88:
            if is_portrait:
                target_h = max(dst_h, int(round(dst_w / POKEMON_CARD_ASPECT_RATIO)))
                dst_w = int(round(target_h * POKEMON_CARD_ASPECT_RATIO))
                dst_h = target_h
            else:
                target_w = max(dst_w, int(round(dst_h / POKEMON_CARD_ASPECT_RATIO)))
                dst_h = int(round(target_w * POKEMON_CARD_ASPECT_RATIO))
                dst_w = target_w

        # Enforce max dimension ceiling without upscaling
        long_edge = max(dst_w, dst_h)
        if long_edge > max_dimension:
            scale_down = max_dimension / float(long_edge)
            dst_w = max(1, int(round(dst_w * scale_down)))
            dst_h = max(1, int(round(dst_h * scale_down)))

        src_pts = np.array([tl, tr, br, bl], dtype=np.float32)
        dst_pts = np.array(
            [
                [0, 0],
                [dst_w - 1, 0],
                [dst_w - 1, dst_h - 1],
                [0, dst_h - 1],
            ],
            dtype=np.float32,
        )

        transform_matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped_bgr = cv2.warpPerspective(
            src_bgr,
            transform_matrix,
            (dst_w, dst_h),
            flags=cv2.INTER_LANCZOS4,
        )

        # Apply rotation
        if rotation == 90:
            warped_bgr = cv2.rotate(warped_bgr, cv2.ROTATE_90_CLOCKWISE)
        elif rotation == 180:
            warped_bgr = cv2.rotate(warped_bgr, cv2.ROTATE_180)
        elif rotation == 270:
            warped_bgr = cv2.rotate(warped_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)

        # Convert BGR to RGB for Pillow saving
        rgb_img = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_img)

        # Save to temporary staging path
        pil_img.save(
            staging_path,
            format="JPEG",
            quality=jpeg_quality,
            optimize=True,
        )

        final_w, final_h = pil_img.size
        file_size = staging_path.stat().st_size

        # Atomic replacement: replaces target_path atomically
        os.replace(staging_path, target_path)

        return final_w, final_h, file_size

    except CropProcessingError:
        if staging_path.exists():
            staging_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if staging_path.exists():
            staging_path.unlink(missing_ok=True)
        logger.exception("Failed to execute crop and warp for %s", source_path)
        raise CropProcessingError(
            f"Image crop failed: {exc}",
            code="CROP_PROCESSING_ERROR",
        ) from exc
