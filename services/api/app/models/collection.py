import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.scan import Scan


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class CollectionItem(Base):
    """Personal collection record representing an owned Pokémon card item."""

    __tablename__ = "collection_items"
    __table_args__ = (
        CheckConstraint(
            "quantity >= 1",
            name="ck_collection_items_quantity_positive",
        ),
        CheckConstraint(
            "purchase_price IS NULL OR purchase_price >= 0",
            name="ck_collection_items_purchase_price_non_negative",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_collection_items_version_positive",
        ),
        Index("ix_collection_items_set_collector", "set_id", "collector_number"),
        Index(
            "ix_collection_items_card_variant_lang",
            "card_id",
            "variant",
            "language",
        ),
        UniqueConstraint(
            "provider",
            "card_id",
            "language",
            "variant",
            "condition",
            name="uq_collection_items_grouping",
        ),
    )

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # External card & catalog identifiers
    card_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="tcgdex",
        server_default="tcgdex",
    )

    # Denormalized card & set snapshots (immutable collection state)
    card_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    set_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    set_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    collector_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    card_image_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        default=None,
    )

    # Inventory & item classification
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
        server_default="en",
        index=True,
    )
    variant: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="normal",
        server_default="normal",
        index=True,
    )
    condition: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="near_mint",
        server_default="near_mint",
        index=True,
    )

    # Collector notes and provenance
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    purchase_price: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        default=None,
    )
    currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
        default=None,
    )
    acquired_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        default=None,
    )

    # Optional origin link back to the scan session that verified this specimen
    source_scan_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "scans.id",
            ondelete="SET NULL",
            name="fk_collection_items_source_scan_id_scans",
        ),
        nullable=True,
        index=True,
    )

    # Optimistic concurrency control
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    scan: Mapped["Scan | None"] = relationship(
        "Scan",
        back_populates="collection_items",
    )
    scan_links: Mapped[list["CollectionScanLink"]] = relationship(
        "CollectionScanLink",
        back_populates="collection_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CollectionItem(id='{self.id}', card_id='{self.card_id}', "
            f"name='{self.card_name}', variant='{self.variant}', "
            f"quantity={self.quantity})>"
        )


class CollectionScanLink(Base):
    """Idempotency link between a physical scan and a grouped collection item."""

    __tablename__ = "collection_scan_links"

    scan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scans.id", ondelete="CASCADE"),
        primary_key=True,
    )
    collection_item_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("collection_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )

    collection_item: Mapped["CollectionItem"] = relationship(
        "CollectionItem",
        back_populates="scan_links",
    )
