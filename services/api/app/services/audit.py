import json
import logging
from typing import Any

from fastapi import Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit import AdminAuditLog
from app.models.user import User
from app.services.auth import hash_ip
from app.services.turnstile import TurnstileService

logger = logging.getLogger(__name__)

SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "hash",
    "credential",
    "cookie",
    "authorization",
)


def sanitize_audit_metadata(data: Any) -> Any:
    """Recursively scrub secrets, tokens, password hashes, and credentials from metadata."""
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS):
                continue
            cleaned[k] = sanitize_audit_metadata(v)
        return cleaned
    elif isinstance(data, list):
        return [sanitize_audit_metadata(item) for item in data]
    return data


class AuditService:
    """Append-only audit service for tracking administrative operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def log_action(
        self,
        action: str,
        target_type: str,
        target_id: str | None = None,
        actor: User | None = None,
        metadata: dict[str, Any] | None = None,
        request: Request | None = None,
    ) -> AdminAuditLog:
        """Create and persist an append-only audit event."""
        sanitized_metadata = sanitize_audit_metadata(metadata) if metadata else None
        metadata_json = (
            json.dumps(sanitized_metadata, separators=(",", ":"), default=str)
            if sanitized_metadata
            else None
        )

        ip_hash = None
        if request:
            client_ip = TurnstileService.get_trusted_client_ip(request)
            ip_hash = hash_ip(client_ip)

        audit_entry = AdminAuditLog(
            actor_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            metadata_json=metadata_json,
            ip_hash=ip_hash,
        )

        self.db.add(audit_entry)
        self.db.commit()
        self.db.refresh(audit_entry)
        logger.info(
            "Admin audit logged: actor=%s action=%s target=%s:%s",
            audit_entry.actor_email or "system",
            action,
            target_type,
            target_id,
        )
        return audit_entry

    def list_logs(
        self,
        actor_id: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AdminAuditLog], int]:
        """Query append-only audit logs with filters and pagination."""
        query = self.db.query(AdminAuditLog)

        if actor_id:
            query = query.filter(AdminAuditLog.actor_id == actor_id)
        if action:
            query = query.filter(AdminAuditLog.action == action)
        if target_type:
            query = query.filter(AdminAuditLog.target_type == target_type)
        if target_id:
            query = query.filter(AdminAuditLog.target_id == target_id)

        total = query.with_entities(func.count(AdminAuditLog.id)).scalar() or 0
        items = (
            query.order_by(AdminAuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total
