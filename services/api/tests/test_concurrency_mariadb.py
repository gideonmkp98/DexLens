import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Update

from app.api.v1.cards import get_tcgdex_client
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.scan import Scan
from app.services import crop_service
from tests.conftest import TestingSessionLocal, test_engine
from tests.test_card_detection_and_crop import (
    _create_synthetic_card_image,
    _setup_scan_in_db,
)


@pytest.fixture(autouse=True)
def require_mariadb_test_db():
    """Ensure tests run against a dedicated MariaDB test database ending in '_test'."""
    backend = test_engine.url.get_backend_name()
    if backend not in ("mysql", "mariadb"):
        pytest.skip(
            f"MariaDB concurrency tests require a dedicated MariaDB database. "
            f"Current backend is '{backend}'. Run via 'docker compose exec api pytest'."
        )
    db_name = test_engine.url.database or ""
    if not db_name.endswith("_test"):
        raise RuntimeError(
            f"Database safeguard: concurrency tests must use a database ending in "
            f"'_test'. Current database is '{db_name}'."
        )


@pytest.fixture(autouse=True)
def per_request_db_sessions():
    """Ensure each concurrent request uses its own dedicated Session/connection."""

    def _get_fresh_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_fresh_db
    yield
    app.dependency_overrides.pop(get_db, None)


def test_mariadb_concurrent_crop_vs_crop(tmp_path: Path, monkeypatch) -> None:
    """Test A: Two concurrent crop requests starting from the same revision.

    Both requests genuinely overlap during image processing and hit the database update
    simultaneously. Exactly one publishes successfully (HTTP 200), the other is rejected
    with HTTP 409, and the losing candidate file is safely unlinked.
    """
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))

    setup_db = TestingSessionLocal()
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(setup_db, tmp_path, img)
    scan_id = str(scan.id)
    setup_db.close()

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    # Barrier: both threads wait until BOTH have finished image processing
    # and generated their candidate crop file on disk before either attempts DB commit
    barrier = threading.Barrier(2)
    orig_warp = crop_service.perform_crop_and_warp

    def synchronized_warp(*args, **kwargs):
        res = orig_warp(*args, **kwargs)
        barrier.wait(timeout=10)
        return res

    monkeypatch.setattr("app.api.v1.scans.perform_crop_and_warp", synchronized_warp)

    results = {}

    def run_crop(worker_id: int, rot: int):
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/scans/{scan_id}/crop",
            json={"corners": corners, "rotation": rot, "expected_version": 0},
        )
        results[worker_id] = (resp.status_code, resp.json())

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_crop, 1, 0)
        f2 = executor.submit(run_crop, 2, 90)
        f1.result()
        f2.result()

    status1, data1 = results[1]
    status2, data2 = results[2]

    # Exactly one request must succeed (200), and one must fail with 409 STALE_VERSION
    statuses = [status1, status2]
    assert 200 in statuses
    assert 409 in statuses

    winner_data = data1 if status1 == 200 else data2
    loser_data = data2 if status1 == 200 else data1
    assert winner_data["crop_version"] == 1
    assert loser_data["detail"]["code"] == "STALE_VERSION"

    # Verify winning state in MariaDB
    check_db = TestingSessionLocal()
    scan_db = check_db.query(Scan).filter(Scan.id == scan_id).first()
    assert scan_db is not None
    assert scan_db.crop_version == 1
    assert scan_db.crop_status == "preview"
    assert scan_db.rotation == winner_data["rotation"]
    assert scan_db.crop_path is not None

    # Verify that the winning image bytes on disk belong to the winning request
    winning_file = storage_root / scan_db.crop_path
    assert winning_file.exists()
    assert len(winning_file.read_bytes()) == winner_data["crop_file_size"]

    # Verify that the losing candidate was safely cleaned up: only source + winning crop
    all_files = list(storage_root.iterdir())
    assert len(all_files) == 2
    assert set(all_files) == {storage_root / f"{scan_id}.jpg", winning_file}
    check_db.close()


def test_mariadb_concurrent_crop_vs_confirmation(tmp_path: Path, monkeypatch) -> None:
    """Test B: Crop began before confirmation and is paused during processing.

    Confirmation of the existing preview completes. The paused crop resumes and
    cannot overwrite the confirmed state (returns HTTP 409).
    """
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))

    setup_db = TestingSessionLocal()
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(setup_db, tmp_path, img)
    scan_id = str(scan.id)
    setup_db.close()

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    # Generate initial preview version 1
    init_client = TestClient(app)
    r_prev = init_client.post(
        f"/api/v1/scans/{scan_id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    assert r_prev.status_code == 200
    assert r_prev.json()["crop_version"] == 1

    crop_processing_done = threading.Event()
    confirm_finished = threading.Event()
    orig_warp = crop_service.perform_crop_and_warp

    def paused_warp(*args, **kwargs):
        res = orig_warp(*args, **kwargs)
        crop_processing_done.set()
        # Pause the crop until confirmation completes
        confirm_finished.wait(timeout=10)
        return res

    monkeypatch.setattr("app.api.v1.scans.perform_crop_and_warp", paused_warp)

    crop_result = {}

    def run_crop_worker():
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/scans/{scan_id}/crop",
            json={"corners": corners, "rotation": 180, "expected_version": 1},
        )
        crop_result["status"] = resp.status_code
        crop_result["body"] = resp.json()

    with ThreadPoolExecutor(max_workers=1) as executor:
        fut = executor.submit(run_crop_worker)

        # 1. Wait until crop has finished processing and candidate file is on disk
        assert crop_processing_done.wait(timeout=10)

        # 2. Confirm version 1 in main thread
        confirm_client = TestClient(app)
        confirm_resp = confirm_client.post(
            f"/api/v1/scans/{scan_id}/confirm",
            json={"crop_version": 1},
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["crop_status"] == "confirmed"

        # 3. Allow paused crop to resume and attempt its conditional update
        confirm_finished.set()
        fut.result()

    # Paused crop must be rejected with 409 and not overwrite confirmed state
    assert crop_result["status"] == 409
    assert crop_result["body"]["detail"]["code"] in (
        "CONFIRMED_CONFLICT",
        "STALE_VERSION",
    )

    # Verify scan remains confirmed in MariaDB with original rotation (0, not 180)
    check_db = TestingSessionLocal()
    scan_db = check_db.query(Scan).filter(Scan.id == scan_id).first()
    assert scan_db is not None
    assert scan_db.crop_status == "confirmed"
    assert scan_db.confirmed_at is not None
    assert scan_db.rotation == 0
    check_db.close()


def test_mariadb_concurrent_confirm_vs_replacement(tmp_path: Path, monkeypatch) -> None:
    """Test C: Confirmation vs Replacement.

    A confirmation request for an older revision cannot confirm a newly replaced crop.
    The resulting state is consistent with whichever atomic operation won.
    """
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))

    setup_db = TestingSessionLocal()
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(setup_db, tmp_path, img)
    scan_id = str(scan.id)
    setup_db.close()

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    # Generate preview version 1
    client1 = TestClient(app)
    r1 = client1.post(
        f"/api/v1/scans/{scan_id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    assert r1.status_code == 200
    assert r1.json()["crop_version"] == 1

    confirm_file_checked = threading.Event()
    replacement_committed = threading.Event()

    orig_execute = Session.execute

    def synchronized_execute(self, statement, *args, **kwargs):
        if (
            isinstance(statement, Update)
            and statement.compile().params.get("crop_status") == "confirmed"
        ):
            confirm_file_checked.set()
            replacement_committed.wait(timeout=10)
        return orig_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", synchronized_execute)

    confirm_result = {}

    def run_confirm_worker():
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/scans/{scan_id}/confirm",
            json={"crop_version": 1},
        )
        confirm_result["status"] = resp.status_code
        confirm_result["body"] = resp.json()

    with ThreadPoolExecutor(max_workers=1) as executor:
        fut = executor.submit(run_confirm_worker)

        # Wait until confirmation verified the file and reached the database update
        assert confirm_file_checked.wait(timeout=10)

        # Replacement crop runs and commits version 2 (rotation 90)
        replace_client = TestClient(app)
        r_replace = replace_client.post(
            f"/api/v1/scans/{scan_id}/crop",
            json={"corners": corners, "rotation": 90, "expected_version": 1},
        )
        assert r_replace.status_code == 200
        assert r_replace.json()["crop_version"] == 2

        # Release confirmation to attempt its conditional update
        replacement_committed.set()
        fut.result()

    # Confirmation for older revision (v1) must NOT confirm the replaced v2 crop
    assert confirm_result["status"] == 409
    assert confirm_result["body"]["detail"]["code"] == "STALE_VERSION"

    # Final database state in MariaDB: remains preview version 2 (not confirmed!)
    check_db = TestingSessionLocal()
    scan_db = check_db.query(Scan).filter(Scan.id == scan_id).first()
    assert scan_db is not None
    assert scan_db.crop_version == 2
    assert scan_db.crop_status == "preview"
    assert scan_db.confirmed_at is None
    assert scan_db.rotation == 90
    check_db.close()


def test_mariadb_concurrent_recognition_vs_crop_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    """Test D: Recognition paused before DB update while a replacement crop commits.

    Recognition must be rejected with HTTP 409 (STALE_VERSION) and must not overwrite
    the newer crop state.
    """
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))

    setup_db = TestingSessionLocal()
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(setup_db, tmp_path, img)
    scan_id = str(scan.id)
    setup_db.close()

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    # Generate and confirm initial crop (version 1 -> 2)
    client1 = TestClient(app)
    r_crop = client1.post(
        f"/api/v1/scans/{scan_id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    assert r_crop.status_code == 200
    v1 = r_crop.json()["crop_version"]

    r_conf = client1.post(
        f"/api/v1/scans/{scan_id}/confirm",
        json={"crop_version": v1},
    )
    assert r_conf.status_code == 200
    confirmed_v = r_conf.json()["crop_version"]

    rec_paused = threading.Event()
    replacement_done = threading.Event()

    orig_execute = Session.execute

    def synchronized_execute(self, statement, *args, **kwargs):
        if (
            isinstance(statement, Update)
            and statement.compile().params.get("recognition_status") == "completed"
        ):
            rec_paused.set()
            replacement_done.wait(timeout=10)
        return orig_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", synchronized_execute)

    rec_result = {}

    def run_recognize_worker():
        client = TestClient(app)
        resp = client.post(f"/api/v1/scans/{scan_id}/recognize")
        rec_result["status"] = resp.status_code
        rec_result["body"] = resp.json()

    with ThreadPoolExecutor(max_workers=1) as executor:
        fut = executor.submit(run_recognize_worker)

        assert rec_paused.wait(timeout=10)

        # In parallel, user replaces the crop
        r_replace = client1.post(
            f"/api/v1/scans/{scan_id}/crop",
            json={"corners": corners, "rotation": 180, "expected_version": confirmed_v},
        )
        assert r_replace.status_code == 200

        replacement_done.set()
        fut.result()

    # Late recognition response cannot publish over newer crop version
    assert rec_result["status"] == 409
    assert rec_result["body"]["detail"]["code"] == "STALE_VERSION"


def test_mariadb_concurrent_card_confirmation_vs_crop_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    """Test E: Confirming a card while a replacement crop commits concurrently.

    The card confirmation must fail with HTTP 409 (STALE_VERSION) and must not confirm
    the wrong (new) crop.
    """
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))

    setup_db = TestingSessionLocal()
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(setup_db, tmp_path, img)
    scan_id = str(scan.id)
    setup_db.close()

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    client = TestClient(app)
    r_crop = client.post(
        f"/api/v1/scans/{scan_id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    v1 = r_crop.json()["crop_version"]
    r_conf = client.post(
        f"/api/v1/scans/{scan_id}/confirm",
        json={"crop_version": v1},
    )
    confirmed_v = r_conf.json()["crop_version"]

    card_conf_paused = threading.Event()
    replacement_done = threading.Event()

    mock_client = AsyncMock()
    mock_client.get_card.return_value = {
        "id": "base1-58",
        "name": "Pikachu",
        "localId": "58",
        "set": {"id": "base1", "name": "Base Set"},
    }
    app.dependency_overrides[get_tcgdex_client] = lambda: mock_client

    orig_execute = Session.execute

    def synchronized_execute(self, statement, *args, **kwargs):
        if (
            isinstance(statement, Update)
            and statement.compile().params.get("confirmed_card_id") == "base1-58"
        ):
            card_conf_paused.set()
            replacement_done.wait(timeout=10)
        return orig_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", synchronized_execute)

    conf_result = {}

    def run_confirm_card_worker():
        c = TestClient(app)
        # Mock client.get_card for test
        resp = c.post(
            f"/api/v1/scans/{scan_id}/confirm-card",
            json={"card_id": "base1-58", "expected_crop_version": confirmed_v},
        )
        conf_result["status"] = resp.status_code
        conf_result["body"] = resp.json()

    with ThreadPoolExecutor(max_workers=1) as executor:
        fut = executor.submit(run_confirm_card_worker)

        assert card_conf_paused.wait(timeout=10)

        # Replacement crop commits
        r_replace = client.post(
            f"/api/v1/scans/{scan_id}/crop",
            json={"corners": corners, "rotation": 90, "expected_version": confirmed_v},
        )
        assert r_replace.status_code == 200

        replacement_done.set()
        fut.result()

    assert conf_result["status"] == 409
    assert conf_result["body"]["detail"]["code"] == "STALE_VERSION"
    app.dependency_overrides.pop(get_tcgdex_client, None)


def test_mariadb_concurrent_competing_candidate_searches(
    tmp_path: Path, monkeypatch
) -> None:
    """Test F: Two overlapping candidate searches on the same crop.

    Both start with expected_search_version = 0.
    Exactly one succeeds with HTTP 200 (search_version becomes 1),
    and the other is rejected with HTTP 409 (STALE_SEARCH_VERSION).
    The winning search results and user search fields are preserved in MariaDB.
    """
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))

    setup_db = TestingSessionLocal()
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(setup_db, tmp_path, img)
    scan_id = str(scan.id)
    setup_db.close()

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    client = TestClient(app)
    r_crop = client.post(
        f"/api/v1/scans/{scan_id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    v1 = r_crop.json()["crop_version"]
    r_conf = client.post(
        f"/api/v1/scans/{scan_id}/confirm",
        json={"crop_version": v1},
    )
    confirmed_v = r_conf.json()["crop_version"]

    mock_client = AsyncMock()
    mock_client.get_cards_search.return_value = [
        {
            "id": "base1-58",
            "name": "Pikachu",
            "localId": "58",
            "set": {"id": "base1", "name": "Base Set", "cardCount": {"official": 102}},
        }
    ]
    app.dependency_overrides[get_tcgdex_client] = lambda: mock_client

    barrier = threading.Barrier(2)
    orig_execute = Session.execute

    def synchronized_execute(self, statement, *args, **kwargs):
        if (
            isinstance(statement, Update)
            and "user_search_name" in statement.compile().params
        ):
            barrier.wait(timeout=10)
        return orig_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", synchronized_execute)

    results = {}

    def run_search(worker_id: int, card_name: str):
        c = TestClient(app)
        resp = c.post(
            f"/api/v1/scans/{scan_id}/search-candidates",
            json={
                "name": card_name,
                "expected_crop_version": confirmed_v,
                "expected_search_version": 0,
            },
        )
        results[worker_id] = (resp.status_code, resp.json())

    with ThreadPoolExecutor(max_workers=2) as executor:
        futs = [
            executor.submit(run_search, 1, "Pikachu"),
            executor.submit(run_search, 2, "Raichu"),
        ]
        for f in futs:
            f.result()

    statuses = [r[0] for r in results.values()]
    assert sorted(statuses) == [200, 409], f"Expected [200, 409], got {statuses}"

    losing_result = next(r[1] for r in results.values() if r[0] == 409)
    assert losing_result["detail"]["code"] == "STALE_SEARCH_VERSION"

    # Verify winning state in DB
    verify_db = TestingSessionLocal()
    updated_scan = verify_db.query(Scan).filter(Scan.id == scan_id).first()
    assert updated_scan.search_version == 1
    assert updated_scan.user_search_name in ("Pikachu", "Raichu")
    assert updated_scan.catalog_status == "ok"
    verify_db.close()
    app.dependency_overrides.pop(get_tcgdex_client, None)


def test_mariadb_user_search_during_delayed_ocr(tmp_path: Path, monkeypatch) -> None:
    """Test G: User initiates a manual candidate search during delayed OCR.

    OCR starts with search_version = 0.
    Before OCR commits, user search finishes and commits (search_version becomes 1,
    user_search_name = 'Charizard').
    When delayed OCR finishes:
    - It must NOT overwrite user_search_name or candidate_matches.
    - It must NOT roll back search_version.
    - It successfully stores ocr_raw_text and recognized_* metadata.
    """
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))

    setup_db = TestingSessionLocal()
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(setup_db, tmp_path, img)
    scan_id = str(scan.id)
    setup_db.close()

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    client = TestClient(app)
    r_crop = client.post(
        f"/api/v1/scans/{scan_id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    v1 = r_crop.json()["crop_version"]
    r_conf = client.post(
        f"/api/v1/scans/{scan_id}/confirm",
        json={"crop_version": v1},
    )
    confirmed_v = r_conf.json()["crop_version"]

    mock_client = AsyncMock()
    mock_client.get_cards_search.return_value = [
        {
            "id": "base1-4",
            "name": "Charizard",
            "localId": "4",
            "set": {"id": "base1", "name": "Base Set", "cardCount": {"official": 102}},
        }
    ]
    app.dependency_overrides[get_tcgdex_client] = lambda: mock_client

    ocr_paused = threading.Event()
    user_search_done = threading.Event()

    orig_execute = Session.execute

    def synchronized_execute(self, statement, *args, **kwargs):
        if (
            isinstance(statement, Update)
            and statement.compile().params.get("recognition_status") == "completed"
        ):
            ocr_paused.set()
            user_search_done.wait(timeout=10)
        return orig_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", synchronized_execute)

    ocr_result = {}

    def run_ocr_worker():
        c = TestClient(app)
        resp = c.post(f"/api/v1/scans/{scan_id}/recognize")
        ocr_result["status"] = resp.status_code
        ocr_result["body"] = resp.json()

    with ThreadPoolExecutor(max_workers=1) as executor:
        fut = executor.submit(run_ocr_worker)

        assert ocr_paused.wait(timeout=10)

        # In parallel, user runs a manual search
        search_res = client.post(
            f"/api/v1/scans/{scan_id}/search-candidates",
            json={
                "name": "Charizard",
                "expected_crop_version": confirmed_v,
                "expected_search_version": 0,
            },
        )
        assert search_res.status_code == 200
        assert search_res.json()["search_version"] == 1

        user_search_done.set()
        fut.result()

    # OCR call returns HTTP 200 and reports completion
    assert ocr_result["status"] == 200

    # Verify DB: user_search_name remains Charizard, search_version is >= 1,
    # and ocr_raw_text is stored!
    verify_db = TestingSessionLocal()
    scan_in_db = verify_db.query(Scan).filter(Scan.id == scan_id).first()
    assert scan_in_db.user_search_name == "Charizard"
    assert scan_in_db.search_version == 1
    assert scan_in_db.recognition_status == "completed"
    assert scan_in_db.ocr_crop_version == confirmed_v
    verify_db.close()
    app.dependency_overrides.pop(get_tcgdex_client, None)


def test_mariadb_competing_card_confirmations(tmp_path: Path, monkeypatch) -> None:
    """Test H: Two competing card confirmations on the same candidate view.

    Both start with expected_selection_version = 0.
    Exactly one succeeds (HTTP 200, card_selection_version becomes 1),
    and the other is rejected with HTTP 409 (STALE_SELECTION_VERSION).
    """
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))

    setup_db = TestingSessionLocal()
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(setup_db, tmp_path, img)
    scan_id = str(scan.id)
    setup_db.close()

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    client = TestClient(app)
    r_crop = client.post(
        f"/api/v1/scans/{scan_id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    v1 = r_crop.json()["crop_version"]
    r_conf = client.post(
        f"/api/v1/scans/{scan_id}/confirm",
        json={"crop_version": v1},
    )
    confirmed_v = r_conf.json()["crop_version"]

    mock_client = AsyncMock()

    async def mock_get_card(cid):
        return {
            "id": cid,
            "name": f"Card {cid}",
            "localId": "1",
            "set": {"id": "base1", "name": "Base Set"},
        }

    mock_client.get_card.side_effect = mock_get_card
    app.dependency_overrides[get_tcgdex_client] = lambda: mock_client

    barrier = threading.Barrier(2)
    orig_execute = Session.execute

    def synchronized_execute(self, statement, *args, **kwargs):
        if (
            isinstance(statement, Update)
            and "confirmed_card_id" in statement.compile().params
        ):
            barrier.wait(timeout=10)
        return orig_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", synchronized_execute)

    results = {}

    def run_confirm(worker_id: int, card_id: str):
        c = TestClient(app)
        resp = c.post(
            f"/api/v1/scans/{scan_id}/confirm-card",
            json={
                "card_id": card_id,
                "expected_crop_version": confirmed_v,
                "expected_search_version": 0,
                "expected_selection_version": 0,
            },
        )
        results[worker_id] = (resp.status_code, resp.json())

    with ThreadPoolExecutor(max_workers=2) as executor:
        futs = [
            executor.submit(run_confirm, 1, "base1-58"),
            executor.submit(run_confirm, 2, "base1-4"),
        ]
        for f in futs:
            f.result()

    statuses = [r[0] for r in results.values()]
    assert sorted(statuses) == [200, 409], f"Expected [200, 409], got {statuses}"

    losing_result = next(r[1] for r in results.values() if r[0] == 409)
    assert losing_result["detail"]["code"] == "STALE_SELECTION_VERSION"

    # Verify winning state in DB
    verify_db = TestingSessionLocal()
    scan_in_db = verify_db.query(Scan).filter(Scan.id == scan_id).first()
    assert scan_in_db.card_selection_version == 1
    assert scan_in_db.confirmed_card_id in ("base1-58", "base1-4")
    verify_db.close()
    app.dependency_overrides.pop(get_tcgdex_client, None)


def test_mariadb_confirmation_rejected_with_stale_search_version(
    tmp_path: Path, monkeypatch
) -> None:
    """Test I: Confirmation rejected if candidate search version has changed.

    If user viewed candidates from search_version = 0, but another search
    completed in the meantime (search_version becomes 1), confirmation using
    expected_search_version = 0 must fail with HTTP 409 (STALE_SEARCH_VERSION).
    """
    storage_root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(storage_root))

    setup_db = TestingSessionLocal()
    img, _ = _create_synthetic_card_image(canvas_size=(800, 600))
    scan, _ = _setup_scan_in_db(setup_db, tmp_path, img)
    scan_id = str(scan.id)
    setup_db.close()

    corners = {
        "top_left": {"x": 0.34, "y": 0.20},
        "top_right": {"x": 0.66, "y": 0.20},
        "bottom_right": {"x": 0.66, "y": 0.80},
        "bottom_left": {"x": 0.34, "y": 0.80},
    }

    client = TestClient(app)
    r_crop = client.post(
        f"/api/v1/scans/{scan_id}/crop",
        json={"corners": corners, "rotation": 0, "expected_version": 0},
    )
    v1 = r_crop.json()["crop_version"]
    r_conf = client.post(
        f"/api/v1/scans/{scan_id}/confirm",
        json={"crop_version": v1},
    )
    confirmed_v = r_conf.json()["crop_version"]

    mock_client = AsyncMock()
    mock_client.get_cards_search.return_value = [
        {
            "id": "base1-58",
            "name": "Pikachu",
            "localId": "58",
            "set": {"id": "base1", "name": "Base Set", "cardCount": {"official": 102}},
        }
    ]
    mock_client.get_card.return_value = {
        "id": "base1-58",
        "name": "Pikachu",
        "localId": "58",
        "set": {"id": "base1", "name": "Base Set"},
    }
    app.dependency_overrides[get_tcgdex_client] = lambda: mock_client

    # Perform a search that advances search_version to 1
    s_res = client.post(
        f"/api/v1/scans/{scan_id}/search-candidates",
        json={
            "name": "Pikachu",
            "expected_crop_version": confirmed_v,
            "expected_search_version": 0,
        },
    )
    assert s_res.status_code == 200
    assert s_res.json()["search_version"] == 1

    # Attempt confirmation with stale expected_search_version = 0
    conf_res = client.post(
        f"/api/v1/scans/{scan_id}/confirm-card",
        json={
            "card_id": "base1-58",
            "expected_crop_version": confirmed_v,
            "expected_search_version": 0,
            "expected_selection_version": 0,
        },
    )
    assert conf_res.status_code == 409
    assert conf_res.json()["detail"]["code"] == "STALE_SEARCH_VERSION"

    # Confirmation with current expected_search_version = 1 succeeds
    conf_ok = client.post(
        f"/api/v1/scans/{scan_id}/confirm-card",
        json={
            "card_id": "base1-58",
            "expected_crop_version": confirmed_v,
            "expected_search_version": 1,
            "expected_selection_version": 0,
        },
    )
    assert conf_ok.status_code == 200
    assert conf_ok.json()["confirmed_card"]["id"] == "base1-58"
    app.dependency_overrides.pop(get_tcgdex_client, None)
