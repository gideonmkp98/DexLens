import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.collection import CollectionItem
from app.models.scan import Scan


def _create_user(client: TestClient, label: str) -> dict[str, str]:
    email = f"{label}_{uuid.uuid4().hex[:8]}@example.com"
    password = "SecurePassword123!"
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert res.status_code == 201
    return {"id": res.json()["id"], "email": email, "password": password}


def test_collection_isolation_between_registered_users(client: TestClient):
    # Setup Client A
    client_a = TestClient(client.app)
    _create_user(client_a, "user_a")

    # User A creates a collection item
    item_payload_a = {
        "card_id": "base1-4",
        "quantity": 2,
        "condition": "near_mint",
        "variant": "holo",
    }
    create_res_a = client_a.post("/api/v1/collection", json=item_payload_a)
    assert create_res_a.status_code == 201
    item_a_id = create_res_a.json()["id"]

    # Setup Client B
    client_b = TestClient(client.app)
    _create_user(client_b, "user_b")

    # User B lists collection -> should NOT contain User A's item
    list_res_b = client_b.get("/api/v1/collection")
    assert list_res_b.status_code == 200
    items_b = list_res_b.json()["items"]
    assert len(items_b) == 0

    # User B tries GET item A -> 404
    get_res_b = client_b.get(f"/api/v1/collection/{item_a_id}")
    assert get_res_b.status_code == 404
    assert get_res_b.json()["detail"]["code"] == "ITEM_NOT_FOUND"

    # User B tries PATCH item A -> 404
    patch_res_b = client_b.patch(
        f"/api/v1/collection/{item_a_id}",
        json={"quantity": 10, "expected_version": 1},
    )
    assert patch_res_b.status_code == 404

    # User B tries DELETE item A -> 404
    del_res_b = client_b.delete(f"/api/v1/collection/{item_a_id}")
    assert del_res_b.status_code == 404

    # User A can still view, update, and delete their own item
    get_res_a = client_a.get(f"/api/v1/collection/{item_a_id}")
    assert get_res_a.status_code == 200
    assert get_res_a.json()["id"] == item_a_id

    patch_res_a = client_a.patch(
        f"/api/v1/collection/{item_a_id}",
        json={"quantity": 5, "expected_version": 1},
    )
    assert patch_res_a.status_code == 200
    assert patch_res_a.json()["quantity"] == 5

    del_res_a = client_a.delete(f"/api/v1/collection/{item_a_id}")
    assert del_res_a.status_code == 204


def test_scan_isolation_between_different_users(client: TestClient, db: Session):
    from pathlib import Path

    from app.core.config import settings

    client_a = TestClient(client.app)
    user_a = _create_user(client_a, "scanner_a")

    client_b = TestClient(client.app)
    _create_user(client_b, "scanner_b")

    # Create dummy scan file on disk

    scan_id = str(uuid.uuid4())
    storage_dir = Path(settings.UPLOAD_DIRECTORY).resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    scan_file = storage_dir / f"{scan_id}.jpg"
    scan_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    # Create scan owned by user A
    scan_a = Scan(
        id=scan_id,
        user_id=user_a["id"],
        anonymous_session_id=None,
        status="confirmed",
        image_path=f"{scan_id}.jpg",
        content_type="image/jpeg",
        width=800,
        height=1100,
        file_size=104,
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2),
    )
    db.add(scan_a)
    db.commit()

    try:
        # User A can access scan
        res_a = client_a.get(f"/api/v1/scans/{scan_a.id}")
        assert res_a.status_code == 200

        # User B cannot access scan A -> 404
        res_b = client_b.get(f"/api/v1/scans/{scan_a.id}")
        assert res_b.status_code == 404
        assert res_b.json()["detail"]["code"] == "SCAN_NOT_FOUND"
    finally:
        if scan_file.exists():
            scan_file.unlink()


def test_legacy_unowned_items_are_not_globally_accessible(
    client: TestClient, db: Session
):
    # Legacy rows require an explicit administrative migration and must never be
    # exposed as a shared collection to every anonymous visitor.
    legacy_item = CollectionItem(
        id=str(uuid.uuid4()),
        user_id=None,
        anonymous_session_id=None,
        card_id="base1-58",
        set_id="base1",
        collector_number="58",
        card_name="Pikachu",
        set_name="Base Set",
        quantity=1,
        condition="near_mint",
        variant="normal",
        language="en",
        version=1,
    )
    db.add(legacy_item)
    db.commit()

    # Fresh clients cannot read unassigned legacy inventory.
    fresh_client = TestClient(client.app)
    res = fresh_client.get(f"/api/v1/collection/{legacy_item.id}")
    assert res.status_code == 404
