"""OCR service module for card text extraction, preprocessing, and normalization."""

from app.services.ocr.engine import (
    OcrEngine,
    OcrEngineProtocol,
    OcrError,
    OcrResult,
    OcrTimeoutError,
    OcrUnavailableError,
    get_ocr_engine,
)
from app.services.ocr.normalizer import (
    CardExtractionResult,
    extract_abilities,
    extract_attacks,
    extract_attacks_and_abilities,
    extract_card_info,
    normalize_card_name,
    normalize_collector_number,
    normalize_hp,
)
from app.services.ocr.preprocessor import CardRegions, prepare_card_regions

__all__ = [
    "CardExtractionResult",
    "CardRegions",
    "OcrEngine",
    "OcrEngineProtocol",
    "OcrError",
    "OcrResult",
    "OcrTimeoutError",
    "OcrUnavailableError",
    "extract_abilities",
    "extract_attacks",
    "extract_attacks_and_abilities",
    "extract_card_info",
    "get_ocr_engine",
    "normalize_card_name",
    "normalize_collector_number",
    "normalize_hp",
    "prepare_card_regions",
]
