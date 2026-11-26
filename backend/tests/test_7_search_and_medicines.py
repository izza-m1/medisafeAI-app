"""TC-7  Search: official NIH labels, products with no official label, and medicines."""
from conftest import check


def test_nih_product_has_its_real_label(search):
    assert search("Fresh Nutrition Vitamin D3 + K2")["label"]["amounts"].get("vitamin_d")


def test_search_without_an_official_label_is_never_safe(search, report):
    _, body = report(search("Sangobion"), "woman_26_periods")
    assert "dose was NOT checked" in check(body, "label")["text"]
    assert body["report"]["is_safe_to_take"]["verdict"] != "Safe"


def test_medicine_cannot_be_searched(client):
    assert client.post("/search-product", json={"name": "Ciprofloxacin"}).status_code == 404


def test_unknown_product_is_flagged(client):
    assert client.post("/check-name", json={"name": "Xyzabc"}).json()["status"] == "unknown"
