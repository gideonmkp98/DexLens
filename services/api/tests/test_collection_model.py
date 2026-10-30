import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models.collection import CollectionItem
from app.models.scan import Scan


def _create_dummy_scan(db: Session, scan_id: str | None = None) -> Scan:
    scan = Scan(
        id=scan_id or str(uuid.uuid4()),
        status="confirmed",
        image_path="/app/uploads/scans/test.jpg",
        content_type="image/jpeg",
        width=1000,
        height=1400,
        file_size=500000,
        expires_at=datetime.now(UTC).replace(tzinfo=None),
        crop_status="confirmed",
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def test_create_collection_item_defaults(db: Session):
    """Test creating a collection item with default fields and server defaults."""
    item = CollectionItem(
        card_id="base1-58",
        card_name="Pikachu",
        set_id="base1",
        set_name="Base Set",
        collector_number="58/102",
        card_image_url="https://assets.tcgdex.net/en/base/base1/58",
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    assert item.id is not None
    assert len(item.id) == 36
    assert item.provider == "tcgdex"
    assert item.language == "en"
    assert item.variant == "normal"
    assert item.condition == "near_mint"
    assert item.quantity == 1
    assert item.version == 1
    assert item.notes is None
    assert item.purchase_price is None
    assert item.currency is None
    assert item.acquired_at is None
    assert item.source_scan_id is None
    assert item.created_at is not None
    assert item.updated_at is not None
    assert repr(item) == (
        f"<CollectionItem(id='{item.id}', card_id='base1-58', "
        "name='Pikachu', variant='normal', quantity=1)>"
    )


def test_create_collection_item_full_attributes(db: Session):
    """Test creating a collection item with all optional attributes filled."""
    scan = _create_dummy_scan(db)
    acquisition_date = date(2026, 10, 30)

    item = CollectionItem(
        card_id="base1-4",
        provider="tcgdex",
        card_name="Charizard",
        set_id="base1",
        set_name="Base Set",
        collector_number="4/102",
        card_image_url="https://assets.tcgdex.net/en/base/base1/4",
        quantity=2,
        language="en",
        variant="first_edition",
        condition="mint",
        notes="PSA candidate, clean holo foil",
        purchase_price=Decimal("450.50"),
        currency="EUR",
        acquired_at=acquisition_date,
        source_scan_id=scan.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    assert item.card_name == "Charizard"
    assert item.quantity == 2
    assert item.variant == "first_edition"
    assert item.condition == "mint"
    assert item.notes == "PSA candidate, clean holo foil"
    assert item.purchase_price == Decimal("450.50")
    assert item.currency == "EUR"
    assert item.acquired_at == acquisition_date
    assert item.source_scan_id == scan.id
    assert item.scan is not None
    assert item.scan.id == scan.id
    assert item in scan.collection_items


def test_collection_item_scan_fk_ondelete_set_null(db: Session):
    """When a scan is deleted (e.g. by expired scan cleanup),

    foreign key ondelete='SET NULL' must preserve the collection item
    and set source_scan_id to NULL.
    """
    scan = _create_dummy_scan(db)
    item = CollectionItem(
        card_id="base1-1",
        card_name="Alakazam",
        set_id="base1",
        set_name="Base Set",
        collector_number="1/102",
        source_scan_id=scan.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    assert item.source_scan_id == scan.id

    # Delete the scan record (simulates cleanup_expired_scans)
    db.delete(scan)
    db.commit()

    # Refresh collection item - it should still exist with source_scan_id = NULL
    db.refresh(item)
    assert item.id is not None
    assert item.source_scan_id is None
    assert item.card_name == "Alakazam"


def test_collection_item_quantity_check_constraint(db: Session):
    """Quantity must be >= 1."""
    item = CollectionItem(
        card_id="base1-2",
        card_name="Blastoise",
        set_id="base1",
        set_name="Base Set",
        collector_number="2/102",
        quantity=0,
    )
    db.add(item)
    with pytest.raises((IntegrityError, OperationalError)) as exc_info:
        db.commit()
    assert "ck_collection_items_quantity_positive" in str(exc_info.value)
    db.rollback()


def test_collection_item_purchase_price_check_constraint(db: Session):
    """Purchase price, if present, must be >= 0."""
    item = CollectionItem(
        card_id="base1-3",
        card_name="Venusaur",
        set_id="base1",
        set_name="Base Set",
        collector_number="3/102",
        purchase_price=Decimal("-10.00"),
    )
    db.add(item)
    with pytest.raises((IntegrityError, OperationalError)) as exc_info:
        db.commit()
    assert "ck_collection_items_purchase_price_non_negative" in str(exc_info.value)
    db.rollback()


def test_collection_item_optimistic_concurrency(db: Session):
    """Verify version column is incremented during update operations."""
    item = CollectionItem(
        card_id="base1-58",
        card_name="Pikachu",
        set_id="base1",
        set_name="Base Set",
        collector_number="58/102",
        quantity=1,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    assert item.version == 1

    # Update item
    item.notes = "Updated notes"
    item.version += 1
    db.commit()
    db.refresh(item)

    assert item.version == 2
    assert item.notes == "Updated notes"
