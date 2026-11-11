import logging
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.collection import CollectionItem
from app.models.scan import Scan
from app.models.user import User, UserSession
from app.services.audit import AuditService
from app.services.quota_service import DefaultQuotaService, QuotaServiceInterface

logger = logging.getLogger(__name__)


class AdminService:
    """Core administrative service managing user state, security controls, and audit trails."""

    def __init__(
        self,
        db: Session,
        audit_service: AuditService | None = None,
        quota_service: QuotaServiceInterface | None = None,
    ) -> None:
        self.db = db
        self.audit = audit_service or AuditService(db)
        self.quota = quota_service or DefaultQuotaService(db)

    def list_users(
        self,
        q: str | None = None,
        status_filter: str | None = None,
        role_filter: str | None = None,
        verification_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """Lookup and filter users without exposing password hashes or raw secrets."""
        query = self.db.query(User)

        if q:
            clean_q = q.strip().lower()
            query = query.filter(
                (func.lower(User.email).like(f"%{clean_q}%"))
                | (User.id == clean_q)
            )
        if status_filter and status_filter != "all":
            query = query.filter(User.status == status_filter)
        if role_filter and role_filter != "all":
            query = query.filter(User.role == role_filter)
        if verification_filter and verification_filter != "all":
            query = query.filter(User.verification_status == verification_filter)

        total = query.with_entities(func.count(User.id)).scalar() or 0
        users = (
            query.order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return users, total

    def get_user_details(self, user_id: str) -> dict[str, Any]:
        """Fetch rich user profile, quotas, and recent activity metrics."""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "USER_NOT_FOUND", "message": "Gebruiker niet gevonden"},
            )

        scans_count = self.db.query(Scan).filter(Scan.user_id == user.id).count()
        sessions_count = (
            self.db.query(UserSession)
            .filter(UserSession.user_id == user.id)
            .count()
        )
        items_count = (
            self.db.query(CollectionItem)
            .filter(CollectionItem.user_id == user.id)
            .count()
        )
        quota_info = self.quota.get_user_quota(user.id)
        recent_logs, _ = self.audit.list_logs(
            target_type="user",
            target_id=user.id,
            limit=10,
        )

        return {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "status": user.status,
            "is_active": user.is_active,
            "verification_status": user.verification_status,
            "scan_quota_override": user.scan_quota_override,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "scans_count": scans_count,
            "active_sessions_count": sessions_count,
            "collection_items_count": items_count,
            "quota": {
                "effective_daily_limit": quota_info.effective_daily_limit,
                "custom_override": quota_info.custom_override,
                "scans_used_today": quota_info.scans_used_today,
                "remaining_today": quota_info.remaining_today,
                "reason": quota_info.reason,
            },
            "recent_audit_events": [
                {
                    "id": log.id,
                    "action": log.action,
                    "actor_email": log.actor_email,
                    "created_at": log.created_at,
                    "metadata": log.metadata_json,
                }
                for log in recent_logs
            ],
        }

    def update_user_status(
        self,
        user_id: str,
        new_status: str,
        reason: str,
        actor: User,
        request: Request | None = None,
    ) -> User:
        """Activate, suspend, or block user with confirmation metadata and session termination."""
        valid_statuses = {"active", "suspended", "blocked"}
        if new_status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_STATUS",
                    "message": f"Ongeldige status. Kies uit: {', '.join(valid_statuses)}",
                },
            )

        if not reason or len(reason.strip()) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "REASON_REQUIRED",
                    "message": "Een toelichting van minimaal 3 tekens is verplicht voor deze actie.",
                },
            )

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "USER_NOT_FOUND", "message": "Gebruiker niet gevonden"},
            )

        # Prevent admin self-suspension/blocking to safeguard admin access
        if user.id == actor.id and new_status in ("suspended", "blocked"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "CANNOT_MODIFY_SELF",
                    "message": "Het is niet toegestaan om je eigen beheerdersaccount te deactiveren of blokkeren.",
                },
            )

        old_status = user.status
        user.status = new_status
        user.is_active = (new_status == "active")

        # Invalidate all active sessions if user is suspended or blocked
        terminated_sessions = 0
        if new_status in ("suspended", "blocked"):
            terminated_sessions = (
                self.db.query(UserSession)
                .filter(UserSession.user_id == user.id)
                .delete(synchronize_session=False)
            )

        self.db.commit()
        self.db.refresh(user)

        # Log append-only audit event
        self.audit.log_action(
            action=f"user.{new_status}",
            target_type="user",
            target_id=user.id,
            actor=actor,
            metadata={
                "old_status": old_status,
                "new_status": new_status,
                "reason": reason.strip(),
                "terminated_sessions": terminated_sessions,
            },
            request=request,
        )

        return user

    def update_user_quota_override(
        self,
        user_id: str,
        custom_limit: int | None,
        reason: str,
        actor: User,
        request: Request | None = None,
    ) -> User:
        """View and change per-user scan quota overrides."""
        if custom_limit is not None and custom_limit < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_QUOTA",
                    "message": "Scan quota kan niet negatief zijn.",
                },
            )

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "USER_NOT_FOUND", "message": "Gebruiker niet gevonden"},
            )

        old_override = user.scan_quota_override
        self.quota.set_user_quota_override(
            user_id=user.id,
            custom_limit=custom_limit,
            actor_id=actor.id,
            reason=reason,
        )

        user.scan_quota_override = custom_limit
        self.db.commit()
        self.db.refresh(user)

        self.audit.log_action(
            action="user.quota_override",
            target_type="user",
            target_id=user.id,
            actor=actor,
            metadata={
                "old_override": old_override,
                "new_override": custom_limit,
                "reason": reason.strip(),
            },
            request=request,
        )

        return user
