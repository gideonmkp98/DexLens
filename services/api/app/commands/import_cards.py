import argparse
import asyncio
import logging
import sys

from app.core.config import settings
from app.integrations.tcgdex import TCGdexProvider
from app.services.importer import CardImporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("import_cards")


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import minimal Pokémon card index from TCGdex into local MariaDB.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--set",
        dest="set_id",
        type=str,
        help="TCGdex set ID to import (e.g. 'base1', 'sv01').",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Import all eligible physical sets from TCGdex sequentially.",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en",
        help="Language code for card data (default: 'en').",
    )
    return parser.parse_args(args)


async def main_async(args: argparse.Namespace) -> int:
    language = args.language.lower().strip()
    if language not in settings.SUPPORTED_LANGUAGES:
        logger.error(
            "Language '%s' is not supported. Supported: %s",
            language,
            settings.SUPPORTED_LANGUAGES,
        )
        return 1

    async with TCGdexProvider() as client:
        importer = CardImporter(client=client)

        if args.set_id:
            logger.info(
                "Starting import for set '%s' in language '%s'...",
                args.set_id,
                language,
            )
            result = await importer.import_set(args.set_id, language=language)
        else:
            logger.info(
                "Starting full physical-card catalog import in language '%s'...",
                language,
            )
            result = await importer.import_all(language=language)

    logger.info("Import run finished with status: %s", result.status)
    logger.info(
        "Counters (cards): created=%d, updated=%d, skipped=%d, failed=%d",
        result.created_count,
        result.updated_count,
        result.skipped_count,
        result.failed_count,
    )

    if result.errors:
        logger.warning("Errors recorded during import:")
        for err in result.errors[:10]:
            logger.warning(" - %s", err)
        if len(result.errors) > 10:
            logger.warning(" - ... and %d more errors", len(result.errors) - 10)

    # Return nonzero code on failure or partial failure
    if result.status == "succeeded":
        return 0
    return 1


def main() -> None:
    args = parse_args()
    code = asyncio.run(main_async(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
