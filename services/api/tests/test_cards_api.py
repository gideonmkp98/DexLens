from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.card import Card
from app.models.set import Set


def _seed_test_data(db: Session) -> tuple[Set, Set]:
    s1 = Set(
        source="tcgdex",
        external_id="base1",
        name="Base Set",
        language="en",
        series="Base",
        release_date="1999-01-09",
        printed_total=102,
        total=102,
    )
    s2 = Set(
        source="tcgdex",
        external_id="base2",
        name="Jungle",
        language="en",
        series="Base",
        release_date="1999-06-16",
        printed_total=64,
        total=64,
    )
    db.add_all([s1, s2])
    db.flush()

    c1 = Card(
        source="tcgdex",
        external_id="base1-58",
        set_id=s1.id,
        local_id="58",
        name="Pikachu",
        language="en",
        image_base_url="https://assets.tcgdex.net/en/base/base1/58",
    )
    c2 = Card(
        source="tcgdex",
        external_id="base2-60",
        set_id=s2.id,
        local_id="60",
        name="Pikachu",
        language="en",
        image_base_url="https://assets.tcgdex.net/en/base/base2/60",
    )
    c3 = Card(
        source="tcgdex",
        external_id="base1-14",
        set_id=s1.id,
        local_id="14",
        name="Raichu",
        language="en",
        image_base_url="https://assets.tcgdex.net/en/base/base1/14",
    )
    c4 = Card(
        source="tcgdex",
        external_id="base1-4",
        set_id=s1.id,
        local_id="4",
        name="Charizard",
        language="en",
        image_base_url="https://assets.tcgdex.net/en/base/base1/4",
    )
    db.add_all([c1, c2, c3, c4])
    db.commit()
    return s1, s2


def test_list_cards_name_partial_match(client: TestClient, db: Session):
    _seed_test_data(db)

    # Partial case-insensitive search
    res = client.get("/api/v1/cards?name=pika")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert all("Pikachu" in c["name"] for c in data["items"])


def test_list_cards_number_exact_match(client: TestClient, db: Session):
    _seed_test_data(db)

    # Exact number match
    res = client.get("/api/v1/cards?number=58")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["local_id"] == "58"
    assert data["items"][0]["name"] == "Pikachu"


def test_list_cards_set_filter_and_combined(client: TestClient, db: Session):
    s1, s2 = _seed_test_data(db)

    # Filter by set_id
    res = client.get(f"/api/v1/cards?set_id={s2.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["set_name"] == "Jungle"

    # Combined filters with AND semantics: Pikachu in Base Set
    res_comb = client.get(f"/api/v1/cards?name=pikachu&set_id={s1.id}&number=58")
    assert res_comb.status_code == 200
    comb_data = res_comb.json()
    assert comb_data["total"] == 1
    assert comb_data["items"][0]["external_id"] == "base1-58"


def test_list_cards_pagination_and_totals(client: TestClient, db: Session):
    _seed_test_data(db)

    res_p1 = client.get("/api/v1/cards?page=1&page_size=2")
    assert res_p1.status_code == 200
    data_p1 = res_p1.json()
    assert len(data_p1["items"]) == 2
    assert data_p1["total"] == 4
    assert data_p1["page"] == 1
    assert data_p1["page_size"] == 2

    res_p2 = client.get("/api/v1/cards?page=2&page_size=2")
    assert res_p2.status_code == 200
    data_p2 = res_p2.json()
    assert len(data_p2["items"]) == 2
    assert data_p2["page"] == 2


def test_list_cards_deterministic_ordering(client: TestClient, db: Session):
    s1, _ = _seed_test_data(db)

    res = client.get(f"/api/v1/cards?set_id={s1.id}")
    assert res.status_code == 200
    items = res.json()["items"]
    # In set 1: 4 (Charizard), 14 (Raichu), 58 (Pikachu)
    local_ids = [c["local_id"] for c in items]
    assert local_ids == ["4", "14", "58"]


def test_get_card_by_id(client: TestClient, db: Session):
    _seed_test_data(db)
    card = db.query(Card).filter(Card.external_id == "base1-4").first()

    res = client.get(f"/api/v1/cards/{card.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Charizard"
    assert data["local_id"] == "4"
    assert data["set"]["name"] == "Base Set"
    assert (
        data["small_image_url"] == "https://assets.tcgdex.net/en/base/base1/4/low.webp"
    )
    assert (
        data["large_image_url"] == "https://assets.tcgdex.net/en/base/base1/4/high.webp"
    )


def test_get_card_not_found(client: TestClient):
    res = client.get("/api/v1/cards/999999")
    assert res.status_code == 404
    assert res.json()["detail"] == "Card not found"


def test_sets_endpoints(client: TestClient, db: Session):
    s1, s2 = _seed_test_data(db)

    # List sets
    res = client.get("/api/v1/sets")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    # Verify local_card_count is included
    counts = {s["name"]: s["local_card_count"] for s in data["items"]}
    assert counts["Base Set"] == 3
    assert counts["Jungle"] == 1

    # Get single set
    res_set = client.get(f"/api/v1/sets/{s1.id}")
    assert res_set.status_code == 200
    s_data = res_set.json()
    assert s_data["name"] == "Base Set"
    assert s_data["local_card_count"] == 3


def test_get_set_not_found(client: TestClient):
    res = client.get("/api/v1/sets/999999")
    assert res.status_code == 404
    assert res.json()["detail"] == "Set not found"


def test_input_validation(client: TestClient):
    res_page_zero = client.get("/api/v1/cards?page=0")
    assert res_page_zero.status_code == 422

    res_large_page_size = client.get("/api/v1/cards?page_size=101")
    assert res_large_page_size.status_code == 422
