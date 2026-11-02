import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.analytics import ProductAnalyticsEvent
from app.models.user import UserSession

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def cleanup_expired_analytics(
    db: Session,
    retention_days: int | None = None,
) -> int:
    """Purge product analytics events older than configured retention period."""
    if retention_days is None:
        retention_days = settings.ANALYTICS_RETENTION_DAYS

    cutoff = _utcnow() - timedelta(days=retention_days)
    logger.info("Purging product analytics events prior to %s", cutoff)

    deleted_count = (
        db.query(ProductAnalyticsEvent)
        .filter(ProductAnalyticsEvent.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    logger.info("Purged %d expired product analytics events", deleted_count)
    return deleted_count


def cleanup_expired_sessions(db: Session) -> int:
    """Purge expired user and anonymous pilot sessions."""
    now = _utcnow()
    deleted_count = (
        db.query(UserSession)
        .filter(UserSession.expires_at < now)
        .delete(synchronize_session=False)
    )
    db.commit()
    logger.info("Purged %d expired user sessions", deleted_count)
    return deleted_count
