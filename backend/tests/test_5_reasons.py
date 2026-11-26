"""TC-5  'Why do you take it?': only reasons the product is used for, and a wrong reason turns the report red."""
from conftest import colour


def reasons_for(client, scan_result, age, sex, periods=None):
    return client.post("/suggest-reasons", json={"scan_id": scan_result["scan_id"], "age": age, "sex": sex,
                                                 "periods": periods}).json()["reasons"]


SANGOBION = [("Sangobion", 60), ("Each capsule contains: Iron 30 mg", 10)]


def test_iron_supplement_only_offers_iron_reasons(client, scan):
    options = reasons_for(client, scan(SANGOBION), 26, "female", "yes")
    assert "Low iron / anaemia" in options
    assert not any(word in r.lower() for r in options for word in ("vitamin d", "stress", "sleep", "bone"))


def test_women_only_reasons_are_hidden_for_men(client, scan):
    options = reasons_for(client, scan(SANGOBION), 30, "male")
    assert "Heavy periods" not in options and "Pregnancy" not in options


def test_right_reason_helps(scan, report):
    _, body = report(scan(SANGOBION), "woman_26_periods", ["Heavy periods"])
    assert colour(body) == "green" and body["report"]["purpose_check"]["results"][0]["result"] == "helps"


def test_illness_reason_wont_help(scan, report):
    _, body = report(scan(SANGOBION), "woman_26_periods", ["Seizures"])
    assert colour(body) == "red" and body["report"]["is_safe_to_take"]["title"] == "Not right for your reason"
