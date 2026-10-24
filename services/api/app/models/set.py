from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.card import Card


class Set(Base):
    __tablename__ = "sets"
    __table_args__ = (
        UniqueConstraint(
            "source", "external_id", "language", name="uq_sets_source_external_lang"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="tcgdex", server_default="tcgdex"
    )
    external_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, default="en", server_default="en"
    )
    series: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    symbol_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    release_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    printed_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    cards: Mapped[list["Card"]] = relationship(
        back_populates="set",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Set(id={self.id}, external_id='{self.external_id}', name='{self.name}')>"
        )
