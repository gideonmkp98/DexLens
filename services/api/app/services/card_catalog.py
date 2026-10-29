from typing import Any

from app.integrations.tcgdex.provider import TCGdexProvider


class CardCatalogService:
    """Domain service layer isolating application features from external
    TCGdex SDK details.
    """

    def __init__(self, provider: TCGdexProvider | None = None) -> None:
        self.provider = provider or TCGdexProvider()

    @property
    def base_url(self) -> str:
        return self.provider.base_url

    async def get_card(
        self, card_id: str, language: str = "en"
    ) -> dict[str, Any] | None:
        """Fetch card details through provider."""
        return await self.provider.get_card(card_id, language=language)

    async def search_cards(
        self,
        name: str | None = None,
        local_id: str | None = None,
        page: int | None = 1,
        page_size: int = 24,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Search card summaries through provider."""
        return await self.provider.search_cards(
            name=name,
            local_id=local_id,
            page=page,
            page_size=page_size,
            language=language,
        )

    async def get_cards_search(
        self,
        name: str | None = None,
        local_id: str | None = None,
        page: int | None = 1,
        page_size: int = 24,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Backward-compatible alias for search_cards."""
        return await self.search_cards(
            name=name,
            local_id=local_id,
            page=page,
            page_size=page_size,
            language=language,
        )

    async def get_set(
        self, set_id: str, language: str = "en"
    ) -> dict[str, Any] | None:
        """Fetch set details through provider."""
        return await self.provider.get_set(set_id, language=language)

    async def get_sets(self, language: str = "en") -> list[dict[str, Any]]:
        """Fetch all set summaries through provider."""
        return await self.provider.get_sets(language=language)

    def get_card_image_url(
        self,
        card: Any,
        quality: str = "high",
        extension: str = "webp",
    ) -> str | None:
        """Derive image URL for card."""
        return self.provider.get_card_image_url(
            card, quality=quality, extension=extension
        )


_card_catalog_service = CardCatalogService()


def get_card_catalog_service() -> CardCatalogService:
    """Dependency provider for FastAPI routes."""
    return _card_catalog_service
