import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class BetaCodeItem:
    id: str
    code: str
    code_prefix: str
    label: str | None
    invitation_email: str | None
    max_uses: int
    used_count: int
    status: str
    expires_at: datetime | None
    created_at: datetime
    created_by_user_id: str | None


class BetaServiceInterface(Protocol):
    """Interface contract consumed by Admin subsystem for beta code management."""

    def list_codes(
        self,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BetaCodeItem], int]: ...

    def create_code(
        self,
        code: str | None = None,
        label: str | None = None,
        invitation_email: str | None = None,
        max_uses: int = 1,
        expires_at: datetime | None = None,
        created_by_id: str | None = None,
    ) -> BetaCodeItem: ...

    def revoke_code(
        self,
        code_or_id: str,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> BetaCodeItem: ...

    def claim_code(
        self,
        code: str,
        user_id: str,
        ip_hash: str | None = None,
    ) -> bool: ...


class DefaultBetaService:
    """Production implementation interfacing with Beta domain tables or in-memory fallback."""

    # In-memory storage fallback when beta table is not present
    _mem_store: dict[str, BetaCodeItem] = {}

    def __init__(self, db: Session) -> None:
        self.db = db
        self._table_names: set[str] | None = None

    def _get_table_names(self) -> set[str]:
        if self._table_names is None:
            insp = inspect(self.db.bind)
            self._table_names = set(insp.get_table_names())
        return self._table_names

    def list_codes(
        self,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BetaCodeItem], int]:
        tables = self._get_table_names()
        if "beta_codes" in tables:
            query_sql = """
                SELECT id, code_prefix, label, is_active, max_uses, used_count,
                       allowed_email, expires_at, created_by_user_id, revoked_at,
                       created_at
                FROM beta_codes
                WHERE 1=1
            """
            params: dict[str, object] = {"lim": limit, "off": offset}
            if search:
                s_clean = search.strip()
                params["srch"] = f"%{s_clean}%"
                params["srch_p"] = f"{s_clean[:8]}%"
                query_sql += " AND (code_prefix LIKE :srch OR code_prefix LIKE :srch_p OR label LIKE :srch OR allowed_email LIKE :srch)"

            rows = self.db.execute(text(query_sql), params).fetchall()

            items: list[BetaCodeItem] = []
            now = _utcnow()
            for r in rows:
                code_id, prefix, lbl, is_act, m_uses, u_count, email, exp, creator, rev, created = r
                if rev or not is_act:
                    st = "revoked"
                elif exp and exp < now:
                    st = "expired"
                elif u_count >= m_uses:
                    st = "exhausted"
                else:
                    st = "active"

                if status and status != "all" and st != status:
                    continue

                items.append(
                    BetaCodeItem(
                        id=code_id,
                        code=f"{prefix}••••••••",
                        code_prefix=prefix,
                        label=lbl,
                        invitation_email=email,
                        max_uses=m_uses,
                        used_count=u_count,
                        status=st,
                        expires_at=exp,
                        created_at=created,
                        created_by_user_id=creator,
                    )
                )

            total = len(items)
            return items[offset : offset + limit], total

        # Fallback to in-memory store
        all_items = list(self._mem_store.values())
        if search:
            s = search.lower()
            all_items = [
                i for i in all_items
                if s in i.code.lower() or (i.label and s in i.label.lower()) or (i.invitation_email and s in i.invitation_email.lower())
            ]
        if status and status != "all":
            all_items = [i for i in all_items if i.status == status]

        total = len(all_items)
        return all_items[offset : offset + limit], total

    def create_code(
        self,
        code: str | None = None,
        label: str | None = None,
        invitation_email: str | None = None,
        max_uses: int = 1,
        expires_at: datetime | None = None,
        created_by_id: str | None = None,
    ) -> BetaCodeItem:
        if not code:
            code = f"BETA-{secrets.token_hex(4).upper()}"
        code = code.strip().upper()
        code_id = str(uuid.uuid4())
        prefix = code[:8]
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
        now = _utcnow()

        tables = self._get_table_names()
        if "beta_codes" in tables:
            self.db.execute(
                text(
                    """
                    INSERT INTO beta_codes
                    (id, code_hash, code_prefix, label, is_active, max_uses, used_count,
                     allowed_email, scan_quota_allocated, beta_entitlement, expires_at,
                     created_by_user_id, created_at, updated_at)
                    VALUES
                    (:id, :chash, :pref, :lbl, 1, :max_u, 0, :email, 100, 'standard', :exp, :creator, :now, :now)
                    """
                ),
                {
                    "id": code_id,
                    "chash": code_hash,
                    "pref": prefix,
                    "lbl": label or f"Invite {prefix}",
                    "max_u": max_uses,
                    "email": invitation_email.strip().lower() if invitation_email else None,
                    "exp": expires_at,
                    "creator": created_by_id,
                    "now": now,
                },
            )
            self.db.commit()

        item = BetaCodeItem(
            id=code_id,
            code=code,
            code_prefix=prefix,
            label=label or f"Invite {prefix}",
            invitation_email=invitation_email.strip().lower() if invitation_email else None,
            max_uses=max_uses,
            used_count=0,
            status="active",
            expires_at=expires_at,
            created_at=now,
            created_by_user_id=created_by_id,
        )
        self._mem_store[code_id] = item
        return item

    def revoke_code(
        self,
        code_or_id: str,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> BetaCodeItem:
        now = _utcnow()
        tables = self._get_table_names()

        if "beta_codes" in tables:
            clean_input = code_or_id.strip().upper()
            chash = hashlib.sha256(clean_input.encode("utf-8")).hexdigest()
            row = self.db.execute(
                text(
                    """
                    SELECT id, code_prefix, label, max_uses, used_count, allowed_email, expires_at, created_by_user_id, created_at
                    FROM beta_codes
                    WHERE id = :cid OR code_prefix = :cid OR code_hash = :chash
                    """
                ),
                {"cid": code_or_id, "chash": chash},
            ).first()

            if not row:
                raise ValueError(f"Beta code '{code_or_id}' not found")

            self.db.execute(
                text(
                    """
                    UPDATE beta_codes
                    SET is_active = 0, revoked_at = :now, revoked_by_user_id = :act, updated_at = :now
                    WHERE id = :id
                    """
                ),
                {"id": row[0], "now": now, "act": actor_id},
            )
            self.db.commit()

            return BetaCodeItem(
                id=row[0],
                code=f"{row[1]}••••••••",
                code_prefix=row[1],
                label=row[2],
                invitation_email=row[5],
                max_uses=row[3],
                used_count=row[4],
                status="revoked",
                expires_at=row[6],
                created_at=row[8],
                created_by_user_id=row[7],
            )

        if code_or_id in self._mem_store:
            item = self._mem_store[code_or_id]
            item.status = "revoked"
            return item

        raise ValueError(f"Beta code '{code_or_id}' not found")

    def claim_code(
        self,
        code: str,
        user_id: str,
        ip_hash: str | None = None,
    ) -> bool:
        clean = code.strip().upper()
        chash = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        tables = self._get_table_names()
        now = _utcnow()

        if "beta_codes" in tables:
            row = self.db.execute(
                text(
                    """
                    SELECT id, is_active, max_uses, used_count, expires_at, revoked_at
                    FROM beta_codes
                    WHERE code_hash = :chash
                    """
                ),
                {"chash": chash},
            ).first()

            if not row:
                return False

            cid, is_act, m_uses, u_count, exp, rev = row
            if rev or not is_act or (exp and exp < now) or (u_count >= m_uses):
                return False

            self.db.execute(
                text("UPDATE beta_codes SET used_count = used_count + 1 WHERE id = :id"),
                {"id": cid},
            )
            if "beta_code_redemptions" in tables:
                self.db.execute(
                    text(
                        """
                        INSERT INTO beta_code_redemptions (id, beta_code_id, user_id, redeemed_at, ip_hash)
                        VALUES (:id, :bcid, :uid, :now, :iph)
                        """
                    ),
                    {"id": str(uuid.uuid4()), "bcid": cid, "uid": user_id, "now": now, "iph": ip_hash},
                )
            self.db.commit()
            return True

        for item in self._mem_store.values():
            if item.code.upper() == clean and item.status == "active":
                item.used_count += 1
                if item.used_count >= item.max_uses:
                    item.status = "exhausted"
                return True
        return False
