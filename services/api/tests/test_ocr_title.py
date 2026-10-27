from app.services.ocr.engine import OcrResult, OcrWord
from app.services.ocr.title import title_from_words


def test_title_follows_neighboring_words_without_absorbing_distant_label():
    words = [
        OcrWord("Battle", 95, (10, 20, 80, 20)),
        OcrWord("VIP", 90, (100, 20, 45, 20)),
        OcrWord("Pass", 90, (155, 20, 60, 20)),
        OcrWord("Noise", 80, (300, 20, 60, 20)),
    ]
    result = title_from_words(OcrResult("Battle VIP Pass Noise", 90, words))
    assert result.raw_text == "Battle VIP Pass"


def test_title_preserves_suffix_and_ignores_smaller_evolution_line():
    words = [
        OcrWord("Evolves", 95, (10, 3, 50, 8)),
        OcrWord("from", 95, (65, 3, 30, 8)),
        OcrWord("Kirlia", 95, (100, 3, 30, 8)),
        OcrWord("Gardevoir", 95, (10, 20, 100, 20)),
        OcrWord("ex", 30, (120, 22, 25, 16)),
        OcrWord("HP", 95, (220, 20, 30, 20)),
    ]
    result = title_from_words(OcrResult("", 80, words))
    assert result.raw_text == "Gardevoir ex"
