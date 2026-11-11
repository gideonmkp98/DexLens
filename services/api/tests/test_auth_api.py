import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.collection import CollectionItem
from app.models.scan import Scan
from app.models.user import User


def test_register_success_sets_session_cookie(client: TestClient, db: Session):
    email = f"pilot_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "password": "DexLensUnpwnedPassword2026!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == email
    assert data["role"] == "user"
    assert "id" in data

    # Verify session cookie was set
    cookie = response.cookies.get("dexlens_session")
    assert cookie is not None

    # Verify user in database has argon2id hash and NOT plaintext
    db_user = db.query(User).filter(User.email == email).first()
    assert db_user is not None
    assert db_user.password_hash.startswith("$argon2id$")
    assert "DexLensUnpwnedPassword2026!" not in db_user.password_hash


def test_register_duplicate_email_fails(client: TestClient):
    email = f"duplicate_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "password": "DexLensUnpwnedPassword2026!",
    }
    res1 = client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    # Second attempt with same email
    res2 = client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 400
    assert res2.json()["detail"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_register_short_password_fails(client: TestClient):
    payload = {
        "email": "short_pw@example.com",
        "password": "short",
        "display_name": "Short PW",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_login_success_and_logout(client: TestClient):
    email = f"login_{uuid.uuid4().hex[:8]}@example.com"
    password = "CorrectPassword123!"
    register_payload = {
        "email": email,
        "password": password,
        "display_name": "Login Tester",
    }
    reg_res = client.post("/api/v1/auth/register", json=register_payload)
    assert reg_res.status_code == 201

    # Clear cookies to simulate fresh login
    client.cookies.clear()

    # Login
    login_payload = {"email": email, "password": password}
    login_res = client.post("/api/v1/auth/login", json=login_payload)
    assert login_res.status_code == 200
    assert login_res.cookies.get("dexlens_session") is not None
    user_data = login_res.json()
    assert user_data["email"] == email

    # /auth/me returns authenticated
    me_res = client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["is_authenticated"] is True
    assert me_data["user"]["email"] == email

    # Logout
    logout_res = client.post("/api/v1/auth/logout")
    assert logout_res.status_code == 200

    # /auth/me after logout returns unauthenticated
    me_after = client.get("/api/v1/auth/me")
    assert me_after.status_code == 200
    assert me_after.json()["is_authenticated"] is False
    assert me_after.json()["user"] is None


def test_login_invalid_credentials(client: TestClient):
    email = f"invalid_{uuid.uuid4().hex[:8]}@example.com"
    password = "CorrectPassword123!"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    client.cookies.clear()

    # Wrong password
    bad_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword999!"},
    )
    assert bad_res.status_code == 401
    assert bad_res.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    # Non-existent email
    bad_res2 = client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent_email_12345@example.com", "password": password},
    )
    assert bad_res2.status_code == 401
    assert bad_res2.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_me_endpoint_provisions_anonymous_session(client: TestClient):
    client.cookies.clear()
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 200
    data = res.json()
    assert data["is_authenticated"] is False
    assert data["user"] is None
    assert data["session_id"] is not None
    assert data["session_type"] == "anonymous"
    assert res.cookies.get("dexlens_session") is not None


def test_claim_anonymous_session(client: TestClient, db: Session):
    client.cookies.clear()

    # 1. Establish anonymous session
    me_res = client.get("/api/v1/auth/me")
    anon_session_id = me_res.json()["session_id"]
    anon_cookie = me_res.cookies.get("dexlens_session")
    assert anon_session_id is not None
    assert anon_cookie is not None

    # 2. Create collection item and scan associated with anonymous session
    col_item = CollectionItem(
        id=str(uuid.uuid4()),
        user_id=None,
        anonymous_session_id=anon_session_id,
        card_id="base1-4",
        set_id="base1",
        collector_number="4",
        card_name="Charizard",
        set_name="Base Set",
        quantity=1,
        condition="near_mint",
        variant="holo",
        language="en",
        version=1,
    )
    scan_item = Scan(
        id=str(uuid.uuid4()),
        user_id=None,
        anonymous_session_id=anon_session_id,
        status="confirmed",
        image_path="/app/uploads/scans/anon_test.jpg",
        content_type="image/jpeg",
        width=800,
        height=1100,
        file_size=150000,
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2),
    )
    db.add(col_item)
    db.add(scan_item)
    db.commit()

    # 3. Create a registered user on a fresh client session
    user_client = TestClient(client.app)
    user_email = f"claimer_{uuid.uuid4().hex[:8]}@example.com"
    reg_res = user_client.post(
        "/api/v1/auth/register",
        json={
            "email": user_email,
            "password": "ClaimerPassword123!",
        },
    )
    assert reg_res.status_code == 201
    user_id = reg_res.json()["id"]

    # 4. User claims the anonymous session
    claim_res = user_client.post(
        "/api/v1/auth/claim-anonymous-session",
        json={
            "anonymous_session_id": anon_session_id,
            "anonymous_session_token": anon_cookie,
        },
    )
    assert claim_res.status_code == 200
    claim_data = claim_res.json()
    assert claim_data["claimed_items_count"] >= 1
    assert "succesvol" in claim_data["message"]

    # 5. Verify records in DB now belong to user_id
    db.refresh(col_item)
    db.refresh(scan_item)
    assert col_item.user_id == user_id
    assert col_item.anonymous_session_id is None
    assert scan_item.user_id == user_id
    assert scan_item.anonymous_session_id is None

    # 6. The one-time proof is invalid after the source session is consumed.
    claim_again = user_client.post(
        "/api/v1/auth/claim-anonymous-session",
        json={
            "anonymous_session_id": anon_session_id,
            "anonymous_session_token": anon_cookie,
        },
    )
    assert claim_again.status_code == 403
    assert claim_again.json()["detail"]["code"] == "INVALID_CLAIM_PROOF"


def test_register_immediately_makes_me_authenticated(client: TestClient):
    client.cookies.clear()
    # 1. Start as anonymous visitor
    me_anon = client.get("/api/v1/auth/me")
    assert me_anon.status_code == 200
    assert me_anon.json()["is_authenticated"] is False
    assert me_anon.json()["session_type"] == "anonymous"

    # 2. Register
    email = f"immediate_me_{uuid.uuid4().hex[:8]}@example.com"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "ImmediateAuthPassword123!"},
    )
    assert reg_res.status_code == 201
    assert "dexlens_session" in reg_res.cookies

    # 3. Immediately query /auth/me with same client session
    me_auth = client.get("/api/v1/auth/me")
    assert me_auth.status_code == 200
    data = me_auth.json()
    assert data["is_authenticated"] is True
    assert data["session_type"] == "authenticated"
    assert data["user"] is not None
    assert data["user"]["email"] == email


def test_register_auto_claims_anonymous_collection_and_scans(
    client: TestClient, db: Session
):
    client.cookies.clear()
    # 1. Establish anonymous session
    me_res = client.get("/api/v1/auth/me")
    anon_session_id = me_res.json()["session_id"]
    anon_cookie = me_res.cookies.get("dexlens_session")
    assert anon_session_id is not None
    assert anon_cookie is not None

    # 2. Add an anonymous collection item and scan
    col_item = CollectionItem(
        id=str(uuid.uuid4()),
        user_id=None,
        anonymous_session_id=anon_session_id,
        card_id="base1-58",
        set_id="base1",
        collector_number="58",
        card_name="Pikachu",
        set_name="Base Set",
        quantity=2,
        condition="near_mint",
        variant="normal",
        language="en",
        version=1,
    )
    scan_item = Scan(
        id=str(uuid.uuid4()),
        user_id=None,
        anonymous_session_id=anon_session_id,
        status="confirmed",
        image_path="/app/uploads/scans/pika_anon.jpg",
        content_type="image/jpeg",
        width=800,
        height=1100,
        file_size=120000,
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2),
    )
    db.add(col_item)
    db.add(scan_item)
    db.commit()

    # 3. Register on the same client that holds the anonymous session cookie
    user_email = f"autoclaim_reg_{uuid.uuid4().hex[:8]}@example.com"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": user_email, "password": "AutoClaimPassword123!"},
    )
    assert reg_res.status_code == 201
    user_id = reg_res.json()["id"]

    # 4. Verify DB items were claimed automatically
    db.refresh(col_item)
    db.refresh(scan_item)
    assert col_item.user_id == user_id
    assert col_item.anonymous_session_id is None
    assert scan_item.user_id == user_id
    assert scan_item.anonymous_session_id is None

    # 5. Verify the old anonymous session cannot be claimed again
    claim_again = client.post(
        "/api/v1/auth/claim-anonymous-session",
        json={
            "anonymous_session_id": anon_session_id,
            "anonymous_session_token": anon_cookie,
        },
    )
    assert claim_again.status_code == 403


def test_login_auto_claims_anonymous_collection_and_scans(
    client: TestClient, db: Session
):
    # 1. Pre-register a user on a separate client
    pre_client = TestClient(client.app)
    user_email = f"autoclaim_login_{uuid.uuid4().hex[:8]}@example.com"
    password = "PreExistingPassword123!"
    reg_res = pre_client.post(
        "/api/v1/auth/register",
        json={"email": user_email, "password": password},
    )
    assert reg_res.status_code == 201
    user_id = reg_res.json()["id"]

    # 2. Main client is an anonymous visitor with items
    client.cookies.clear()
    me_res = client.get("/api/v1/auth/me")
    anon_session_id = me_res.json()["session_id"]
    anon_cookie = me_res.cookies.get("dexlens_session")

    col_item = CollectionItem(
        id=str(uuid.uuid4()),
        user_id=None,
        anonymous_session_id=anon_session_id,
        card_id="base1-4",
        set_id="base1",
        collector_number="4",
        card_name="Charizard",
        set_name="Base Set",
        quantity=1,
        condition="near_mint",
        variant="holo",
        language="en",
        version=1,
    )
    db.add(col_item)
    db.commit()

    # 3. Main client logs in
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": password},
    )
    assert login_res.status_code == 200

    # 4. Verify item was claimed
    db.refresh(col_item)
    assert col_item.user_id == user_id
    assert col_item.anonymous_session_id is None

    # 5. Old anonymous cookie cannot be claimed
    claim_again = client.post(
        "/api/v1/auth/claim-anonymous-session",
        json={
            "anonymous_session_id": anon_session_id,
            "anonymous_session_token": anon_cookie,
        },
    )
    assert claim_again.status_code == 403
