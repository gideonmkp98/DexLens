import re

PRINTED_SET_CODE_TO_PROVIDER_ID: dict[str, str] = {
    # Scarlet & Violet era
    "SVI": "sv01",
    "PAL": "sv02",
    "OBF": "sv03",
    "MEW": "sv03.5",
    "PAR": "sv04",
    "PAF": "sv04.5",
    "TEF": "sv05",
    "TWM": "sv06",
    "SFA": "sv06.5",
    "SCR": "sv07",
    "SSP": "sv08",
    "PRE": "sv08.5",
    "SVP": "svp",
    # Sword & Shield era
    "SSH": "swsh1",
    "RCL": "swsh2",
    "DAA": "swsh3",
    "CPA": "swsh3.5",
    "VIV": "swsh4",
    "SHF": "swsh4.5",
    "BST": "swsh5",
    "CRE": "swsh6",
    "EVS": "swsh7",
    "CEL": "cel25",
    "FST": "swsh8",
    "BRS": "swsh9",
    "ASR": "swsh10",
    "PGO": "swsh10.5",
    "LOR": "swsh11",
    "SIT": "swsh12",
    "CRZ": "swsh12.5",
    "SWSH": "swshp",
    # Sun & Moon era
    "SUM": "sm1",
    "GRI": "sm2",
    "BUS": "sm3",
    "CIN": "sm4",
    "UPR": "sm5",
    "FLI": "sm6",
    "CES": "sm7",
    "DRM": "sm7.5",
    "LOT": "sm8",
    "TEU": "sm9",
    "DET": "det1",
    "UNB": "sm10",
    "UNM": "sm11",
    "HIF": "sm115",
    "CEC": "sm12",
    "SMP": "smp",
    # XY era
    "XY": "xy1",
    "FLF": "xy2",
    "FFI": "xy3",
    "PHF": "xy4",
    "PRC": "xy5",
    "DCR": "dc1",
    "ROS": "xy6",
    "AOR": "xy7",
    "BKT": "xy8",
    "BKP": "xy9",
    "GEN": "g1",
    "FCO": "xy10",
    "STS": "xy11",
    "EVO": "xy12",
    "XYP": "xyp",
    # Classic / Base Era
    "BASE": "base1",
    "BS": "base1",
    "JU": "base2",
    "FO": "base3",
    "TR": "base5",
    "G1": "gym1",
    "G2": "gym2",
    "N1": "neo1",
    "N2": "neo2",
    "N3": "neo3",
    "N4": "neo4",
}


def resolve_printed_set_code(code: str | None) -> str | None:
    """Map a printed 2-4 letter set code to its canonical TCGdex provider set ID.

    Returns the mapped provider set ID if known, or None if unresolvable.
    """
    if not code:
        return None
    clean = re.sub(r"[^A-Za-z0-9]", "", code).upper()
    return PRINTED_SET_CODE_TO_PROVIDER_ID.get(clean)
