from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AppSetting(Base):
    """Persistent key-value system settings stored in the database.

    Used for multi-worker coordinated settings such as registration mode.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<AppSetting key={self.key!r} value={self.value!r}>"
