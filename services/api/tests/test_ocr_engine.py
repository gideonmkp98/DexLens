import shutil
import subprocess
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image
from pytesseract import TesseractError, TesseractNotFoundError

from app.services.ocr.engine import (
    OcrEngine,
    OcrError,
    OcrTimeoutError,
    OcrUnavailableError,
    TesseractOcrEngine,
)


def test_tesseract_engine_missing_binary_raises_unavailable():
    engine = TesseractOcrEngine(timeout_seconds=2.0)
    img = Image.fromarray(np.full((50, 100), 255, dtype=np.uint8))

    with patch(
        "pytesseract.image_to_data",
        side_effect=TesseractNotFoundError(),
    ):
        with pytest.raises(OcrUnavailableError) as exc_info:
            engine.recognize(img)
        assert "not found" in str(exc_info.value).lower()

    # Verify semaphore was released
    assert engine._semaphore._value == engine.max_concurrency


def test_tesseract_engine_missing_language_data_raises_unavailable():
    engine = TesseractOcrEngine(timeout_seconds=2.0)
    img = Image.fromarray(np.full((50, 100), 255, dtype=np.uint8))

    err_msg = (
        "Error opening data file /usr/share/tesseract-ocr/5/tessdata/eng.traineddata\n"
        "Failed loading language 'eng'"
    )
    with patch(
        "pytesseract.image_to_data",
        side_effect=TesseractError(1, err_msg),
    ):
        with pytest.raises(OcrUnavailableError) as exc_info:
            engine.recognize(img)
        assert (
            "language" in str(exc_info.value).lower()
            or "traineddata" in str(exc_info.value).lower()
        )

    # Verify semaphore was released
    assert engine._semaphore._value == engine.max_concurrency


def test_tesseract_engine_timeout_raises_ocr_timeout():
    engine = TesseractOcrEngine(timeout_seconds=1.0)
    img = Image.fromarray(np.full((50, 100), 255, dtype=np.uint8))

    with patch(
        "pytesseract.image_to_data",
        side_effect=RuntimeError("Tesseract process timeout"),
    ):
        with pytest.raises(OcrTimeoutError) as exc_info:
            engine.recognize(img)
        assert "timed out" in str(exc_info.value).lower()

    # Verify semaphore was released
    assert engine._semaphore._value == engine.max_concurrency


def test_tesseract_engine_subprocess_timeout_expired():
    engine = TesseractOcrEngine(timeout_seconds=1.0)
    img = Image.fromarray(np.full((50, 100), 255, dtype=np.uint8))

    with patch(
        "pytesseract.image_to_data",
        side_effect=subprocess.TimeoutExpired(cmd="tesseract", timeout=1.0),
    ):
        with pytest.raises(OcrTimeoutError):
            engine.recognize(img)

    assert engine._semaphore._value == engine.max_concurrency


def test_tesseract_engine_processing_crash_raises_ocr_error():
    engine = TesseractOcrEngine(timeout_seconds=2.0)
    img = Image.fromarray(np.full((50, 100), 255, dtype=np.uint8))

    with patch(
        "pytesseract.image_to_data",
        side_effect=TesseractError(139, "Segmentation fault (core dumped)"),
    ):
        with pytest.raises(OcrError) as exc_info:
            engine.recognize(img)
        assert "processing failed" in str(exc_info.value).lower()

    assert engine._semaphore._value == engine.max_concurrency


def test_tesseract_engine_overall_deadline_exceeded_before_call():
    engine = TesseractOcrEngine(timeout_seconds=5.0)
    img = Image.fromarray(np.full((50, 100), 255, dtype=np.uint8))

    # Expired deadline
    expired_deadline = time.monotonic() - 1.0

    mock_to_data = MagicMock()
    with patch("pytesseract.image_to_data", mock_to_data):
        with pytest.raises(OcrTimeoutError) as exc_info:
            engine.recognize(img, deadline=expired_deadline)
        assert "deadline exceeded" in str(exc_info.value).lower()

    # pytesseract should not even be called
    mock_to_data.assert_not_called()
    assert engine._semaphore._value == engine.max_concurrency


def test_tesseract_engine_semaphore_contention_timeout():
    # Engine with concurrency=1
    engine = TesseractOcrEngine(timeout_seconds=0.2, max_concurrency=1)
    img = Image.fromarray(np.full((50, 100), 255, dtype=np.uint8))

    # Acquire the only permit
    assert engine._semaphore.acquire(blocking=False)

    try:
        with pytest.raises(OcrTimeoutError) as exc_info:
            engine.recognize(img, timeout=0.1)
        assert "timed out" in str(exc_info.value).lower()
    finally:
        engine._semaphore.release()

    assert engine._semaphore._value == 1


@pytest.mark.skipif(
    not shutil.which("tesseract"), reason="Tesseract not installed on PATH"
)
def test_tesseract_engine_real_smoke_test():
    """Real local OCR execution smoke test verifying actual tesseract outputs."""
    import cv2

    engine = OcrEngine(timeout_seconds=5.0)

    # Create an image with clean high-contrast text "PIKACHU 58"
    img_bgr = np.full((120, 400, 3), 255, dtype=np.uint8)
    cv2.putText(
        img_bgr,
        "PIKACHU 58",
        (20, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        2.0,
        (0, 0, 0),
        4,
    )

    result = engine.recognize(img_bgr, psm=6)
    assert "PIKACHU" in result.raw_text.upper()
    assert "58" in result.raw_text
    assert result.confidence > 50.0
    assert len(result.words) >= 2
    assert any("PIKACHU" in w.text.upper() for w in result.words)
