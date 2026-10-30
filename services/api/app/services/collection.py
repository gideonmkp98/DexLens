import logging
import time
import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models.card import Card
from app.models.collection import CollectionItem, CollectionScanLink
from app.models.scan import Scan
from app.schemas.collection import (
    ALLOWED_CONDITIONS,
    AddFromScanRequest,
    CollectionCreateRequest,
    CollectionItemResponse,
    CollectionSetDistributionItem,
    CollectionStatsResponse,
    CollectionUpdateRequest,
)
from app.services.card_catalog import CardCatalogService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CollectionError(Exception):
    """Base domain exception for personal collection operations."""

    pass


class CollectionItemNotFoundError(CollectionError):
    """Raised when an operation targets a non-existent collection item."""

    pass


class ConcurrencyConflictError(CollectionError):
    """Raised when optimistic concurrency check fails on an update."""

    def __init__(
        self,
        message: str = "Item version conflict",
        current_version: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.current_version = current_version


class InvalidScanStateError(CollectionError):
    """Raised when an invalid or unconfirmed scan cannot be added to the collection."""

    def __init__(self, message: str, code: str = "INVALID_SCAN_STATE") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class CollectionService:
    """Domain service for managing personal Pokémon card collections."""

    def __init__(
        self,
        db: "Session | AsyncSession",
        catalog_service: CardCatalogService | None = None,
    ) -> None:
        # Runtime session is SQLAlchemy Session
        self.db: Session = db  # type: ignore[assignment]
        self.catalog_service = catalog_service

    async def list_items(
        self,
        query: str | None = None,
        set_id: str | None = None,
        condition: str | None = None,
        language: str | None = None,
        variant: str | None = None,
        sort: str = "recent",
        page: int = 1,
        page_size: int = 24,
    ) -> tuple[list[CollectionItem], int, bool]:
        """Query and filter personal collection items with sorting and pagination.

        Supported sorts:
        - recent: created_at DESC
        - name_asc: card_name ASC, collector_number ASC
        - name_desc: card_name DESC, collector_number ASC
        - set_asc: set_id ASC, collector_number ASC
        - number_asc: collector_number ASC, created_at DESC
        - quantity_desc: quantity DESC, created_at DESC
        """
        filters: list[Any] = []

        if query and query.strip():
            clean_q = f"%{query.strip()}%"
            filters.append(
                or_(
                    CollectionItem.card_name.ilike(clean_q),
                    CollectionItem.collector_number.ilike(clean_q),
                    CollectionItem.set_name.ilike(clean_q),
                    CollectionItem.notes.ilike(clean_q),
                )
            )

        if set_id and set_id.strip():
            filters.append(CollectionItem.set_id == set_id.strip())

        if condition and condition.strip():
            filters.append(CollectionItem.condition == condition.strip())

        if language and language.strip():
            filters.append(CollectionItem.language == language.strip().lower())

        if variant and variant.strip():
            filters.append(CollectionItem.variant == variant.strip().lower())

        # Determine ordering
        order_clauses: list[Any] = []
        if sort == "name_asc":
            order_clauses = [
                CollectionItem.card_name.asc(),
                CollectionItem.collector_number.asc(),
            ]
        elif sort == "name_desc":
            order_clauses = [
                CollectionItem.card_name.desc(),
                CollectionItem.collector_number.asc(),
            ]
        elif sort == "set_asc":
            order_clauses = [
                CollectionItem.set_id.asc(),
                CollectionItem.collector_number.asc(),
            ]
        elif sort == "number_asc":
            order_clauses = [
                CollectionItem.collector_number.asc(),
                CollectionItem.created_at.desc(),
            ]
        elif sort == "quantity_desc":
            order_clauses = [
                CollectionItem.quantity.desc(),
                CollectionItem.created_at.desc(),
            ]
        else:  # default "recent"
            order_clauses = [
                CollectionItem.created_at.desc(),
                CollectionItem.id.desc(),
            ]

        # Count total matching records
        count_stmt = select(func.count(CollectionItem.id)).where(*filters)
        total_count = self.db.execute(count_stmt).scalar() or 0

        # Query paginated page
        offset = max(0, (page - 1) * page_size)
        items_stmt = (
            select(CollectionItem)
            .where(*filters)
            .order_by(*order_clauses)
            .offset(offset)
            .limit(page_size)
        )
        items = list(self.db.execute(items_stmt).scalars().all())
        has_more = (offset + len(items)) < total_count

        return items, total_count, has_more

    async def get_item(self, entry_id: str) -> CollectionItem | None:
        """Fetch a single collection item by primary key."""
        return (
            self.db.query(CollectionItem).filter(CollectionItem.id == entry_id).first()
        )

    async def get_item_for_scan(self, scan_id: str) -> CollectionItem | None:
        """Return the grouped collection item already linked to a physical scan."""
        return (
            self.db.query(CollectionItem)
            .join(
                CollectionScanLink,
                CollectionScanLink.collection_item_id == CollectionItem.id,
            )
            .filter(CollectionScanLink.scan_id == scan_id)
            .first()
        )

    def _find_merge_target(
        self,
        *,
        card_id: str,
        provider: str = "tcgdex",
        language: str = "en",
        variant: str = "normal",
        condition: str = "near_mint",
    ) -> CollectionItem | None:
        """Find an equivalent grouped inventory row matching grouping identity."""
        query = self.db.query(CollectionItem).filter(
            CollectionItem.card_id == card_id,
            CollectionItem.provider == provider,
            CollectionItem.language == language,
            CollectionItem.variant == variant,
            CollectionItem.condition == condition,
        )
        return query.with_for_update().order_by(CollectionItem.created_at.asc()).first()

    async def create_item(self, data: CollectionCreateRequest) -> CollectionItem:
        """Create a new collection item, looking up missing snapshot data if needed."""
        card_name = data.card_name
        set_id = data.set_id
        set_name = data.set_name
        collector_number = data.collector_number
        card_image_url = data.card_image_url

        # Check local DB if any snapshot fields are missing
        if not (card_name and set_id and set_name and collector_number):
            local_card = (
                self.db.query(Card).filter(Card.external_id == data.card_id).first()
            )
            if local_card:
                card_name = card_name or local_card.name
                collector_number = collector_number or local_card.local_id
                if not card_image_url and local_card.image_base_url:
                    card_image_url = f"{local_card.image_base_url}/high.webp"
                if local_card.set:
                    set_id = set_id or local_card.set.external_id
                    set_name = set_name or local_card.set.name

        # If still missing and catalog service is available, query catalog
        if (
            not (card_name and set_id and set_name and collector_number)
            and self.catalog_service is not None
        ):
            try:
                card_data = await self.catalog_service.get_card(
                    data.card_id, language=data.language
                )
                if card_data and isinstance(card_data, dict):
                    card_name = card_name or card_data.get("name")
                    collector_number = collector_number or str(
                        card_data.get("localId", "")
                    )
                    raw_img = card_data.get("image")
                    if not card_image_url and raw_img:
                        card_image_url = f"{raw_img}/high.webp"
                    set_obj = card_data.get("set", {})
                    if isinstance(set_obj, dict):
                        set_id = set_id or set_obj.get("id")
                        set_name = set_name or set_obj.get("name")
            except Exception as e:
                logger.warning(
                    "Failed to fetch catalog card for snapshot: %s (%s)",
                    data.card_id,
                    e,
                )

        # Resilient fallbacks to guarantee non-null snapshot columns
        card_name = card_name or data.card_id
        if not set_id:
            set_id = data.card_id.split("-")[0] if "-" in data.card_id else "unknown"
        set_name = set_name or set_id.replace("-", " ").title()
        collector_number = collector_number or (
            data.card_id.split("-")[1] if "-" in data.card_id else "1"
        )

        acquired_at = data.acquired_at or date.today()
        provider = data.provider or "tcgdex"
        existing_item = self._find_merge_target(
            card_id=data.card_id,
            provider=provider,
            language=data.language,
            variant=data.variant,
            condition=data.condition,
        )
        if existing_item is not None:
            existing_item.quantity += data.quantity
            existing_item.version += 1
            existing_item.updated_at = datetime.now(UTC).replace(tzinfo=None)
            if existing_item.notes is None and data.notes:
                existing_item.notes = data.notes
            if existing_item.purchase_price is None and data.purchase_price:
                existing_item.purchase_price = data.purchase_price
                existing_item.currency = data.currency
            self.db.commit()
            self.db.refresh(existing_item)
            return existing_item

        item = CollectionItem(
            id=str(uuid.uuid4()),
            card_id=data.card_id,
            provider=provider,
            card_name=card_name,
            set_id=set_id,
            set_name=set_name,
            collector_number=collector_number,
            card_image_url=card_image_url,
            quantity=data.quantity,
            language=data.language,
            variant=data.variant,
            condition=data.condition,
            notes=data.notes,
            purchase_price=data.purchase_price,
            currency=data.currency,
            acquired_at=acquired_at,
            source_scan_id=data.source_scan_id,
            version=1,
        )

        try:
            self.db.add(item)
            self.db.commit()
            self.db.refresh(item)
            return item
        except (IntegrityError, OperationalError):
            self.db.rollback()
            # Concurrent insert collision or lock contention on grouping constraint
            for _ in range(5):
                winner = self._find_merge_target(
                    card_id=data.card_id,
                    provider=provider,
                    language=data.language,
                    variant=data.variant,
                    condition=data.condition,
                )
                if winner is not None:
                    winner.quantity += data.quantity
                    winner.version += 1
                    winner.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    if winner.notes is None and data.notes:
                        winner.notes = data.notes
                    if winner.purchase_price is None and data.purchase_price:
                        winner.purchase_price = data.purchase_price
                        winner.currency = data.currency
                    self.db.commit()
                    self.db.refresh(winner)
                    return winner
                time.sleep(0.05)
            raise

    async def update_item(
        self, entry_id: str, data: CollectionUpdateRequest
    ) -> CollectionItem:
        """Update an item with database-atomic optimistic concurrency."""
        update_values: dict[str, Any] = {}

        if data.quantity is not None:
            if data.quantity < 1:
                raise ValueError("Quantity must be at least 1.")
            update_values["quantity"] = data.quantity

        if data.condition is not None:
            update_values["condition"] = data.condition

        if data.variant is not None:
            update_values["variant"] = data.variant

        if data.notes is not None:
            update_values["notes"] = data.notes

        if data.purchase_price is not None:
            if data.purchase_price < 0:
                raise ValueError("Purchase price cannot be negative.")
            update_values["purchase_price"] = data.purchase_price

        if data.currency is not None:
            update_values["currency"] = data.currency

        if data.acquired_at is not None:
            update_values["acquired_at"] = data.acquired_at

        # Database-atomic conditional update on primary key and expected version
        stmt = (
            sa_update(CollectionItem)
            .where(
                CollectionItem.id == entry_id,
                CollectionItem.version == data.expected_version,
            )
            .values(
                **update_values,
                version=CollectionItem.version + 1,
                updated_at=func.now(),
            )
        )
        try:
            result = self.db.execute(stmt)
        except IntegrityError as exc:
            self.db.rollback()
            raise ConcurrencyConflictError(
                "Cannot change attributes to match an existing grouped card.",
                current_version=None,
            ) from exc

        if result.rowcount == 0:
            # Distinguish missing item (404) from stale version (409)
            existing = (
                self.db.query(CollectionItem.version)
                .filter(CollectionItem.id == entry_id)
                .first()
            )
            if existing is None:
                raise CollectionItemNotFoundError(
                    f"Collection item '{entry_id}' not found."
                )
            raise ConcurrencyConflictError(
                f"Stale version: expected {data.expected_version}, "
                f"but current version is {existing.version}.",
                current_version=existing.version,
            )

        self.db.commit()
        updated_item = await self.get_item(entry_id)
        if updated_item is None:
            raise CollectionItemNotFoundError(
                f"Collection item '{entry_id}' not found."
            )
        return updated_item

    async def delete_item(self, entry_id: str) -> bool:
        """Delete a collection item by primary key."""
        item = await self.get_item(entry_id)
        if item is None:
            return False

        self.db.delete(item)
        self.db.commit()
        return True

    async def get_stats(self) -> CollectionStatsResponse:
        """Compute aggregated collection analytics efficiently in minimal queries."""
        # 1. Main totals in a single query
        agg_stmt = select(
            func.coalesce(func.sum(CollectionItem.quantity), 0).label("total_cards"),
            func.count(CollectionItem.id).label("unique_cards"),
            func.count(func.distinct(CollectionItem.set_id)).label("total_sets"),
            func.coalesce(
                func.sum(
                    case(
                        (CollectionItem.quantity > 1, CollectionItem.quantity - 1),
                        else_=0,
                    )
                ),
                0,
            ).label("duplicate_count"),
        )
        agg_row = self.db.execute(agg_stmt).one()
        total_cards = int(agg_row.total_cards)
        unique_cards = int(agg_row.unique_cards)
        total_sets = int(agg_row.total_sets)
        duplicate_count = int(agg_row.duplicate_count)

        # 2. Condition distribution (total physical cards per condition)
        cond_stmt = select(
            CollectionItem.condition,
            func.coalesce(func.sum(CollectionItem.quantity), 0).label("card_count"),
        ).group_by(CollectionItem.condition)
        cond_rows = self.db.execute(cond_stmt).all()

        condition_distribution: dict[str, int] = dict.fromkeys(ALLOWED_CONDITIONS, 0)
        for cond_name, count in cond_rows:
            condition_distribution[cond_name] = int(count)

        # 3. Top set distribution (unique grouped cards and total physical cards)
        set_stmt = (
            select(
                CollectionItem.set_id,
                CollectionItem.set_name,
                func.count(CollectionItem.id).label("unique_cards"),
                func.coalesce(func.sum(CollectionItem.quantity), 0).label(
                    "total_cards"
                ),
            )
            .group_by(CollectionItem.set_id, CollectionItem.set_name)
            .order_by(func.sum(CollectionItem.quantity).desc())
            .limit(10)
        )
        set_rows = self.db.execute(set_stmt).all()
        set_distribution = [
            CollectionSetDistributionItem(
                set_id=s_id,
                set_name=s_name,
                count=int(u_count),
                total_cards=int(t_cards),
            )
            for s_id, s_name, u_count, t_cards in set_rows
        ]

        # 4. Recent additions (top 5 most recent by updated_at / created_at)
        recent_stmt = (
            select(CollectionItem)
            .order_by(
                CollectionItem.updated_at.desc(),
                CollectionItem.created_at.desc(),
                CollectionItem.id.desc(),
            )
            .limit(5)
        )
        recent_items = list(self.db.execute(recent_stmt).scalars().all())
        recent_additions = [
            CollectionItemResponse.model_validate(item) for item in recent_items
        ]

        return CollectionStatsResponse(
            total_cards=total_cards,
            unique_cards=unique_cards,
            total_sets=total_sets,
            duplicate_count=duplicate_count,
            condition_distribution=condition_distribution,
            set_distribution=set_distribution,
            recent_additions=recent_additions,
        )

    async def add_from_scan(
        self, scan_id: str, data: AddFromScanRequest
    ) -> tuple[CollectionItem, bool]:
        """Convert a verified, confirmed scan session into a collection item.

        Returns:
            tuple[CollectionItem, bool]: (item, was_created)
            was_created is False if the scan was already added (idempotent).
        """
        scan = self.db.query(Scan).filter(Scan.id == scan_id).first()
        if scan is None:
            raise InvalidScanStateError(
                f"Scan '{scan_id}' not found.", code="SCAN_NOT_FOUND"
            )

        now_utc = datetime.now(UTC).replace(tzinfo=None)
        if scan.expires_at <= now_utc:
            raise InvalidScanStateError(
                f"Scan '{scan_id}' has expired.", code="SCAN_EXPIRED"
            )

        # Must have a confirmed crop and confirmed catalog card
        if scan.crop_status != "confirmed" or not scan.confirmed_card_id:
            raise InvalidScanStateError(
                "Scan has no confirmed card.", code="SCAN_NOT_CONFIRMED"
            )

        # Lock the scan row and check the dedicated idempotency link. A card may
        # have many distinct scans, while a single scan may increment only once.
        scan = self.db.query(Scan).filter(Scan.id == scan_id).with_for_update().first()
        linked_item = await self.get_item_for_scan(scan_id)
        if linked_item is not None:
            return linked_item, False

        # Extract snapshot strictly from scan's confirmed fields
        card_id = scan.confirmed_card_id
        card_name = scan.confirmed_card_name or scan.confirmed_card_id
        set_name = scan.confirmed_card_set_name or "Unknown Set"
        collector_number = scan.confirmed_card_number or "0"
        card_image_url = scan.confirmed_card_image_url

        # Derive set_id from provider/search clues or card_id hyphen
        set_id = scan.user_search_provider_set_id or scan.user_search_set_code
        if not set_id:
            set_id = card_id.split("-")[0] if "-" in card_id else "unknown"

        acquired_at = data.acquired_at or date.today()
        item = self._find_merge_target(
            card_id=card_id,
            provider="tcgdex",
            language="en",
            variant=data.variant,
            condition=data.condition,
        )
        if item is None:
            item = CollectionItem(
                id=str(uuid.uuid4()),
                card_id=card_id,
                provider="tcgdex",
                card_name=card_name,
                set_id=set_id,
                set_name=set_name,
                collector_number=collector_number,
                card_image_url=card_image_url,
                quantity=data.quantity,
                language="en",
                variant=data.variant,
                condition=data.condition,
                notes=data.notes,
                purchase_price=data.purchase_price,
                currency=data.currency,
                acquired_at=acquired_at,
                source_scan_id=scan_id,
                version=1,
            )
            try:
                self.db.add(item)
                self.db.flush()
                self.db.add(
                    CollectionScanLink(scan_id=scan_id, collection_item_id=item.id)
                )
                self.db.commit()
                self.db.refresh(item)
                return item, True
            except (IntegrityError, OperationalError):
                self.db.rollback()
                for _ in range(5):
                    # Check if this scan was already linked concurrently
                    linked = await self.get_item_for_scan(scan_id)
                    if linked is not None:
                        return linked, False

                    # Race with another scan for the same grouping card
                    winner = self._find_merge_target(
                        card_id=card_id,
                        provider="tcgdex",
                        language="en",
                        variant=data.variant,
                        condition=data.condition,
                    )
                    if winner is not None:
                        winner.quantity += data.quantity
                        winner.version += 1
                        winner.updated_at = datetime.now(UTC).replace(tzinfo=None)
                        if winner.source_scan_id is None:
                            winner.source_scan_id = scan_id
                        self.db.add(
                            CollectionScanLink(
                                scan_id=scan_id, collection_item_id=winner.id
                            )
                        )
                        self.db.commit()
                        self.db.refresh(winner)
                        return winner, True
                    time.sleep(0.05)
                raise
        else:
            item.quantity += data.quantity
            item.version += 1
            item.updated_at = datetime.now(UTC).replace(tzinfo=None)
            if item.source_scan_id is None:
                item.source_scan_id = scan_id

            try:
                self.db.add(
                    CollectionScanLink(scan_id=scan_id, collection_item_id=item.id)
                )
                self.db.commit()
                self.db.refresh(item)
                return item, True
            except (IntegrityError, OperationalError):
                self.db.rollback()
                # Same scan added concurrently
                linked = await self.get_item_for_scan(scan_id)
                if linked is not None:
                    return linked, False
                raise
