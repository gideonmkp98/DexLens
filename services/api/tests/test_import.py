from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm import Session

from app.models.card import Card
from app.models.import_run import ImportRun
from app.models.set import Set
from app.services.importer import CardImporter
from app.services.tcgdex import TcgdexClient, TcgdexConnectionError


@pytest.mark.asyncio
async def test_initial_set_and_card_import(db: Session, sample_set_fixture):
    mock_client = AsyncMock(spec=TcgdexClient)
    mock_client.get_set.return_value = sample_set_fixture

    importer = CardImporter(client=mock_client)
    result = await importer.import_set("base1", language="en")

    assert result.status == "succeeded"
    assert result.created_count == 5
    assert result.updated_count == 0
    assert result.skipped_count == 0
    assert result.failed_count == 0

    # Verify set row
    set_row = db.query(Set).filter(Set.external_id == "base1").first()
    assert set_row is not None
    assert set_row.name == "Base Set"
    assert set_row.source == "tcgdex"
    assert set_row.series == "Base"
    assert set_row.printed_total == 102
    assert set_row.total == 102

    # Verify card rows
    cards = db.query(Card).filter(Card.set_id == set_row.id).all()
    assert len(cards) == 5

    # Verify ImportRun logged in DB
    run = db.query(ImportRun).filter(ImportRun.scope == "set:base1").first()
    assert run is not None
    assert run.status == "succeeded"
    assert run.created_count == 5


@pytest.mark.asyncio
async def test_reimport_idempotency_without_duplicates(db: Session, sample_set_fixture):
    mock_client = AsyncMock(spec=TcgdexClient)
    mock_client.get_set.return_value = sample_set_fixture

    importer = CardImporter(client=mock_client)

    # First import
    res1 = await importer.import_set("base1", language="en")
    assert res1.created_count == 5

    set_id_before = db.query(Set).filter(Set.external_id == "base1").first().id
    card_ids_before = {c.id for c in db.query(Card).all()}

    # Second import (repeat)
    res2 = await importer.import_set("base1", language="en")
    assert res2.status == "succeeded"
    assert res2.created_count == 0
    assert res2.updated_count == 0
    assert res2.skipped_count == 5

    # Verify no duplicates and stable IDs
    set_after = db.query(Set).filter(Set.external_id == "base1").first()
    assert set_after.id == set_id_before
    assert {c.id for c in db.query(Card).all()} == card_ids_before


@pytest.mark.asyncio
async def test_import_updates_existing_records_retaining_internal_ids(
    db: Session, sample_set_fixture
):
    mock_client = AsyncMock(spec=TcgdexClient)
    mock_client.get_set.return_value = sample_set_fixture

    importer = CardImporter(client=mock_client)
    await importer.import_set("base1", language="en")

    card_before = db.query(Card).filter(Card.external_id == "base1-1").first()
    original_id = card_before.id

    # Modify card name in fixture
    modified_fixture = dict(sample_set_fixture)
    modified_cards = [dict(c) for c in sample_set_fixture["cards"]]
    modified_cards[0]["name"] = "Alakazam GX"
    modified_fixture["cards"] = modified_cards

    mock_client.get_set.return_value = modified_fixture

    res = await importer.import_set("base1", language="en")
    assert res.status == "succeeded"
    assert res.updated_count == 1
    assert res.skipped_count == 4

    db.commit()
    card_after = db.query(Card).filter(Card.external_id == "base1-1").first()
    assert card_after.id == original_id
    assert card_after.name == "Alakazam GX"


@pytest.mark.asyncio
async def test_leading_zeros_and_nonnumeric_card_numbers(
    db: Session, sample_set_fixture
):
    mock_client = AsyncMock(spec=TcgdexClient)
    mock_client.get_set.return_value = sample_set_fixture

    importer = CardImporter(client=mock_client)
    await importer.import_set("base1", language="en")

    chansey = db.query(Card).filter(Card.external_id == "base1-003").first()
    assert chansey is not None
    assert chansey.local_id == "003"  # Leading zeros preserved

    pikachu = db.query(Card).filter(Card.external_id == "base1-TG01").first()
    assert pikachu is not None
    assert pikachu.local_id == "TG01"  # Prefix preserved


@pytest.mark.asyncio
async def test_missing_images_and_optional_fields(db: Session, sample_set_fixture):
    mock_client = AsyncMock(spec=TcgdexClient)
    mock_client.get_set.return_value = sample_set_fixture

    importer = CardImporter(client=mock_client)
    await importer.import_set("base1", language="en")

    clefairy = db.query(Card).filter(Card.external_id == "base1-5").first()
    assert clefairy is not None
    assert clefairy.image_base_url is None


@pytest.mark.asyncio
async def test_malformed_records_and_partial_failures(db: Session, sample_set_fixture):
    bad_fixture = dict(sample_set_fixture)
    bad_fixture["cards"] = list(sample_set_fixture["cards"]) + [
        {"id": "bad-card-1", "localId": "99", "name": None},  # Missing name
        {"id": None, "localId": "100", "name": "Nameless"},  # Missing ID
    ]

    mock_client = AsyncMock(spec=TcgdexClient)
    mock_client.get_set.return_value = bad_fixture

    importer = CardImporter(client=mock_client)
    result = await importer.import_set("base1", language="en")

    assert result.status == "partially_failed"
    assert result.created_count == 5
    assert result.failed_count == 2
    assert len(result.errors) == 2

    # Verify import run logged as partially_failed
    run = db.query(ImportRun).filter(ImportRun.scope == "set:base1").first()
    assert run.status == "partially_failed"
    assert run.failed_count == 2


@pytest.mark.asyncio
async def test_provider_failures_logged(db: Session):
    mock_client = AsyncMock(spec=TcgdexClient)
    mock_client.get_set.side_effect = TcgdexConnectionError("Network connection reset")

    importer = CardImporter(client=mock_client)
    result = await importer.import_set("base1", language="en")

    assert result.status == "failed"
    assert len(result.errors) > 0

    run = db.query(ImportRun).filter(ImportRun.scope == "set:base1").first()
    assert run is not None
    assert run.status == "failed"
    assert "Network connection reset" in (run.error_summary or "")


@pytest.mark.asyncio
async def test_exclusion_of_digital_only_products(
    db: Session, sample_digital_set_fixture
):
    mock_client = AsyncMock(spec=TcgdexClient)
    mock_client.get_set.return_value = sample_digital_set_fixture

    importer = CardImporter(client=mock_client)
    result = await importer.import_set("A1", language="en")

    assert result.status == "failed"
    assert "digital-only product" in result.errors[0]
    assert db.query(Set).count() == 0
    assert db.query(Card).count() == 0


@pytest.mark.asyncio
async def test_no_per_card_detail_requests_during_index_import(sample_set_fixture):
    mock_client = AsyncMock(spec=TcgdexClient)
    mock_client.get_set.return_value = sample_set_fixture
    mock_client.get_card.return_value = {"id": "dummy"}

    importer = CardImporter(client=mock_client)
    await importer.import_set("base1", language="en")

    assert mock_client.get_set.call_count == 1
    assert mock_client.get_card.call_count == 0  # CRITICAL: zero per-card calls


@pytest.mark.asyncio
async def test_unsupported_language_rejection():
    mock_client = AsyncMock(spec=TcgdexClient)
    importer = CardImporter(client=mock_client)

    result = await importer.import_set("base1", language="xx")
    assert result.status == "failed"
    assert "Unsupported language" in result.errors[0]
    assert mock_client.get_set.call_count == 0
