import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import SessionContext, get_session_context
from app.core.database import get_db
from app.models.feedback import ScanFeedback
from app.models.scan import Scan
from app.schemas.feedback import ScanFeedbackCreate, ScanFeedbackResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Scan Feedback"])


def _get_owned_scan(scan_id: str, session_ctx: SessionContext, db: Session) -> Scan:
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SCAN_NOT_FOUND", "message": "Scan niet gevonden"},
        )
    return scan


def _apply_feedback_values(
    feedback: ScanFeedback, feedback_in: ScanFeedbackCreate
) -> None:
    feedback.feedback_type = feedback_in.feedback_type
    feedback.suggested_card_id = feedback_in.suggested_card_id
    feedback.selected_card_id = feedback_in.selected_card_id
    feedback.confidence_state = feedback_in.confidence_state
    feedback.selected_in_candidates = feedback_in.selected_in_candidates
    feedback.notes = feedback_in.notes
    feedback.device_category = feedback_in.device_category


@router.post(
    "/scans/{scan_id}/feedback",
    response_model=ScanFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_scan_feedback(
    scan_id: str,
    feedback_in: ScanFeedbackCreate,
    session_ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> ScanFeedbackResponse:
    """Submit user or pilot feedback on a scan result with idempotency."""
    _get_owned_scan(scan_id, session_ctx, db)

    # Check for existing feedback for this scan and actor (idempotent upsert)
    query = db.query(ScanFeedback).filter(ScanFeedback.scan_id == scan_id)
    if session_ctx.is_authenticated:
        query = query.filter(ScanFeedback.user_id == session_ctx.user_id)
    else:
        query = query.filter(
            ScanFeedback.anonymous_session_id == session_ctx.session_id
        )

    existing = query.first()
    if existing:
        _apply_feedback_values(existing, feedback_in)
        db.commit()
        db.refresh(existing)
        return ScanFeedbackResponse.model_validate(existing)

    feedback = ScanFeedback(
        scan_id=scan_id,
        user_id=session_ctx.user_id if session_ctx.is_authenticated else None,
        anonymous_session_id=(
            None if session_ctx.is_authenticated else session_ctx.session_id
        ),
        feedback_type=feedback_in.feedback_type,
        suggested_card_id=feedback_in.suggested_card_id,
        selected_card_id=feedback_in.selected_card_id,
        confidence_state=feedback_in.confidence_state,
        selected_in_candidates=feedback_in.selected_in_candidates,
        notes=feedback_in.notes,
        device_category=feedback_in.device_category,
    )
    db.add(feedback)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request for the same scan and actor won the unique key.
        db.rollback()
        existing = query.first()
        if existing is None:
            raise
        _apply_feedback_values(existing, feedback_in)
        db.commit()
        feedback = existing
    db.refresh(feedback)

    return ScanFeedbackResponse.model_validate(feedback)


@router.get(
    "/scans/{scan_id}/feedback",
    response_model=ScanFeedbackResponse,
)
def get_scan_feedback(
    scan_id: str,
    session_ctx: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
) -> ScanFeedbackResponse:
    """Retrieve existing feedback for a scan."""
    _get_owned_scan(scan_id, session_ctx, db)
    query = db.query(ScanFeedback).filter(ScanFeedback.scan_id == scan_id)
    if session_ctx.is_authenticated:
        query = query.filter(ScanFeedback.user_id == session_ctx.user_id)
    else:
        query = query.filter(
            ScanFeedback.anonymous_session_id == session_ctx.session_id
        )

    feedback = query.first()
    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "FEEDBACK_NOT_FOUND",
                "message": "Geen feedback gevonden voor deze scan",
            },
        )

    return ScanFeedbackResponse.model_validate(feedback)
