import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User, UserSession
from app.services.admin import AdminService
from app.services.audit import AuditService
from app.services.auth import AuthService
from app.services.beta_service import DefaultBetaService
from app.services.quota_service import DefaultQuotaService


@pytest.fixture
def admin_service(db: Session) -> AdminService:
    return AdminService(db)


@pytest.fixture
def test_admin_user(db: Session) -> User:
    auth = AuthService(db)
    admin = auth.register_user("admin-test@example.com", "AdminPass1234!", role="admin")
    return admin


@pytest.fixture
def test_regular_user(db: Session) -> User:
    auth = AuthService(db)
    user = auth.register_user("collector-test@example.com", "UserPass1234!", role="user")
    return user


def test_user_lookup_and_filtering(
    db: Session,
    admin_service: AdminService,
    test_admin_user: User,
    test_regular_user: User,
):
    users, total = admin_service.list_users(q="collector-test")
    assert total == 1
    assert users[0].email == "collector-test@example.com"
    assert users[0].status == "active"

    # Filter by role
    admins, total_admins = admin_service.list_users(role_filter="admin")
    assert total_admins == 1
    assert admins[0].email == "admin-test@example.com"


def test_user_status_transitions_and_session_invalidation(
    db: Session,
    admin_service: AdminService,
    test_admin_user: User,
    test_regular_user: User,
):
    auth = AuthService(db)
    # Create active sessions for regular user
    session, token = auth.create_session(user_id=test_regular_user.id)
    assert auth.get_session(token) is not None

    # Suspend user
    admin_service.update_user_status(
        user_id=test_regular_user.id,
        new_status="suspended",
        reason="Suspicious bot activity detected",
        actor=test_admin_user,
    )

    db.refresh(test_regular_user)
    assert test_regular_user.status == "suspended"
    assert not test_regular_user.is_active

    # Active session MUST be deleted/invalidated
    assert auth.get_session(token) is None

    # Audit log entry must exist
    audit = AuditService(db)
    logs, count = audit.list_logs(target_type="user", target_id=test_regular_user.id)
    assert count >= 1
    assert logs[0].action == "user.suspended"
    assert "Suspicious bot activity" in logs[0].metadata_json

    # Reactivate user
    admin_service.update_user_status(
        user_id=test_regular_user.id,
        new_status="active",
        reason="User verified identity via support",
        actor=test_admin_user,
    )
    db.refresh(test_regular_user)
    assert test_regular_user.status == "active"
    assert test_regular_user.is_active


def test_admin_cannot_self_suspend(
    db: Session,
    admin_service: AdminService,
    test_admin_user: User,
):
    with pytest.raises(HTTPException) as exc_info:
        admin_service.update_user_status(
            user_id=test_admin_user.id,
            new_status="suspended",
            reason="Accidental self-lockout",
            actor=test_admin_user,
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "CANNOT_MODIFY_SELF"


def test_per_user_scan_quota_override(
    db: Session,
    admin_service: AdminService,
    test_admin_user: User,
    test_regular_user: User,
):
    admin_service.update_user_quota_override(
        user_id=test_regular_user.id,
        custom_limit=500,
        reason="Power collector tier upgrade",
        actor=test_admin_user,
    )

    db.refresh(test_regular_user)
    assert test_regular_user.scan_quota_override == 500

    details = admin_service.get_user_details(test_regular_user.id)
    assert details["quota"]["custom_override"] == 500
    assert details["quota"]["effective_daily_limit"] == 500

    # Reset override
    admin_service.update_user_quota_override(
        user_id=test_regular_user.id,
        custom_limit=None,
        reason="Revert to standard tier",
        actor=test_admin_user,
    )
    db.refresh(test_regular_user)
    assert test_regular_user.scan_quota_override is None


def test_global_quota_management(db: Session):
    quota_svc = DefaultQuotaService(db)
    current = quota_svc.get_global_quota()
    assert current.daily_scan_limit > 0

    updated = quota_svc.update_global_quota(
        daily_limit=250,
        hourly_limit=50,
        actor_id="admin-123",
        reason="Community beta burst allowance",
    )
    assert updated.daily_scan_limit == 250
    assert updated.hourly_scan_limit == 50


def test_beta_service_lifecycle(db: Session, test_admin_user: User):
    beta_svc = DefaultBetaService(db)

    # Create beta code
    code_item = beta_svc.create_code(
        code="TEST-BETA-2026",
        label="Influencer batch",
        max_uses=2,
        created_by_id=test_admin_user.id,
    )
    assert code_item.code == "TEST-BETA-2026"
    assert code_item.status == "active"

    # List codes
    codes, total = beta_svc.list_codes(search="TEST-BETA")
    assert total >= 1

    # Claim code with valid user
    claimed = beta_svc.claim_code(code="TEST-BETA-2026", user_id=test_admin_user.id)
    assert claimed

    # Revoke code
    revoked = beta_svc.revoke_code(code_or_id="TEST-BETA-2026", actor_id=test_admin_user.id)
    assert revoked.status == "revoked"

    # Cannot claim revoked code
    claimed_after = beta_svc.claim_code(code="TEST-BETA-2026", user_id=test_admin_user.id)
    assert not claimed_after
