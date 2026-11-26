"""TC-8  Products not in our data: checked with the composition printed on their own pack, never guessed."""
from conftest import check, colour
from services import composition, scanner


def test_unknown_brand_is_read_from_its_label(scan):
    r = scan([("NUTRIFACTOR", 60), ("Nutri B3", 30), ("Each tablet contains: Niacin 500 mg", 10)])
    assert r["product"]["supported"] and r["label"]["amounts"] == {"niacin": 500.0}


def test_same_vitamin_different_strength_gives_different_results(scan, report):
    _, low = report(scan([("BRANDX", 60), ("Each tablet contains: Niacin 14 mg", 10)]), "man_30")
    _, high = report(scan([("BRANDY", 60), ("Each tablet contains: Niacin 500 mg", 10)]), "man_30")
    assert colour(low) == "green" and colour(high) != "green"


def test_child_is_stopped_by_a_strong_unknown_product(scan, report):
    _, body = report(scan([("NUTRIFACTOR", 60), ("Each tablet contains: Niacin 500 mg", 10)]), "boy_8")
    assert colour(body) == "red"


def test_front_only_photo_gets_the_full_list_by_lookup(scan, report, client, monkeypatch):
    monkeypatch.setattr(scanner, "_read_with_ai", lambda images, text: {
        "product_name": "Nutricost Vitamin B6", "brand": "Nutricost", "is_supplement": True})
    monkeypatch.setattr(composition, "look_up", lambda brand, product: {
        "lines": ["Vitamin B6 (as Pyridoxine HCl) 100 mg"], "inactive": ["Rice flour"], "name": "Vitamin B6 100 mg",
        "source": "NIH Dietary Supplement Label Database", "url": "https://dsld.od.nih.gov/label/1"})
    r = scan([("nutricost", 30), ("Vitamin B6", 60), ("240 CAPSULES", 10)])
    assert r["label"]["facts_seen"] is False
    looked_up = client.post("/lookup-composition", json={"scan_id": r["scan_id"]}).json()["label"]
    assert looked_up["amounts"] == {"vitamin_b6": 100.0} and looked_up["composition_source"]["name"].startswith("NIH")


def test_nothing_found_is_never_called_safe(scan, report, client, monkeypatch):
    monkeypatch.setattr(scanner, "_read_with_ai", lambda images, text: {
        "product_name": "Zorvex Daily", "brand": "Zorvex", "is_supplement": True})
    monkeypatch.setattr(composition, "look_up", lambda brand, product: None)
    r = scan([("ZORVEX", 60), ("Daily", 30)])
    assert client.post("/lookup-composition", json={"scan_id": r["scan_id"]}).status_code == 404
    _, body = report(r, "man_30")
    assert "dose was NOT checked" in check(body, "label")["text"] and colour(body) != "green"


def test_brand_on_the_pack_is_shown_as_the_company(scan, monkeypatch):
    monkeypatch.setattr(scanner, "_read_with_ai", lambda images, text: {
        "product_name": "Nutricost Vitamin B6", "brand": "Nutricost", "active_ingredients": ["Vitamin B6 100 mg"], "is_supplement": True})
    r = scan([("nutricost", 30), ("Vitamin B6", 60), ("240 CAPSULES", 10)])
    assert r["company"]["status"] == "brand_seen" and r["company"]["name"] == "Nutricost"
