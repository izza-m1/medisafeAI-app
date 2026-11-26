"""TC-6  Food guidance (only what NIH fact sheets state) and the dose compared with NIH limits."""
from services.label_reader import parse_amounts


def foods(body):
    r = body["report"]
    return [f["food"] for f in r["recommended_foods"]], [f["food"] for f in r["foods_to_avoid"]]


def test_iron_foods_that_help_and_foods_that_lower_absorption(scan, report):
    _, body = report(scan([("Sangobion", 60), ("Iron 30 mg", 10)]), "woman_26_periods")
    r = body["report"]
    helps = {f["food"]: f["nutrients"] for f in r["recommended_foods"]}
    lowers = {f["food"]: f["nutrients"] for f in r["foods_to_avoid"]}
    assert helps["Kinnu / malta / orange"] == ["Iron"] and "Murghi (chicken)" in helps
    assert {"Roti / chapati", "Daal (lentils)", "Doodh (milk)"} <= set(lowers)
    assert r["timing"]["text"] == "You can take it with food if it upsets your stomach."
    assert any(s["id"] == "iron-calcium-apart" for s in r["other_supplements"])
    assert all(q["url"].startswith("https://ods.od.nih.gov/") for f in r["foods_to_avoid"] for w in f["why"] for q in w["quotes"])


def test_strength_is_compared_with_nih_limit(scan, report):
    _, body = report(scan([("Neurobion", 60), ("Vitamin B6 200 mg Vitamin B12 200 mcg", 10)]), "man_30")
    b6 = next(n for n in body["report"]["recommended_dosage"]["nutrients"] if n["nutrient"].startswith("Vitamin B6"))
    assert b6["over_limit"] is True


def test_thousands_separator_is_not_read_as_a_decimal():
    assert parse_amounts("Vitamin D3 10,000 IU") == {"vitamin_d": 10000.0}
    assert parse_amounts("Folic acid 2,5 mg")["folate"] == 2500.0


def test_mineral_salt_weight_is_not_the_mineral_amount():
    assert parse_amounts("Ferrous sulphate 200 mg") == {}
    assert parse_amounts("Ferrous sulphate 200 mg equivalent to elemental iron 65 mg") == {"iron": 65.0}
