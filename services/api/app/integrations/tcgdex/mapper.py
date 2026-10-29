import dataclasses
from typing import Any

from tcgdexsdk import Card, CardResume, Set, SetResume
from tcgdexsdk.enums import Extension, Quality


def _strip_sdk(data: Any) -> Any:
    """Recursively strip the 'sdk' attribute injected by the TCGdex SDK."""
    if dataclasses.is_dataclass(data):
        data = dataclasses.asdict(data)
    if isinstance(data, dict):
        return {k: _strip_sdk(v) for k, v in data.items() if k != "sdk"}
    if isinstance(data, list):
        return [_strip_sdk(item) for item in data]
    return data


def derive_image_urls(
    base_url_or_obj: Any,
) -> tuple[str | None, str | None]:
    """Derive low-quality and high-quality WebP image URLs using SDK image helpers.

    Supports Card or CardResume instances, or raw base image URL strings.
    """
    if not base_url_or_obj:
        return None, None

    if isinstance(base_url_or_obj, (Card, CardResume)):
        return (
            base_url_or_obj.get_image_url(Quality.LOW, Extension.WEBP),
            base_url_or_obj.get_image_url(Quality.HIGH, Extension.WEBP),
        )

    if isinstance(base_url_or_obj, str):
        clean = base_url_or_obj.rstrip("/")
        if clean.endswith("/low.webp") or clean.endswith("/high.webp"):
            clean = clean.rsplit("/", 1)[0]
        resume = CardResume(id="", localId="", name="", image=clean)
        return (
            resume.get_image_url(Quality.LOW, Extension.WEBP),
            resume.get_image_url(Quality.HIGH, Extension.WEBP),
        )

    return None, None


def is_digital_set(set_data: Any) -> bool:
    """Determine whether a set is a digital-only product (e.g., Pokémon TCG Pocket).

    Digital products are identified by:
    1. Series ID equals 'tcgp' or series name contains 'pocket'
    2. Logo or symbol URL path containing '/tcgp/'
    3. Set ID or name containing 'pocket'
    """
    if isinstance(set_data, (Set, SetResume)):
        serie = getattr(set_data, "serie", None)
        if serie:
            serie_id = str(getattr(serie, "id", "")).lower()
            serie_name = str(getattr(serie, "name", "")).lower()
            if serie_id == "tcgp" or "pocket" in serie_name:
                return True

        logo = str(getattr(set_data, "logo", "") or "").lower()
        symbol = str(getattr(set_data, "symbol", "") or "").lower()
        if "/tcgp/" in logo or "/tcgp/" in symbol:
            return True

        set_id = str(getattr(set_data, "id", "") or "").lower()
        if set_id.startswith("tcgp") or "pocket" in set_id:
            return True

        set_name = str(getattr(set_data, "name", "") or "").lower()
        if "pocket" in set_name:
            return True

        return False

    if isinstance(set_data, dict):
        serie = set_data.get("serie")
        if isinstance(serie, dict):
            serie_id = str(serie.get("id", "")).lower()
            serie_name = str(serie.get("name", "")).lower()
            if serie_id == "tcgp" or "pocket" in serie_name:
                return True

        logo = str(set_data.get("logo", "")).lower()
        symbol = str(set_data.get("symbol", "")).lower()
        if "/tcgp/" in logo or "/tcgp/" in symbol:
            return True

        set_id = str(set_data.get("id", "")).lower()
        if set_id.startswith("tcgp") or "pocket" in set_id:
            return True

        set_name = str(set_data.get("name", "")).lower()
        if "pocket" in set_name:
            return True

    return False


def is_digital_card(card_data: Any) -> bool:
    """Determine whether a card belongs to a digital-only product."""
    if isinstance(card_data, (Card, CardResume)):
        card_id = str(getattr(card_data, "id", "") or "").lower()
        if card_id.startswith("tcgp") or "pocket" in card_id:
            return True

        image = str(getattr(card_data, "image", "") or "").lower()
        if "/tcgp/" in image:
            return True

        set_obj = getattr(card_data, "set", None)
        if set_obj is not None and is_digital_set(set_obj):
            return True

        return False

    if isinstance(card_data, dict):
        card_id = str(card_data.get("id", "")).lower()
        if card_id.startswith("tcgp") or "pocket" in card_id:
            return True

        image = str(card_data.get("image", "")).lower()
        if "/tcgp/" in image:
            return True

        set_obj = card_data.get("set")
        if isinstance(set_obj, dict):
            if is_digital_set(set_obj):
                return True

    return False


def map_tcgdex_card(card: Any) -> dict[str, Any]:
    """Map a TCGdex SDK Card instance or dict into the application card model."""
    if isinstance(card, dict):
        return card

    return _strip_sdk(card)


def map_tcgdex_card_resume(resume: Any) -> dict[str, Any]:
    """Map a TCGdex SDK CardResume instance or dict into card summary dictionary."""
    if isinstance(resume, dict):
        return resume

    if isinstance(resume, CardResume):
        return {
            "id": resume.id,
            "localId": resume.localId,
            "name": resume.name,
            "image": resume.image,
        }

    return _strip_sdk(resume)


def map_tcgdex_set(set_obj: Any) -> dict[str, Any]:
    """Map a TCGdex SDK Set instance or dict into the application set model."""
    if isinstance(set_obj, dict):
        return set_obj

    return _strip_sdk(set_obj)


def map_tcgdex_set_resume(resume: Any) -> dict[str, Any]:
    """Map a TCGdex SDK SetResume instance or dict into set summary dictionary."""
    if isinstance(resume, dict):
        return resume

    if isinstance(resume, SetResume):
        card_count = None
        if resume.cardCount is not None:
            card_count = {
                "total": resume.cardCount.total,
                "official": resume.cardCount.official,
            }
        return {
            "id": resume.id,
            "name": resume.name,
            "logo": resume.logo,
            "symbol": resume.symbol,
            "cardCount": card_count,
        }

    return _strip_sdk(resume)
