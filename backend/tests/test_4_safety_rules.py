"""TC-4  The verdict for each kind of person. Amounts come from the pack's own label text, as in a real scan."""
import pytest

from conftest import colour

PACKS = {
    "Centrum Men":   [("Centrum", 60), ("MEN", 40), ("Vitamin C 90 mg Vitamin D 25 mcg Zinc 11 mg Iron 8 mg", 10)],
    "Centrum Kids":  [("Centrum", 60), ("Kids", 40), ("Vitamin C 25 mg Zinc 5 mg Iron 7 mg", 10)],
    "Sangobion":     [("Sangobion", 60), ("Each capsule contains: Iron 30 mg", 10)],
    "Ashwagandha":   [("Ashwagandha", 60), ("Root extract 500 mg", 10)],
}
CASES = [
    ("Centrum Men", "man_30", "green"), ("Centrum Men", "woman_26_periods", "orange"), ("Centrum Men", "girl_8_periods", "red"),
    ("Centrum Kids", "boy_8", "green"),
    ("Sangobion", "woman_26_periods", "green"), ("Sangobion", "man_30", "orange"), ("Sangobion", "boy_8", "red"),
    ("Ashwagandha", "pregnant_28", "red"),
]


@pytest.mark.parametrize("pack,person,expected", CASES, ids=[f"{p} | {who} -> {c}" for p, who, c in CASES])
def test_verdict(scan, report, pack, person, expected):
    status, body = report(scan(PACKS[pack]), person)
    assert status == 200, body
    assert colour(body) == expected


def test_every_check_shows_its_source(scan, report):
    _, body = report(scan(PACKS["Sangobion"]), "man_30")
    assert all(c["source"] for c in body["report"]["is_safe_to_take"]["checks"])
