import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Scan(Base):
    """Scan database record for uploaded cards in Phase 3 and Phase 4."""

    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="uploaded",
        server_default="uploaded",
    )
    image_path: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="image/jpeg",
        server_default="image/jpeg",
    )
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=_utcnow,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
    )

    # Phase 4: Card detection, cropping, rotation, and confirmation
    crop_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="none",
        server_default="none",
    )
    corners: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
    )
    rotation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    crop_path: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )
    crop_width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    crop_height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    crop_file_size: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    crop_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        default=None,
    )

    # Phase 5: OCR recognition, candidate matching, and card confirmation
    recognition_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="none",
        server_default="none",
    )
    recognition_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        default=None,
    )
    ocr_crop_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    ocr_raw_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    recognition_evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recognized_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )
    recognized_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default=None,
    )
    recognized_set_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default=None,
    )
    ocr_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=None,
    )
    search_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    card_selection_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    catalog_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="none",
        server_default="none",
    )
    catalog_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    user_search_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )
    user_search_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default=None,
    )
    user_search_set_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default=None,
    )
    user_search_provider_set_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default=None,
    )
    candidate_matches: Mapped[list | dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
    )
    confirmed_card_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )
    confirmed_card_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )
    confirmed_card_set_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )
    confirmed_card_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default=None,
    )
    confirmed_card_image_url: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )
    card_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        default=None,
    )

    def __repr__(self) -> str:
        return (
            f"<Scan(id='{self.id}', status='{self.status}', "
            f"crop_status='{self.crop_status}', "
            f"size={self.width}x{self.height}, expires='{self.expires_at}')>"
        )
