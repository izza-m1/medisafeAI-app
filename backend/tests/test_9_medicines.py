"""TC-9  The user's own medicines: interactions from the NIH ODS fact sheets."""
from conftest import check, colour

CALCIUM = [("Calcium", 60), ("Each tablet contains: Calcium 500 mg", 10)]
VITAMIN_K = [("Vitamin K2", 60), ("Each tablet contains: Vitamin K2 100 mcg", 10)]


def test_thyroid_medicine_and_calcium_need_4_hours_apart(scan, report):
    _, body = report(scan(CALCIUM), "woman_60_menopause", medicines=["levothyroxine"])
    assert "4 hours apart" in check(body, "medicine")["text"] and colour(body) == "orange"


def test_warfarin_and_vitamin_k_is_stopped(scan, report):
    _, body = report(scan(VITAMIN_K), "man_30", medicines=["warfarin"])
    assert colour(body) == "red"


def test_medicine_with_no_interaction_adds_nothing(scan, report):
    _, body = report(scan(CALCIUM), "man_30", medicines=["warfarin"])
    assert check(body, "medicine") is None


def test_medicine_list_for_the_app(client):
    names = [m["key"] for m in client.get("/medicines").json()["medicines"]]
    assert "levothyroxine" in names and "warfarin" in names
