import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.card import Card
from app.models.import_run import ImportRun
from app.models.set import Set
from app.services.tcgdex import TcgdexClient, TcgdexError, is_digital_set

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    scope: str
    status: str  # "succeeded", "partially_failed", "failed"
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)
    import_run_id: int | None = None

    @property
    def is_successful(self) -> bool:
        return self.status == "succeeded"


class CardImporter:
    """Service to import and synchronize Pokémon cards and sets from TCGdex."""

    def __init__(self, client: TcgdexClient | None = None) -> None:
        self.client = client or TcgdexClient()

    def _create_import_run(self, db: Session, scope: str, language: str) -> ImportRun:
        run = ImportRun(
            source="tcgdex",
            language=language,
            scope=scope,
            started_at=datetime.now(UTC),
            status="running",
            created_count=0,
            updated_count=0,
            skipped_count=0,
            failed_count=0,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def _persist_run_completion(
        self,
        run_id: int,
        status: str,
        created: int,
        updated: int,
        skipped: int,
        failed: int,
        error_summary: str | None,
    ) -> None:
        """Persist import run results in a dedicated transaction."""
        db = SessionLocal()
        try:
            run = db.query(ImportRun).filter(ImportRun.id == run_id).first()
            if run:
                run.finished_at = datetime.now(UTC)
                run.status = status
                run.created_count = created
                run.updated_count = updated
                run.skipped_count = skipped
                run.failed_count = failed
                run.error_summary = error_summary
                db.commit()
        except Exception as err:
            logger.error("Failed to persist import_run record %d: %s", run_id, err)
            db.rollback()
        finally:
            db.close()

    async def import_set(self, set_id: str, language: str = "en") -> ImportResult:
        """Import a single set and its card summaries into the minimal local index."""
        if language not in settings.SUPPORTED_LANGUAGES:
            msg = (
                f"Unsupported language '{language}'. "
                f"Supported languages: {', '.join(settings.SUPPORTED_LANGUAGES)}"
            )
            return ImportResult(scope=f"set:{set_id}", status="failed", errors=[msg])

        scope = f"set:{set_id}"
        db = SessionLocal()
        run = self._create_import_run(db, scope, language)
        db.close()

        errors: list[str] = []
        created = 0
        updated = 0
        skipped = 0
        failed = 0

        try:
            # 1. Fetch set metadata and card summaries from TCGdex
            set_data = await self.client.get_set(set_id, language=language)
            if set_data is None:
                err_msg = f"Set '{set_id}' was not found on TCGdex (HTTP 404)"
                self._persist_run_completion(
                    run.id,
                    "failed",
                    0,
                    0,
                    0,
                    0,
                    err_msg,
                )
                return ImportResult(
                    scope=scope,
                    status="failed",
                    errors=[err_msg],
                    import_run_id=run.id,
                )

            # 2. Check for digital-only product exclusion (e.g. Pokémon TCG Pocket)
            if is_digital_set(set_data):
                serie_info = set_data.get("serie")
                serie_name = (
                    serie_info.get("name")
                    if isinstance(serie_info, dict)
                    else str(serie_info)
                )
                err_msg = (
                    f"Set '{set_id}' is a digital-only product "
                    f"(series: '{serie_name}') and is excluded "
                    f"from the physical card import."
                )
                self._persist_run_completion(
                    run.id,
                    "failed",
                    0,
                    0,
                    0,
                    0,
                    err_msg,
                )
                return ImportResult(
                    scope=scope,
                    status="failed",
                    errors=[err_msg],
                    import_run_id=run.id,
                )

            # 3. Validate required set fields
            ext_set_id = set_data.get("id")
            set_name = set_data.get("name")
            if not ext_set_id or not set_name:
                err_msg = f"Malformed set data for '{set_id}': missing 'id' or 'name'"
                self._persist_run_completion(run.id, "failed", 0, 0, 0, 0, err_msg)
                return ImportResult(
                    scope=scope,
                    status="failed",
                    errors=[err_msg],
                    import_run_id=run.id,
                )

            # 4. Upsert set inside an isolated transaction
            db = SessionLocal()
            try:
                serie_val = None
                serie_raw = set_data.get("serie")
                if isinstance(serie_raw, dict):
                    serie_val = serie_raw.get("name")
                elif isinstance(serie_raw, str):
                    serie_val = serie_raw

                card_count = set_data.get("cardCount") or {}
                printed_total = (
                    card_count.get("official") if isinstance(card_count, dict) else None
                )
                total = (
                    card_count.get("total") if isinstance(card_count, dict) else None
                )

                set_row = (
                    db.query(Set)
                    .filter(
                        Set.source == "tcgdex",
                        Set.external_id == ext_set_id,
                        Set.language == language,
                    )
                    .first()
                )

                if set_row is None:
                    set_row = Set(
                        source="tcgdex",
                        external_id=ext_set_id,
                        name=set_name,
                        language=language,
                        series=serie_val,
                        logo_url=set_data.get("logo"),
                        symbol_url=set_data.get("symbol"),
                        release_date=set_data.get("releaseDate"),
                        printed_total=printed_total,
                        total=total,
                    )
                    db.add(set_row)
                    db.flush()
                else:
                    # Update changed fields without altering internal ID
                    set_row.name = set_name
                    if serie_val is not None:
                        set_row.series = serie_val
                    if "logo" in set_data:
                        set_row.logo_url = set_data.get("logo")
                    if "symbol" in set_data:
                        set_row.symbol_url = set_data.get("symbol")
                    if "releaseDate" in set_data:
                        set_row.release_date = set_data.get("releaseDate")
                    if printed_total is not None:
                        set_row.printed_total = printed_total
                    if total is not None:
                        set_row.total = total
                    db.flush()

                # 5. Upsert card summaries
                cards_data = set_data.get("cards") or []
                for card_summary in cards_data:
                    card_ext_id = card_summary.get("id")
                    card_local_id = card_summary.get("localId")
                    card_name = card_summary.get("name")
                    card_image = card_summary.get("image")

                    if not card_ext_id or card_local_id is None or not card_name:
                        failed += 1
                        errors.append(
                            f"Malformed card record in set '{set_id}': {card_summary}"
                        )
                        continue

                    local_id_str = str(card_local_id).strip()
                    card_row = (
                        db.query(Card)
                        .filter(
                            Card.source == "tcgdex",
                            Card.external_id == card_ext_id,
                            Card.language == language,
                        )
                        .first()
                    )

                    if card_row is None:
                        new_card = Card(
                            source="tcgdex",
                            external_id=card_ext_id,
                            set_id=set_row.id,
                            local_id=local_id_str,
                            name=card_name,
                            language=language,
                            image_base_url=card_image,
                        )
                        db.add(new_card)
                        created += 1
                    else:
                        changed = False
                        if card_row.name != card_name:
                            card_row.name = card_name
                            changed = True
                        if card_row.local_id != local_id_str:
                            card_row.local_id = local_id_str
                            changed = True
                        if card_row.set_id != set_row.id:
                            card_row.set_id = set_row.id
                            changed = True
                        if (
                            card_image is not None
                            and card_row.image_base_url != card_image
                        ):
                            card_row.image_base_url = card_image
                            changed = True

                        if changed:
                            updated += 1
                        else:
                            skipped += 1

                db.commit()

            except Exception as e:
                db.rollback()
                raise e
            finally:
                db.close()

            # 6. Determine status and record results
            if failed == 0:
                final_status = "succeeded"
            elif created > 0 or updated > 0 or skipped > 0:
                final_status = "partially_failed"
            else:
                final_status = "failed"

            err_summary = "; ".join(errors) if errors else None
            self._persist_run_completion(
                run.id,
                final_status,
                created,
                updated,
                skipped,
                failed,
                err_summary,
            )

            return ImportResult(
                scope=scope,
                status=final_status,
                created_count=created,
                updated_count=updated,
                skipped_count=skipped,
                failed_count=failed,
                errors=errors,
                import_run_id=run.id,
            )

        except TcgdexError as err:
            err_msg = f"TCGdex provider error while importing set '{set_id}': {err}"
            self._persist_run_completion(
                run.id, "failed", created, updated, skipped, failed, err_msg
            )
            return ImportResult(
                scope=scope,
                status="failed",
                created_count=created,
                updated_count=updated,
                skipped_count=skipped,
                failed_count=failed,
                errors=[err_msg],
                import_run_id=run.id,
            )
        except Exception as err:
            err_msg = f"Unexpected error while importing set '{set_id}': {err}"
            self._persist_run_completion(
                run.id, "failed", created, updated, skipped, failed, err_msg
            )
            return ImportResult(
                scope=scope,
                status="failed",
                created_count=created,
                updated_count=updated,
                skipped_count=skipped,
                failed_count=failed,
                errors=[err_msg],
                import_run_id=run.id,
            )

    async def import_all(self, language: str = "en") -> ImportResult:
        """Import all eligible physical-card sets from TCGdex sequentially."""
        if language not in settings.SUPPORTED_LANGUAGES:
            msg = (
                f"Unsupported language '{language}'. "
                f"Supported languages: {', '.join(settings.SUPPORTED_LANGUAGES)}"
            )
            return ImportResult(scope="all", status="failed", errors=[msg])

        db = SessionLocal()
        run = self._create_import_run(db, "all", language)
        db.close()

        all_errors: list[str] = []
        total_created = 0
        total_updated = 0
        total_skipped = 0
        total_failed = 0

        try:
            sets_summary = await self.client.get_sets(language=language)
            eligible_sets = [s for s in sets_summary if not is_digital_set(s)]

            for s in eligible_sets:
                set_id = s.get("id")
                if not set_id:
                    continue

                res = await self.import_set(set_id, language=language)
                total_created += res.created_count
                total_updated += res.updated_count
                total_skipped += res.skipped_count
                total_failed += res.failed_count
                if res.errors:
                    all_errors.extend(res.errors)

            if total_failed == 0 and not all_errors:
                status = "succeeded"
            elif total_created > 0 or total_updated > 0 or total_skipped > 0:
                status = "partially_failed"
            else:
                status = "failed"

            err_summary = "; ".join(all_errors) if all_errors else None
            self._persist_run_completion(
                run.id,
                status,
                total_created,
                total_updated,
                total_skipped,
                total_failed,
                err_summary,
            )

            return ImportResult(
                scope="all",
                status=status,
                created_count=total_created,
                updated_count=total_updated,
                skipped_count=total_skipped,
                failed_count=total_failed,
                errors=all_errors,
                import_run_id=run.id,
            )

        except Exception as err:
            err_msg = f"Fatal error during import_all: {err}"
            self._persist_run_completion(
                run.id,
                "failed",
                total_created,
                total_updated,
                total_skipped,
                total_failed,
                err_msg,
            )
            return ImportResult(
                scope="all",
                status="failed",
                created_count=total_created,
                updated_count=total_updated,
                skipped_count=total_skipped,
                failed_count=total_failed,
                errors=[err_msg],
                import_run_id=run.id,
            )
