import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)


class OcrError(Exception):
    """Base exception for OCR engine failures."""


class OcrUnavailableError(OcrError):
    """Raised when the OCR engine binary or language data is missing or unavailable."""


class OcrTimeoutError(OcrError):
    """Raised when an OCR operation exceeds the configured time limit or deadline."""


@dataclass
class OcrWord:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int] | None = None


@dataclass
class OcrResult:
    raw_text: str
    confidence: float = 0.0
    words: list[OcrWord] = field(default_factory=list)


def _is_timeout_error(err: BaseException) -> bool:
    if isinstance(err, (subprocess.TimeoutExpired, TimeoutError)):
        return True
    msg = str(err).lower()
    return "timeout" in msg or "timed out" in msg


def _is_unavailable_error(err: BaseException) -> bool:
    if isinstance(err, FileNotFoundError):
        return True
    msg = str(err).lower()
    indicators = [
        "not installed",
        "not found",
        "no such file or directory",
        "error opening data file",
        "traineddata",
        "failed loading language",
        "could not initialize tesseract",
        "cannot open language",
    ]
    return any(ind in msg for ind in indicators)


class OcrEngineProtocol(Protocol):
    """Replaceable OCR engine interface."""

    def recognize(
        self,
        image: Image.Image | np.ndarray,
        psm: int = 6,
        char_whitelist: str | None = None,
        timeout: float | None = None,
        deadline: float | None = None,
    ) -> OcrResult:
        """Run OCR on the given image or ROI with optional timeout/deadline."""
        ...


class TesseractOcrEngine:
    """Tesseract OCR engine implementation with bounded concurrency and timeouts."""

    def __init__(
        self,
        timeout_seconds: float | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.OCR_TIMEOUT_SECONDS
        )
        concurrency = (
            max_concurrency
            if max_concurrency is not None
            else settings.OCR_MAX_CONCURRENCY
        )
        self.max_concurrency = concurrency
        self._semaphore = threading.Semaphore(concurrency)

    def _convert_image(self, image: Image.Image | np.ndarray) -> Image.Image:
        if isinstance(image, np.ndarray):
            if len(image.shape) == 2:
                return Image.fromarray(image)
            if len(image.shape) == 3:
                # Expect BGR from OpenCV, convert to RGB
                if image.shape[2] == 3:
                    rgb = image[:, :, ::-1]
                    return Image.fromarray(rgb)
                if image.shape[2] == 4:
                    rgba = image[:, :, [2, 1, 0, 3]]
                    return Image.fromarray(rgba)
            return Image.fromarray(image)
        return image

    def recognize(
        self,
        image: Image.Image | np.ndarray,
        psm: int = 6,
        char_whitelist: str | None = None,
        timeout: float | None = None,
        deadline: float | None = None,
    ) -> OcrResult:
        try:
            import pytesseract
            from pytesseract import Output, TesseractError, TesseractNotFoundError
        except ImportError as err:
            raise OcrUnavailableError("pytesseract library is not installed.") from err

        now = time.monotonic()
        if deadline is not None:
            if now >= deadline:
                remaining_sec = deadline - now
                raise OcrTimeoutError(
                    f"Overall OCR deadline exceeded ({remaining_sec:.2f}s left)."
                )
            effective_timeout = max(0.01, deadline - now)
            effective_deadline = deadline
        else:
            effective_timeout = timeout if timeout is not None else self.timeout_seconds
            effective_deadline = now + effective_timeout

        pil_img = self._convert_image(image)

        # Enforce maximum dimension bounds
        max_dim = settings.OCR_MAX_IMAGE_DIMENSION
        if pil_img.width > max_dim or pil_img.height > max_dim:
            pil_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        config_parts = [f"--psm {psm}"]
        if char_whitelist:
            config_parts.append(f"-c tessedit_char_whitelist={char_whitelist}")
        custom_config = " ".join(config_parts)

        # Bound concurrent execution across threads
        acquire_timeout = max(0.001, effective_deadline - time.monotonic())
        acquired = self._semaphore.acquire(timeout=acquire_timeout)
        if not acquired:
            raise OcrTimeoutError("OCR engine semaphore acquisition timed out.")

        try:
            # Check remaining budget after acquisition
            now = time.monotonic()
            if now >= effective_deadline:
                raise OcrTimeoutError(
                    "Overall OCR recognition deadline exceeded waiting for capacity."
                )
            call_timeout = max(0.05, effective_deadline - now)

            # 1. Extract detailed word data with confidences
            try:
                data: dict[str, list[Any]] = pytesseract.image_to_data(
                    pil_img,
                    lang="eng",
                    config=custom_config,
                    output_type=Output.DICT,
                    timeout=call_timeout,
                )
            except TesseractNotFoundError as err:
                raise OcrUnavailableError(
                    "Tesseract binary was not found on system PATH."
                ) from err
            except TesseractError as err:
                if _is_unavailable_error(err):
                    raise OcrUnavailableError(
                        f"Tesseract language data or engine error: {err}"
                    ) from err
                raise OcrError(f"Tesseract OCR processing failed: {err}") from err
            except Exception as err:
                if _is_timeout_error(err):
                    raise OcrTimeoutError("Tesseract OCR execution timed out.") from err
                if _is_unavailable_error(err):
                    raise OcrUnavailableError(
                        f"Tesseract binary or resource unavailable: {err}"
                    ) from err
                raise OcrError(f"Tesseract OCR processing error: {err}") from err

            words: list[OcrWord] = []
            confidences: list[float] = []

            texts = data.get("text", [])
            confs = data.get("conf", [])
            lefts = data.get("left", [])
            tops = data.get("top", [])
            widths = data.get("width", [])
            heights = data.get("height", [])

            for i, raw_w in enumerate(texts):
                w_str = str(raw_w).strip()
                if not w_str:
                    continue
                try:
                    c = float(confs[i])
                except (IndexError, ValueError, TypeError):
                    c = -1.0

                bbox = None
                if (
                    i < len(lefts)
                    and i < len(tops)
                    and i < len(widths)
                    and i < len(heights)
                ):
                    bbox = (
                        int(lefts[i]),
                        int(tops[i]),
                        int(widths[i]),
                        int(heights[i]),
                    )

                # Tesseract returns -1 when confidence is undefined
                if c >= 0.0:
                    confidences.append(c)
                    words.append(OcrWord(text=w_str, confidence=round(c, 2), bbox=bbox))
                else:
                    words.append(OcrWord(text=w_str, confidence=0.0, bbox=bbox))

            # 2. Fetch full text representation
            now = time.monotonic()
            if now >= effective_deadline:
                raise OcrTimeoutError(
                    "Overall OCR deadline exceeded before string extraction."
                )
            call_timeout = max(0.05, effective_deadline - now)

            try:
                full_text = pytesseract.image_to_string(
                    pil_img,
                    lang="eng",
                    config=custom_config,
                    timeout=call_timeout,
                ).strip()
            except TesseractNotFoundError as err:
                raise OcrUnavailableError(
                    "Tesseract binary was not found on system PATH."
                ) from err
            except TesseractError as err:
                if _is_unavailable_error(err):
                    raise OcrUnavailableError(
                        f"Tesseract language data or engine error: {err}"
                    ) from err
                raise OcrError(f"Tesseract OCR processing failed: {err}") from err
            except Exception as err:
                if _is_timeout_error(err):
                    raise OcrTimeoutError("Tesseract OCR execution timed out.") from err
                if _is_unavailable_error(err):
                    raise OcrUnavailableError(
                        f"Tesseract binary or resource unavailable: {err}"
                    ) from err
                raise OcrError(f"Tesseract OCR processing error: {err}") from err

            avg_conf = (
                round(sum(confidences) / len(confidences), 2) if confidences else 0.0
            )

            return OcrResult(
                raw_text=full_text,
                confidence=avg_conf,
                words=words,
            )

        finally:
            self._semaphore.release()


# Module-level singleton
_ocr_engine_instance: OcrEngineProtocol | None = None


def get_ocr_engine() -> OcrEngineProtocol:
    global _ocr_engine_instance
    if _ocr_engine_instance is None:
        _ocr_engine_instance = TesseractOcrEngine()
    return _ocr_engine_instance


OcrEngine = TesseractOcrEngine
