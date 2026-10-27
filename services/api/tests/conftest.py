import os
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
import app.services.importer as importer_module
from app.core.database import Base, get_db
from app.main import app

# Test database connection string (separate from normal development DB)
DEFAULT_TEST_DB = "mysql+pymysql://tcg_user:tcg_password@db:3306/tcg_test"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DB)
test_url = make_url(TEST_DATABASE_URL)
if test_url.get_backend_name() != "sqlite" and not (
    test_url.database and test_url.database.endswith("_test")
):
    raise RuntimeError("Tests require a dedicated database ending in _test")

try:
    if test_url.get_backend_name() == "sqlite":
        if test_url.database not in (None, "", ":memory:"):
            raise RuntimeError("SQLite tests must use an in-memory database")
        test_engine = create_engine(
            TEST_DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    with test_engine.connect() as conn:
        pass
except Exception:
    # Fallback to SQLite in-memory for environments without MariaDB
    TEST_DATABASE_URL = "sqlite:///:memory:"
    test_engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables in the test database once per session."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def clean_test_database():
    """Safeguard: clean all tables in the test database between tests."""
    with test_engine.connect() as conn:
        with conn.begin():
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())
    yield


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Provide an isolated database session for tests."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def override_db_dependency(db: Session):
    """Override FastAPI get_db dependency and importer SessionLocal with test DB."""
    app.dependency_overrides[get_db] = lambda: db
    orig_session_local = importer_module.SessionLocal
    importer_module.SessionLocal = lambda: TestingSessionLocal()
    yield
    app.dependency_overrides.pop(get_db, None)
    importer_module.SessionLocal = orig_session_local


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# Representative provider fixtures
@pytest.fixture
def sample_set_fixture() -> dict[str, Any]:
    return {
        "id": "base1",
        "name": "Base Set",
        "serie": {"id": "base", "name": "Base"},
        "logo": "https://assets.tcgdex.net/en/base/base1/logo",
        "symbol": "https://assets.tcgdex.net/univ/base/base1/symbol",
        "releaseDate": "1999-01-09",
        "cardCount": {"official": 102, "total": 102},
        "cards": [
            {
                "id": "base1-1",
                "localId": "1",
                "name": "Alakazam",
                "image": "https://assets.tcgdex.net/en/base/base1/1",
            },
            {
                "id": "base1-2",
                "localId": "2",
                "name": "Blastoise",
                "image": "https://assets.tcgdex.net/en/base/base1/2",
            },
            {
                "id": "base1-003",
                "localId": "003",
                "name": "Chansey",
                "image": "https://assets.tcgdex.net/en/base/base1/3",
            },
            {
                "id": "base1-TG01",
                "localId": "TG01",
                "name": "Pikachu",
                "image": "https://assets.tcgdex.net/en/base/base1/58",
            },
            {
                "id": "base1-5",
                "localId": "5",
                "name": "Clefairy",
                "image": None,  # Test missing optional image
            },
        ],
    }


@pytest.fixture
def sample_digital_set_fixture() -> dict[str, Any]:
    return {
        "id": "A1",
        "name": "Genetic Apex",
        "serie": {"id": "tcgp", "name": "Pokémon TCG Pocket"},
        "logo": "https://assets.tcgdex.net/en/tcgp/A1/logo",
        "cardCount": {"official": 226, "total": 286},
        "cards": [
            {
                "id": "A1-1",
                "localId": "1",
                "name": "Bulbasaur",
                "image": "https://assets.tcgdex.net/en/tcgp/A1/1",
            }
        ],
    }


@pytest.fixture
def sample_card_detail_fixture() -> dict[str, Any]:
    return {
        "id": "base1-1",
        "localId": "1",
        "name": "Alakazam",
        "image": "https://assets.tcgdex.net/en/base/base1/1",
        "category": "Pokemon",
        "illustrator": "Ken Sugimori",
        "rarity": "Rare Holo",
        "hp": 80,
        "types": ["Psychic"],
        "regulationMark": None,
        "variants": {
            "firstEdition": True,
            "holo": True,
            "normal": False,
            "reverse": False,
            "wPromo": False,
        },
        "attacks": [
            {
                "name": "Confuse Ray",
                "cost": ["Psychic", "Psychic", "Psychic"],
                "damage": 30,
                "effect": (
                    "Flip a coin. If heads, the Defending Pokémon is now Confused."
                ),
            }
        ],
        "abilities": [
            {
                "type": "Pokemon Power",
                "name": "Damage Swap",
                "effect": (
                    "As often as you like during your turn, "
                    "you may move 1 damage counter."
                ),
            }
        ],
        "pricing": {
            "cardmarket": {"avg": 45.0},
            "tcgplayer": {"market": 50.0},
        },
    }
