import logging
import os
import uuid
from collections.abc import Sequence
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.Image import DecompressionBombError

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS: Sequence[str] = ("JPEG", "PNG", "WEBP")


class ImageValidationError(Exception):
    """Base exception for image validation failures."""

    def __init__(self, code: str, message: str, status_code: int = 422):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class UnsupportedFormatError(ImageValidationError):
    """Raised when the uploaded format is not supported (HTTP 415)."""

    def __init__(
        self,
        message: str = "Unsupported image format. Allowed formats: JPEG, PNG, WebP.",
    ):
        super().__init__(code="UNSUPPORTED_FORMAT", message=message, status_code=415)


class FileTooLargeError(ImageValidationError):
    """Raised when file or stream size exceeds the configured byte limit (HTTP 413)."""

    def __init__(self, message: str = "File exceeds maximum permitted size."):
        super().__init__(code="FILE_TOO_LARGE", message=message, status_code=413)


class EmptyFileError(ImageValidationError):
    """Raised when uploaded file contains zero bytes (HTTP 422)."""

    def __init__(self, message: str = "Uploaded file is empty."):
        super().__init__(code="EMPTY_FILE", message=message, status_code=422)


class CorruptImageError(ImageValidationError):
    """Raised when image stream is corrupt, truncated, or unreadable (HTTP 422)."""

    def __init__(self, message: str = "Image file is corrupt or truncated."):
        super().__init__(code="CORRUPT_IMAGE", message=message, status_code=422)


class AnimatedImageError(ImageValidationError):
    """Raised when image contains animations or multiple frames (HTTP 422)."""

    def __init__(
        self, message: str = "Animated or multi-frame images are not supported."
    ):
        super().__init__(
            code="ANIMATED_IMAGE_NOT_SUPPORTED", message=message, status_code=422
        )


class PixelLimitExceededError(ImageValidationError):
    """Raised when image total pixel count exceeds the configured maximum (HTTP 422)."""

    def __init__(self, message: str = "Image pixel limit exceeded."):
        super().__init__(code="PIXEL_LIMIT_EXCEEDED", message=message, status_code=422)


async def stream_upload_to_temp_file(
    upload_file: UploadFile,
    temp_dir: Path,
    max_bytes: int,
    chunk_size: int = 65536,
) -> tuple[Path, int]:
    """Stream an UploadFile to a temporary file enforcing max_bytes in chunks.

    Raises:
        FileTooLargeError: If read bytes exceed max_bytes.
        EmptyFileError: If 0 bytes were read.
    """
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = temp_dir / f"upload_{uuid.uuid4().hex}.tmp"
    total_bytes = 0

    try:
        with open(temp_file_path, "wb") as f:
            while True:
                chunk = await upload_file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise FileTooLargeError(
                        f"File size exceeds maximum limit of {max_bytes} bytes."
                    )
                f.write(chunk)

        if total_bytes == 0:
            raise EmptyFileError("Uploaded file is empty.")

        return temp_file_path, total_bytes
    except Exception:
        if temp_file_path.exists():
            temp_file_path.unlink(missing_ok=True)
        raise


def process_and_normalize_image(
    source_path: Path,
    target_path: Path,
    max_pixels: int | None = None,
    max_dimension: int | None = None,
    jpeg_quality: int | None = None,
) -> tuple[int, int, int]:
    """Validate, normalize, and atomically save the image as JPEG.

    Steps:
      1. Inspect format, dimensions, frame count.
      2. Verify image integrity.
      3. Apply EXIF orientation.
      4. Flatten transparency onto a white background.
      5. Convert to RGB (handles RGBA, P, L, CMYK, etc.).
      6. Downscale if long edge exceeds max_dimension (never upscale).
      7. Save as JPEG with jpeg_quality and stripped metadata.
      8. Atomically rename to target_path.

    Returns:
      (width, height, file_size) of the saved normalized JPEG.
    """
    if max_pixels is None:
        max_pixels = settings.UPLOAD_MAX_PIXELS
    if max_dimension is None:
        max_dimension = settings.UPLOAD_MAX_DIMENSION
    if jpeg_quality is None:
        jpeg_quality = settings.UPLOAD_JPEG_QUALITY

    target_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = target_path.with_suffix(f".tmp_{uuid.uuid4().hex}")

    try:
        # Step 1 & 2: Header verification and structural checks
        try:
            with Image.open(source_path) as img:
                fmt = img.format
                if fmt not in SUPPORTED_FORMATS:
                    raise UnsupportedFormatError(
                        f"Unsupported image format '{fmt or 'unknown'}'. "
                        f"Allowed formats: {', '.join(SUPPORTED_FORMATS)}."
                    )

                if (
                    getattr(img, "is_animated", False)
                    or getattr(img, "n_frames", 1) > 1
                ):
                    raise AnimatedImageError(
                        "Animated or multi-frame images are not supported."
                    )

                w, h = img.size
                if w <= 0 or h <= 0:
                    raise CorruptImageError("Invalid image dimensions.")

                if (w * h) > max_pixels:
                    raise PixelLimitExceededError(
                        f"Image size {w}x{h} ({w * h} pixels) exceeds maximum "
                        f"permitted limit of {max_pixels} pixels."
                    )

                # Verify integrity
                img.verify()
        except ImageValidationError:
            raise
        except UnidentifiedImageError as err:
            raise UnsupportedFormatError(
                "Uploaded file is not a valid or supported image."
            ) from err
        except DecompressionBombError as err:
            raise PixelLimitExceededError(
                "Image pixel count exceeds decompression bomb limits."
            ) from err
        except (OSError, SyntaxError, ValueError) as err:
            raise CorruptImageError("Image is corrupt or truncated.") from err

        # Step 3 to 7: Re-open for decoding, normalization, and saving
        try:
            with Image.open(source_path) as img:
                # Apply EXIF orientation
                transposed = ImageOps.exif_transpose(img)
                if transposed is not None:
                    img = transposed

                # Flatten transparency onto white background and convert to RGB
                if img.mode in ("RGBA", "LA") or img.mode == "P":
                    rgba = img.convert("RGBA")
                    bg = Image.new("RGB", rgba.size, (255, 255, 255))
                    alpha_channel = rgba.split()[3]
                    bg.paste(rgba, mask=alpha_channel)
                    img = bg
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Downscale proportionally if long edge > max_dimension
                w, h = img.size
                long_edge = max(w, h)
                if long_edge > max_dimension:
                    scale = max_dimension / long_edge
                    new_w = max(1, round(w * scale))
                    new_h = max(1, round(h * scale))
                    img = img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

                # Save to staging path without EXIF/metadata
                try:
                    img.save(
                        staging_path,
                        format="JPEG",
                        quality=jpeg_quality,
                        optimize=True,
                    )
                except OSError as err:
                    raise ImageValidationError(
                        "STORAGE_ERROR",
                        "Unable to store image. Please try again.",
                        status_code=500,
                    ) from err

                final_w, final_h = img.size
                final_size = staging_path.stat().st_size
        except (OSError, SyntaxError, ValueError) as err:
            raise CorruptImageError(
                "Image could not be decoded or normalized."
            ) from err

        # Step 8: Atomic rename
        os.replace(staging_path, target_path)
        return final_w, final_h, final_size

    except Exception:
        if staging_path.exists():
            staging_path.unlink(missing_ok=True)
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        raise
    finally:
        # Clean up source temp file
        if source_path.exists():
            source_path.unlink(missing_ok=True)
