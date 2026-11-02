import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import (
    SessionContext,
    get_session_context,
    require_admin_or_pilot_secret,
)
from app.core.database import get_db
from app.models.analytics import ProductAnalyticsEvent
from app.models.feedback import ScanFeedback
from app.models.scan import Scan
from app.models.scan_session import ScanSession
from app.schemas.analytics import (
    AnalyticsEventResponse,
    PilotSummaryMetrics,
    ProductAnalyticsEventCreate,
)
from app.services.auth import pseudonymize_identifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Product Analytics"])


@router.post(
    "/events",
    response_model=AnalyticsEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def track_event(
    event_in: ProductAnalyticsEventCreate,
    session_ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> AnalyticsEventResponse:
    """Ingest an allowlisted, privacy-safe product analytics event."""
    if event_in.scan_id:
        scan = db.query(Scan).filter(Scan.id == event_in.scan_id).first()
        owns_scan = scan is not None and (
            (
                session_ctx.user_id is not None
                and scan.user_id == session_ctx.user_id
                and scan.anonymous_session_id is None
            )
            or (
                session_ctx.anonymous_session_id is not None
                and scan.anonymous_session_id == session_ctx.anonymous_session_id
                and scan.user_id is None
            )
        )
        if not owns_scan:
            raise HTTPException(
                status_code=404,
                detail={"code": "SCAN_NOT_FOUND", "message": "Scan not found"},
            )

    analytics_session_id = None
    if event_in.session_id:
        scan_session = (
            db.query(ScanSession).filter(ScanSession.id == event_in.session_id).first()
        )
        owns_session = scan_session is not None and (
            (
                session_ctx.user_id is not None
                and scan_session.user_id == session_ctx.user_id
                and scan_session.anonymous_session_id is None
            )
            or (
                session_ctx.anonymous_session_id is not None
                and scan_session.anonymous_session_id
                == session_ctx.anonymous_session_id
                and scan_session.user_id is None
            )
        )
        if not owns_session:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "SCAN_SESSION_NOT_FOUND",
                    "message": "Scan session not found",
                },
            )
        analytics_session_id = event_in.session_id

    actor_type = "auth" if session_ctx.is_authenticated else "anon"
    raw_actor_id = (
        session_ctx.user_id if session_ctx.is_authenticated else session_ctx.session_id
    )
    actor_id = pseudonymize_identifier(raw_actor_id)

    metadata_str = None
    if event_in.metadata:
        metadata_str = json.dumps(event_in.metadata)

    event_record = ProductAnalyticsEvent(
        event_name=event_in.event_name,
        schema_version=event_in.schema_version,
        actor_type=actor_type,
        actor_id=actor_id,
        session_id=analytics_session_id,
        scan_id=event_in.scan_id,
        timestamp=datetime.now(UTC).replace(tzinfo=None),
        capture_mode=event_in.capture_mode,
        device_category=event_in.device_category,
        browser_category=event_in.browser_category,
        viewport_category=event_in.viewport_category,
        processing_duration_ms=event_in.processing_duration_ms,
        confidence_state=event_in.confidence_state,
        candidate_count=event_in.candidate_count,
        is_top_suggestion_selected=event_in.is_top_suggestion_selected,
        failure_category=event_in.failure_category,
        metadata_json=metadata_str,
    )
    db.add(event_record)
    db.commit()
    db.refresh(event_record)

    return AnalyticsEventResponse(
        id=event_record.id,
        event_name=event_record.event_name,
        created_at=event_record.created_at,
    )


@router.get(
    "/admin/summary",
    response_model=PilotSummaryMetrics,
    dependencies=[Depends(require_admin_or_pilot_secret)],
)
def get_pilot_summary_metrics(
    db: Session = Depends(get_db),
) -> PilotSummaryMetrics:
    """Retrieve aggregated pilot diagnostics metrics without PII."""
    # Total scans
    total_scans_event = (
        db.query(
            func.count(
                func.distinct(
                    func.coalesce(
                        ProductAnalyticsEvent.scan_id,
                        ProductAnalyticsEvent.session_id,
                        ProductAnalyticsEvent.id,
                    )
                )
            )
        )
        .filter(ProductAnalyticsEvent.event_name == "scan_started")
        .scalar()
        or 0
    )
    total_scans_db = db.query(func.count(Scan.id)).scalar() or 0
    total_scans = max(total_scans_event, total_scans_db)

    # Completed scans
    completed_events = (
        db.query(
            func.count(
                func.distinct(
                    func.coalesce(
                        ProductAnalyticsEvent.scan_id,
                        ProductAnalyticsEvent.id,
                    )
                )
            )
        )
        .filter(ProductAnalyticsEvent.event_name == "scan_processing_completed")
        .scalar()
        or 0
    )
    completion_rate = (
        min(completed_events / total_scans, 1.0) if total_scans > 0 else 0.0
    )

    # Top-candidate acceptance rate & corrections
    confirmed_events = (
        db.query(ProductAnalyticsEvent)
        .filter(ProductAnalyticsEvent.event_name == "card_confirmed")
        .order_by(ProductAnalyticsEvent.timestamp.asc(), ProductAnalyticsEvent.id.asc())
        .all()
    )
    latest_confirmed_by_scan: dict[str, ProductAnalyticsEvent] = {}
    for event in confirmed_events:
        key = event.scan_id or event.id
        latest_confirmed_by_scan[key] = event
    distinct_confirmed_events = list(latest_confirmed_by_scan.values())
    total_confirmed = len(distinct_confirmed_events)
    top_selected = sum(
        1 for e in distinct_confirmed_events if e.is_top_suggestion_selected is True
    )
    top_candidate_acceptance_rate = (
        (top_selected / total_confirmed) if total_confirmed > 0 else 0.0
    )

    corrected_events_count = (
        db.query(
            func.count(
                func.distinct(
                    func.coalesce(
                        ProductAnalyticsEvent.scan_id,
                        ProductAnalyticsEvent.id,
                    )
                )
            )
        )
        .filter(ProductAnalyticsEvent.event_name == "top_candidate_corrected")
        .scalar()
        or 0
    )
    candidate_correction_rate = (
        min(corrected_events_count / total_confirmed, 1.0)
        if total_confirmed > 0
        else 0.0
    )

    # Processing durations
    durations_rows = (
        db.query(ProductAnalyticsEvent.processing_duration_ms)
        .filter(
            ProductAnalyticsEvent.event_name == "scan_processing_completed",
            ProductAnalyticsEvent.processing_duration_ms.isnot(None),
        )
        .all()
    )
    durations = sorted(r[0] for r in durations_rows if r[0] is not None)
    median_duration = None
    p95_duration = None
    if durations:
        n = len(durations)
        median_duration = float(durations[n // 2])
        p95_idx = int(n * 0.95)
        p95_duration = float(durations[min(p95_idx, n - 1)])

    # Capture mode distribution
    mode_rows = (
        db.query(
            ProductAnalyticsEvent.capture_mode,
            func.count(ProductAnalyticsEvent.id),
        )
        .filter(ProductAnalyticsEvent.capture_mode.isnot(None))
        .group_by(ProductAnalyticsEvent.capture_mode)
        .all()
    )
    capture_mode_distribution = {
        row[0]: row[1] for row in mode_rows if row[0] is not None
    }

    # Failure categories
    failure_rows = (
        db.query(
            ProductAnalyticsEvent.failure_category,
            func.count(ProductAnalyticsEvent.id),
        )
        .filter(ProductAnalyticsEvent.failure_category.isnot(None))
        .group_by(ProductAnalyticsEvent.failure_category)
        .all()
    )
    failure_categories = {row[0]: row[1] for row in failure_rows if row[0] is not None}

    # Feedback stats
    feedback_rows = (
        db.query(
            ScanFeedback.feedback_type,
            func.count(ScanFeedback.id),
        )
        .group_by(ScanFeedback.feedback_type)
        .all()
    )
    feedback_breakdown = {row[0]: row[1] for row in feedback_rows}
    total_feedback_count = sum(feedback_breakdown.values())

    return PilotSummaryMetrics(
        total_scans=total_scans,
        completion_rate=round(completion_rate, 4),
        top_candidate_acceptance_rate=round(top_candidate_acceptance_rate, 4),
        candidate_correction_rate=round(candidate_correction_rate, 4),
        processing_duration_median_ms=median_duration,
        processing_duration_p95_ms=p95_duration,
        capture_mode_distribution=capture_mode_distribution,
        failure_categories=failure_categories,
        total_feedback_count=total_feedback_count,
        feedback_breakdown=feedback_breakdown,
    )
