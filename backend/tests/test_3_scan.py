"""TC-3  Scanning: the photo check, reading the brand, OCR mistakes, medicines and the maker."""


def test_photo_that_is_not_a_supplement_is_rejected(scan):
    assert scan([("Rice", 50)], is_supplement=False)["success"] is False


def test_brand_is_read(scan):
    r = scan([("NEUROBION", 60), ("Vitamin B1 B6 B12", 12)])
    assert r["product"]["name"] == "Neurobion" and r["product"]["supported"]


def test_ocr_mistakes_are_tolerated(scan):
    assert scan([("Fefo1-Vit", 60)])["product"]["name"] == "Fefol Vit"


def test_medicine_is_recognised(scan):
    r = scan([("Klaricid", 60), ("Clarithromycin 500mg", 12)])
    assert r["product"]["medicine"] is True and r["product"]["supported"] is False


def test_maker_is_verified(scan):
    r = scan([("Neurobion", 60), ("Manufactured by Martin Dow Marker Ltd under licence of Merck KGaA", 8)])
    assert r["company"]["status"] == "verified"


def test_different_maker_may_be_fake(scan):
    r = scan([("Neurobion", 60), ("Manufactured by Getz Pharma", 8)])
    assert r["company"]["status"] == "mismatch"
