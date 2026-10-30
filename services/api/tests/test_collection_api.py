import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.collection import CollectionItem
from app.models.scan import Scan


def _create_confirmed_scan(
    db: Session,
    card_id: str = "base1-4",
    card_name: str = "Charizard",
    set_name: str = "Base Set",
    collector_number: str = "4",
    image_url: str | None = "https://assets.tcgdex.net/en/base/base1/4",
    expired: bool = False,
    crop_status: str = "confirmed",
) -> Scan:
    expires_at = datetime.now(UTC).replace(tzinfo=None) + (
        timedelta(hours=-1) if expired else timedelta(hours=2)
    )
    scan = Scan(
        id=str(uuid.uuid4()),
        status="confirmed",
        image_path="/app/uploads/scans/test.jpg",
        content_type="image/jpeg",
        width=800,
        height=1100,
        file_size=200000,
        expires_at=expires_at,
        crop_status=crop_status,
        confirmed_card_id=card_id if crop_status == "confirmed" else None,
        confirmed_card_name=card_name if crop_status == "confirmed" else None,
        confirmed_card_set_name=set_name if crop_status == "confirmed" else None,
        confirmed_card_number=collector_number if crop_status == "confirmed" else None,
        confirmed_card_image_url=image_url if crop_status == "confirmed" else None,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def test_create_collection_item_minimal(client: TestClient):
    """Test manual creation of a collection item with only card_id."""
    payload = {"card_id": "base1-58"}
    response = client.post("/api/v1/collection", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["card_id"] == "base1-58"
    assert data["set_id"] == "base1"
    assert data["collector_number"] == "58"
    assert data["quantity"] == 1
    assert data["condition"] == "near_mint"
    assert data["variant"] == "normal"
    assert data["language"] == "en"
    assert data["version"] == 1
    assert data["source_scan_id"] is None
    assert "id" in data
    assert len(data["id"]) == 36


def test_create_collection_item_full_attributes(client: TestClient):
    """Test manual creation with all explicit snapshot and metadata fields."""
    payload = {
        "card_id": "sv1-25",
        "card_name": "Miraidon ex",
        "set_id": "sv1",
        "set_name": "Scarlet & Violet",
        "collector_number": "025/198",
        "card_image_url": "https://assets.tcgdex.net/en/sv/sv1/25",
        "quantity": 3,
        "language": "ja",
        "variant": "holo",
        "condition": "mint",
        "notes": "Pulled from booster box, double sleeved",
        "purchase_price": "45.00",
        "currency": "usd",  # should be normalized to uppercase
        "acquired_at": "2026-10-30",
    }
    response = client.post("/api/v1/collection", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["card_name"] == "Miraidon ex"
    assert data["quantity"] == 3
    assert data["language"] == "ja"
    assert data["variant"] == "holo"
    assert data["condition"] == "mint"
    assert data["notes"] == "Pulled from booster box, double sleeved"
    assert data["purchase_price"] == "45.00"
    assert data["currency"] == "USD"
    assert data["acquired_at"] == "2026-10-30"


def test_create_collection_item_validation_errors(client: TestClient):
    """Invalid attributes must be rejected with 422 Unprocessable Entity."""
    # Quantity < 1
    resp = client.post("/api/v1/collection", json={"card_id": "c1", "quantity": 0})
    assert resp.status_code == 422

    # Invalid condition grade
    resp = client.post("/api/v1/collection", json={"card_id": "c1", "condition": "gem"})
    assert resp.status_code == 422

    # Invalid variant
    resp = client.post("/api/v1/collection", json={"card_id": "c1", "variant": "gold"})
    assert resp.status_code == 422

    # Negative purchase price
    resp = client.post(
        "/api/v1/collection", json={"card_id": "c1", "purchase_price": "-5.00"}
    )
    assert resp.status_code == 422

    # Purchase price with > 2 decimal places
    resp = client.post(
        "/api/v1/collection", json={"card_id": "c1", "purchase_price": "10.999"}
    )
    assert resp.status_code == 422

    # Invalid currency format
    resp = client.post("/api/v1/collection", json={"card_id": "c1", "currency": "US"})
    assert resp.status_code == 422


def test_get_collection_item_by_id(client: TestClient):
    """Test retrieving collection item by UUID primary key."""
    post_resp = client.post("/api/v1/collection", json={"card_id": "base1-1"})
    assert post_resp.status_code == 201
    item_id = post_resp.json()["id"]

    get_resp = client.get(f"/api/v1/collection/{item_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == item_id

    # Non-existent item
    missing_resp = client.get(f"/api/v1/collection/{uuid.uuid4()}")
    assert missing_resp.status_code == 404
    assert missing_resp.json()["detail"]["code"] == "ITEM_NOT_FOUND"


def test_patch_collection_item_success(client: TestClient):
    """Test updating collection item fields with optimistic concurrency."""
    post_resp = client.post(
        "/api/v1/collection",
        json={"card_id": "base1-2", "quantity": 1, "condition": "near_mint"},
    )
    item_id = post_resp.json()["id"]
    assert post_resp.json()["version"] == 1

    patch_payload = {
        "quantity": 4,
        "condition": "lightly_played",
        "notes": "Added 3 copies",
        "purchase_price": "19.95",
        "currency": "eur",
        "expected_version": 1,
    }
    patch_resp = client.patch(f"/api/v1/collection/{item_id}", json=patch_payload)
    assert patch_resp.status_code == 200
    data = patch_resp.json()

    assert data["quantity"] == 4
    assert data["condition"] == "lightly_played"
    assert data["notes"] == "Added 3 copies"
    assert data["purchase_price"] == "19.95"
    assert data["currency"] == "EUR"
    assert data["version"] == 2


def test_patch_collection_item_optimistic_concurrency_conflict(client: TestClient):
    """Updating with a stale expected_version must raise HTTP 409 conflict."""
    post_resp = client.post("/api/v1/collection", json={"card_id": "base1-3"})
    item_id = post_resp.json()["id"]

    conflict_resp = client.patch(
        f"/api/v1/collection/{item_id}",
        json={"quantity": 2, "expected_version": 99},
    )
    assert conflict_resp.status_code == 409
    err = conflict_resp.json()["detail"]
    assert err["code"] == "VERSION_CONFLICT"
    assert err["current_version"] == 1


def test_delete_collection_item(client: TestClient):
    """Test deleting collection item removes it and returns 204."""
    post_resp = client.post("/api/v1/collection", json={"card_id": "base1-4"})
    item_id = post_resp.json()["id"]

    del_resp = client.delete(f"/api/v1/collection/{item_id}")
    assert del_resp.status_code == 204

    # Subsequent GET returns 404
    get_resp = client.get(f"/api/v1/collection/{item_id}")
    assert get_resp.status_code == 404

    # Subsequent DELETE returns 404
    del_again = client.delete(f"/api/v1/collection/{item_id}")
    assert del_again.status_code == 404


def test_list_collection_pagination_and_has_more(client: TestClient):
    """Test pagination counters and has_more flag."""
    for i in range(1, 6):
        client.post(
            "/api/v1/collection",
            json={"card_id": f"base1-{i}", "card_name": f"Card {i}"},
        )

    # Page 1 with page_size=2
    r1 = client.get("/api/v1/collection?page=1&page_size=2")
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["total"] == 5
    assert len(d1["items"]) == 2
    assert d1["page"] == 1
    assert d1["has_more"] is True

    # Page 3 with page_size=2
    r3 = client.get("/api/v1/collection?page=3&page_size=2")
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["total"] == 5
    assert len(d3["items"]) == 1
    assert d3["page"] == 3
    assert d3["has_more"] is False


def test_list_collection_filtering(client: TestClient):
    """Test filtering by query, set_id, condition, variant, and language."""
    client.post(
        "/api/v1/collection",
        json={
            "card_id": "base1-58",
            "card_name": "Pikachu",
            "set_id": "base1",
            "condition": "mint",
            "variant": "normal",
            "language": "en",
        },
    )
    client.post(
        "/api/v1/collection",
        json={
            "card_id": "base1-4",
            "card_name": "Charizard",
            "set_id": "base1",
            "condition": "near_mint",
            "variant": "holo",
            "language": "en",
        },
    )
    client.post(
        "/api/v1/collection",
        json={
            "card_id": "neo1-1",
            "card_name": "Ampharos",
            "set_id": "neo1",
            "condition": "mint",
            "variant": "first_edition",
            "language": "ja",
        },
    )

    # Query search
    resp = client.get("/api/v1/collection?query=pikachu")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["card_name"] == "Pikachu"

    # Set filter
    resp = client.get("/api/v1/collection?set_id=neo1")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["card_name"] == "Ampharos"

    # Condition filter
    resp = client.get("/api/v1/collection?condition=mint")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2

    # Variant filter
    resp = client.get("/api/v1/collection?variant=holo")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["card_name"] == "Charizard"

    # Language filter
    resp = client.get("/api/v1/collection?language=ja")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["card_name"] == "Ampharos"


def test_list_collection_sorting(client: TestClient):
    """Test sorting orders: name_asc, name_desc, quantity_desc, set_asc."""
    client.post(
        "/api/v1/collection",
        json={"card_id": "b-1", "card_name": "Blastoise", "quantity": 1},
    )
    client.post(
        "/api/v1/collection",
        json={"card_id": "a-1", "card_name": "Alakazam", "quantity": 5},
    )
    client.post(
        "/api/v1/collection",
        json={"card_id": "c-1", "card_name": "Charizard", "quantity": 2},
    )

    # Name ASC
    r_asc = client.get("/api/v1/collection?sort=name_asc")
    names_asc = [it["card_name"] for it in r_asc.json()["items"]]
    assert names_asc == ["Alakazam", "Blastoise", "Charizard"]

    # Name DESC
    r_desc = client.get("/api/v1/collection?sort=name_desc")
    names_desc = [it["card_name"] for it in r_desc.json()["items"]]
    assert names_desc == ["Charizard", "Blastoise", "Alakazam"]

    # Quantity DESC
    r_qty = client.get("/api/v1/collection?sort=quantity_desc")
    quantities = [it["quantity"] for it in r_qty.json()["items"]]
    assert quantities == [5, 2, 1]


def test_collection_stats_accuracy(client: TestClient):
    """Test accuracy of stats aggregation query."""
    # Item 1: quantity 3 (2 duplicates)
    client.post(
        "/api/v1/collection",
        json={
            "card_id": "base1-4",
            "set_id": "base1",
            "set_name": "Base Set",
            "condition": "mint",
            "quantity": 3,
        },
    )
    # Item 2: quantity 1 (0 duplicates)
    client.post(
        "/api/v1/collection",
        json={
            "card_id": "base1-58",
            "set_id": "base1",
            "set_name": "Base Set",
            "condition": "near_mint",
            "quantity": 1,
        },
    )
    # Item 3: quantity 2 (1 duplicate)
    client.post(
        "/api/v1/collection",
        json={
            "card_id": "jungle-1",
            "set_id": "jungle",
            "set_name": "Jungle",
            "condition": "mint",
            "quantity": 2,
        },
    )

    stats_resp = client.get("/api/v1/collection/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()

    assert stats["total_cards"] == 6  # 3 + 1 + 2
    assert stats["unique_cards"] == 3
    assert stats["total_sets"] == 2
    assert stats["duplicate_count"] == 3  # (3-1) + 0 + (2-1) = 3

    assert stats["condition_distribution"]["mint"] == 5  # 3 + 2 physical cards
    assert stats["condition_distribution"]["near_mint"] == 1  # 1 physical card
    assert stats["condition_distribution"]["damaged"] == 0

    assert len(stats["set_distribution"]) == 2
    base_dist = next(s for s in stats["set_distribution"] if s["set_id"] == "base1")
    assert base_dist["count"] == 2
    assert base_dist["total_cards"] == 4

    assert len(stats["recent_additions"]) == 3


def test_scan_to_collection_unconfirmed_rejected(client: TestClient, db: Session):
    """Adding an unconfirmed scan or crop must fail with 400."""
    scan_unconfirmed = _create_confirmed_scan(db, crop_status="none")

    resp = client.post(f"/api/v1/scans/{scan_unconfirmed.id}/collection")
    assert resp.status_code == 400
    err = resp.json()["detail"]
    assert err["code"] == "SCAN_NOT_CONFIRMED"


def test_scan_to_collection_expired_rejected(client: TestClient, db: Session):
    """Expired scan must be rejected with 404 SCAN_EXPIRED."""
    expired_scan = _create_confirmed_scan(db, expired=True)

    resp = client.post(f"/api/v1/scans/{expired_scan.id}/collection")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "SCAN_EXPIRED"


def test_scan_to_collection_success_and_idempotency(client: TestClient, db: Session):
    """Adding a confirmed scan creates a collection item; calls are idempotent."""
    scan = _create_confirmed_scan(
        db,
        card_id="base1-4",
        card_name="Charizard",
        set_name="Base Set",
        collector_number="4/102",
        image_url="https://assets.tcgdex.net/en/base/base1/4",
    )

    # First call: creates new collection item (201 Created)
    resp1 = client.post(
        f"/api/v1/scans/{scan.id}/collection",
        json={"condition": "mint", "variant": "holo", "notes": "From scan"},
    )
    assert resp1.status_code == 201
    item1 = resp1.json()
    assert item1["card_id"] == "base1-4"
    assert item1["card_name"] == "Charizard"
    assert item1["set_name"] == "Base Set"
    assert item1["collector_number"] == "4/102"
    assert item1["condition"] == "mint"
    assert item1["variant"] == "holo"
    assert item1["source_scan_id"] == scan.id

    # Second call with same scan_id: idempotent return (200 OK), no duplicate row!
    resp2 = client.post(f"/api/v1/scans/{scan.id}/collection")
    assert resp2.status_code == 200
    item2 = resp2.json()
    assert item2["id"] == item1["id"]

    # Verify MariaDB database state: exactly 1 CollectionItem row exists
    items_in_db = (
        db.query(CollectionItem).filter(CollectionItem.source_scan_id == scan.id).all()
    )
    assert len(items_in_db) == 1


def test_distinct_scans_of_same_card_merge_quantity_but_remain_idempotent(
    client: TestClient, db: Session
):
    """Two physical scans group into one tile; each scan can increment only once."""
    first_scan = _create_confirmed_scan(
        db, card_id="base1-58", card_name="Pikachu", collector_number="58"
    )
    second_scan = _create_confirmed_scan(
        db, card_id="base1-58", card_name="Pikachu", collector_number="58"
    )

    first = client.post(f"/api/v1/scans/{first_scan.id}/collection")
    second = client.post(f"/api/v1/scans/{second_scan.id}/collection")

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["quantity"] == 2
    assert db.query(CollectionItem).filter_by(card_id="base1-58").count() == 1

    # Both scans resolve to the grouped item.
    for scan in (first_scan, second_scan):
        lookup = client.get(f"/api/v1/scans/{scan.id}/collection")
        assert lookup.status_code == 200
        assert lookup.json()["id"] == first.json()["id"]

    repeated = client.post(f"/api/v1/scans/{second_scan.id}/collection")
    assert repeated.status_code == 200
    assert repeated.json()["quantity"] == 2


def test_manual_duplicate_addition_increments_matching_collection_item(
    client: TestClient,
):
    payload = {
        "card_id": "base1-58",
        "card_name": "Pikachu",
        "set_id": "base1",
        "set_name": "Base Set",
        "collector_number": "58",
        "quantity": 1,
        "variant": "normal",
        "condition": "near_mint",
    }

    first = client.post("/api/v1/collection", json=payload)
    second = client.post("/api/v1/collection", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["quantity"] == 2

    listing = client.get("/api/v1/collection")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["quantity"] == 2


def test_collection_item_scan_fk_ondelete_preserves_item(
    client: TestClient, db: Session
):
    """Deleting a scan record sets source_scan_id to null and preserves item."""
    scan = _create_confirmed_scan(db, card_id="base1-1", card_name="Alakazam")

    # Add to collection
    post_resp = client.post(f"/api/v1/scans/{scan.id}/collection")
    assert post_resp.status_code == 201
    item_id = post_resp.json()["id"]

    # Delete scan (simulating expired scan cleanup)
    db.delete(scan)
    db.commit()

    # Collection item must still exist with source_scan_id = None
    get_resp = client.get(f"/api/v1/collection/{item_id}")
    assert get_resp.status_code == 200
    item = get_resp.json()
    assert item["id"] == item_id
    assert item["card_name"] == "Alakazam"
    assert item["source_scan_id"] is None
