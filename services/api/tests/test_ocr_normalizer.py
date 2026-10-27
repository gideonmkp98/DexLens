from app.services.ocr.engine import OcrResult
from app.services.ocr.normalizer import (
    extract_abilities,
    extract_attacks,
    extract_attacks_and_abilities,
    extract_card_info,
    normalize_card_name,
    normalize_collector_number,
    normalize_hp,
)


def test_normalize_numeric_collector_numbers():
    res1 = normalize_collector_number("058/102")
    assert res1 is not None
    assert res1.local_id == "058"
    assert res1.denominator == "102"
    assert res1.full_formatted == "058/102"
    assert "58" in res1.alternatives
    assert "58/102" in res1.alternatives

    res2 = normalize_collector_number("12/64")
    assert res2 is not None
    assert res2.local_id == "12"
    assert res2.denominator == "64"
    assert res2.full_formatted == "12/64"


def test_normalize_standalone_numeric_collector_numbers():
    # Standalone '58'
    res_58 = normalize_collector_number("58")
    assert res_58 is not None
    assert res_58.local_id == "58"
    assert res_58.denominator is None
    assert "58" in res_58.alternatives

    # Standalone '058' preserves leading zero and provides stripped alternative
    res_058 = normalize_collector_number("058")
    assert res_058 is not None
    assert res_058.local_id == "058"
    assert res_058.denominator is None
    assert "58" in res_058.alternatives
    assert "058" in res_058.alternatives


def test_normalize_secret_rares():
    # Numerator greater than denominator is valid for secret rares
    res = normalize_collector_number("199/165")
    assert res is not None
    assert res.local_id == "199"
    assert res.denominator == "165"
    assert res.full_formatted == "199/165"


def test_normalize_trainer_gallery_and_galarian_gallery():
    res_tg = normalize_collector_number("TG01/TG30")
    assert res_tg is not None
    assert res_tg.local_id == "TG01"
    assert res_tg.denominator == "TG30"
    assert res_tg.full_formatted == "TG01/TG30"

    res_gg = normalize_collector_number("GG01/GG70")
    assert res_gg is not None
    assert res_gg.local_id == "GG01"
    assert res_gg.denominator == "GG70"

    res_standalone_tg = normalize_collector_number("TG12")
    assert res_standalone_tg is not None
    assert res_standalone_tg.local_id == "TG12"


def test_normalize_promo_identifiers():
    res_svp = normalize_collector_number("SVP 001")
    assert res_svp is not None
    assert res_svp.local_id == "SVP 001"
    assert "SVP001" in res_svp.alternatives
    assert "SVP 1" in res_svp.alternatives

    res_swsh = normalize_collector_number("SWSH050")
    assert res_swsh is not None
    assert res_swsh.local_id == "SWSH 050"


def test_disambiguate_ambiguous_characters():
    # O instead of 0
    res_o = normalize_collector_number("1O5/165")
    assert res_o is not None
    assert res_o.local_id == "105"

    # l instead of 1
    res_l = normalize_collector_number("058/l02")
    assert res_l is not None
    assert res_l.denominator == "102"


def test_filter_false_positives():
    # HP text should not be a collector number
    assert normalize_collector_number("HP 120") is None
    assert normalize_collector_number("120 HP") is None

    # Attack damage should not be a collector number
    assert normalize_collector_number("30+") is None
    assert normalize_collector_number("120x") is None

    # Copyright years should not be a collector number
    assert normalize_collector_number("© 2023 Pokémon") is None
    assert normalize_collector_number("1995-2022") is None


def test_reject_non_numeric_slash_patterns():
    # 'thoes/ie' from low-res Steelix crop must NOT become a collector number
    assert normalize_collector_number("bpsteg thoes / ie |e i") is None
    assert normalize_collector_number("thoes/ie") is None
    assert normalize_collector_number("abc/def") is None
    assert normalize_collector_number("retreat/cost") is None


def test_reject_modifier_prefixed_and_retreat_numbers():
    # Retreat cost noise 'x 3' from Gastly crop must NOT become a collector number
    assert normalize_collector_number("er Re te x 3") is None
    assert normalize_collector_number("weakness @x2") is None
    assert normalize_collector_number("resistance -20") is None
    assert normalize_collector_number("retreat cost 3") is None
    assert normalize_collector_number("No. 092 Gastly") is None


def test_evidence_strength_classification():
    # Slash denominator format: strong
    res_slash = normalize_collector_number("60/64")
    assert res_slash is not None
    assert res_slash.strength == "strong"

    # Promo format: strong
    res_promo = normalize_collector_number("SVP 001")
    assert res_promo is not None
    assert res_promo.strength == "strong"

    # Multi-digit standalone number: moderate
    res_multi = normalize_collector_number("58")
    assert res_multi is not None
    assert res_multi.strength == "moderate"

    # Clean single-digit standalone number: weak
    res_single = normalize_collector_number("4")
    assert res_single is not None
    assert res_single.strength == "weak"


def test_generate_name_hypotheses():
    from app.services.ocr.normalizer import generate_name_hypotheses

    # Gastly with trailing noise
    hyps_gastly = generate_name_hypotheses("Gastly se")
    assert hyps_gastly[0] == "Gastly"
    assert "Gastly se" in hyps_gastly

    # Steelix with noise prefix, noise suffix, and stray digit
    hyps_steelix = generate_name_hypotheses("ad Steelix eee 4")
    assert hyps_steelix[0] == "Steelix"

    # Suffix cards produce base species as alternative
    hyps_charizard = generate_name_hypotheses("Charizard ex")
    assert hyps_charizard[0] == "Charizard ex"
    assert "Charizard" in hyps_charizard

    # Multiword trainer/energy cards preserved
    hyps_trainer = generate_name_hypotheses("Professor Research")
    assert hyps_trainer[0] == "Professor Research"

    hyps_energy = generate_name_hypotheses("Double Colorless Energy")
    assert hyps_energy[0] == "Double Colorless Energy"


def test_normalize_card_name():
    # Strips trailing HP
    assert normalize_card_name("Pikachu HP 60") == "Pikachu"
    assert normalize_card_name("120 HP Mewtwo") == "Mewtwo"

    # Preserves suffixes
    assert normalize_card_name("Charizard ex") == "Charizard ex"
    assert normalize_card_name("Mewtwo EX") == "Mewtwo EX"
    assert normalize_card_name("Rayquaza VMAX") == "Rayquaza VMAX"
    assert normalize_card_name("Giratina VSTAR") == "Giratina VSTAR"

    # Handles noise characters
    assert normalize_card_name("| Pikachu |") == "Pikachu"

    # Strips stage & evolution header lines
    stage_text = (
        "STAGE 1 Evolves from Charmeleon Put Charizard on the Stage 1 card\n"
        "Charizard 120 HP"
    )
    assert normalize_card_name(stage_text) == "Charizard"
    assert normalize_card_name("Basic Weedle HP 40") == "Weedle"
    assert normalize_card_name("Basic Pokémon\nPikachu 60 HP") == "Pikachu"

    # Empty text
    assert normalize_card_name("") is None
    assert normalize_card_name("   ") is None


def test_extract_card_info_integration():
    header = OcrResult(raw_text="Charizard ex HP 330", confidence=92.5)
    footer = OcrResult(raw_text="MEW 199/165 ©2023 Pokemon", confidence=88.0)

    extracted = extract_card_info(header, footer)
    assert extracted.name == "Charizard ex"
    assert extracted.hp == "330"
    assert extracted.number == "199/165"
    assert extracted.local_id == "199"
    assert extracted.printed_denominator == "165"
    assert extracted.set_code == "MEW"
    assert extracted.confidence > 80.0
    assert extracted.source_regions.get("hp") == "header"


def test_normalize_hp_explicit_and_fuzzy():
    # Explicit HP patterns
    assert normalize_hp("190 HP") == "190"
    assert normalize_hp("HP 120") == "120"
    assert normalize_hp("Pikachu HP 60") == "60"
    assert normalize_hp("330 HP") == "330"
    assert normalize_hp("HP30") == "30"

    # Fuzzy OCR typos
    assert normalize_hp("Charizard 120 HE") == "120"
    assert normalize_hp("Pikachu 50 HPD") == "50"
    assert normalize_hp("Mewtwo 120 HB") == "120"

    # Multiple of 10 in header ROI
    assert normalize_hp("2 Steelix te 190 (ee)") == "190"
    assert normalize_hp("Alakazam 100") == "100"


def test_normalize_hp_rejects_non_hp_numbers():
    # Never hallucinate non-HP context numbers
    assert normalize_hp("STAGE 2") is None
    assert normalize_hp("STAGE 1") is None
    assert normalize_hp("LV.14 #25") is None
    assert normalize_hp("No. 092 Gastly") is None
    assert normalize_hp("60/64") is None
    assert normalize_hp("©1999 Wizards") is None
    assert normalize_hp("Basic Pokémon Pikachu") is None
    assert normalize_hp("") is None
    assert normalize_hp("   ") is None


def test_extract_attacks_with_damage_modifiers():
    body_text = (
        "© Surprise Attack 30\n"
        "Flip a coin. If tails, this attack does nothing.\n"
        "Hydro Pump 60+\n"
        "Does 20 more damage for each Water Energy.\n"
        "Quick Attack 10x\n"
        "Flip 2 coins."
    )
    attacks, abilities = extract_attacks_and_abilities(body_text)
    assert "Surprise Attack" in attacks
    assert "Hydro Pump" in attacks
    assert "Quick Attack" in attacks
    assert abilities == []


def test_extract_attacks_with_following_rules_and_symbols():
    body_text = (
        "Flame Pokémon. Length: 5' 7\", Weight: 200 Ibs.\n"
        "() @ Fire Spin Discard 2 Energy cards\n"
        "attached to Charizard in order to use 100\n"
        "this attack.\n"
        "weakness resistance retreat cost"
    )
    attacks = extract_attacks(body_text)
    assert attacks == ["Fire Spin"]


def test_extract_abilities_modern_and_vintage():
    # Modern inline
    modern = (
        "Ability: Quick Search\n"
        "Once during your turn, you may search your deck for a card."
    )
    assert extract_abilities(modern) == ["Quick Search"]

    # Modern multiline
    multiline = (
        "Ability\n"
        "Quick Search\n"
        "Once during your turn, you may search your deck for a card."
    )
    assert extract_abilities(multiline) == ["Quick Search"]

    # Vintage Pokémon Power
    vintage_power = (
        "Pokémon Power: Energy Burn As often as you like during your turn "
        "(before your attack)...\n"
        "() @ Fire Spin 100"
    )
    at, ab = extract_attacks_and_abilities(vintage_power)
    assert ab == ["Energy Burn"]
    assert at == ["Fire Spin"]

    # Poké-Power / Poké-Body
    poke_body = "Poké-Body: Thick Fat Any damage done to Snorlax by attacks..."
    assert extract_abilities(poke_body) == ["Thick Fat"]


def test_extract_card_info_with_structured_evidence():
    header = OcrResult(raw_text="Steelix", confidence=88.0)
    footer = OcrResult(raw_text="8/100", confidence=82.0)
    body = OcrResult(
        raw_text=(
            "** Powerful Rage 20\n22+ Earthquake 180\nweakness resistance retreat cost"
        ),
        confidence=85.0,
    )
    hp_roi = OcrResult(raw_text="190 HP", confidence=90.0)

    res = extract_card_info(
        header_ocr=header,
        footer_ocr=footer,
        body_ocr=body,
        hp_ocr=hp_roi,
    )
    assert res.name == "Steelix"
    assert res.hp == "190"
    assert res.number == "8/100"
    assert res.attacks == ["Powerful Rage", "Earthquake"]
    assert res.abilities == []
    assert res.source_regions["hp"] == "hp_roi"
    assert res.source_regions["attacks"] == "body"
    assert "[Body]:" in res.raw_text
    assert "[HP]:" in res.raw_text
