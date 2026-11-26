"""TC-11  Food, drink and supplement interactions: every one is an exact NIH sentence, and each applies only to
the right products and doses."""
import re

import pytest

from datasets import FOOD_GROUPS, FOOD_INTERACTIONS, FOODS, NUTRIENTS
from etl import build_knowledge
from services import food_guidance

KINDS = {"food", "drink", "how_to_take", "tip", "supplement"}


@pytest.fixture(scope="module")
def page_text():
    """The text of every saved NIH page, as the knowledge base reads it."""
    pages = build_knowledge.saved_pages([u for t in build_knowledge.topics() for u in t["pages"]])
    return {key: re.sub(r"\s+", " ", " ".join(" ".join(p) for _, _, p in build_knowledge.sections(html)))
            for key, html in pages.items()}


def test_every_quote_is_word_for_word_in_its_nih_page(page_text):
    for entry in FOOD_INTERACTIONS:
        for quote in entry["quotes"]:
            page = page_text[build_knowledge.page_key(quote["url"])]
            assert re.sub(r"\s+", " ", quote["text"]) in page, entry["id"]


def test_entries_use_known_supplements_groups_and_kinds():
    for entry in FOOD_INTERACTIONS:
        assert entry["kind"] in KINDS and set(entry["supplements"]) <= set(NUTRIENTS)
        assert set(entry["groups"]) <= set(FOOD_GROUPS)
    assert all(set(f["groups"]) <= set(FOOD_GROUPS) for f in FOODS)


def test_chai_is_linked_through_what_it_contains():
    lower = {f["food"]: f for f in food_guidance.for_nutrients(["calcium"])["lower"]}
    assert lower["Chai (with milk)"]["nutrients"] == ["Calcium"] and "Coffee" in lower


def test_a_food_is_never_both_helping_and_lowering():
    """A multivitamin: paratha has fat (helps vitamin D) but is a grain (lowers iron), so it is only under lower."""
    found = food_guidance.for_nutrients(["iron", "zinc", "vitamin_d", "vitamin_e", "calcium"])
    helps, lowers = {f["food"] for f in found["help"]}, {f["food"] for f in found["lower"]}
    assert not helps & lowers and "Paratha" in lowers and "Ghee, butter, oil" in helps
    fat = next(f for f in found["help"] if f["food"] == "Ghee, butter, oil")
    assert fat["nutrients"] == ["Vitamin D", "Vitamin E"]                      # one row, not one per vitamin
    assert found["timing"]["text"].startswith("Take it with a meal that has some fat")


def test_one_food_lists_every_nutrient_it_lowers():
    lowers = {f["food"]: f["nutrients"] for f in food_guidance.for_nutrients(["iron", "zinc"])["lower"]}
    assert set(lowers["Roti / chapati"]) == {"Iron", "Zinc"}


def test_dose_limited_interaction_is_left_out_below_its_dose():
    low = food_guidance.for_nutrients(["zinc"], {"zinc": 15})["other_supplements"]
    high = food_guidance.for_nutrients(["zinc"], {"zinc": 50})["other_supplements"]
    assert "zinc-copper" not in {s["id"] for s in low} and "zinc-copper" in {s["id"] for s in high}


def test_product_with_both_iron_and_calcium_is_flagged():
    found = food_guidance.for_nutrients(["iron", "calcium"], {"iron": 18, "calcium": 200})["other_supplements"]
    pair = next(s for s in found if s["id"] == "iron-calcium-apart")
    assert pair["in_this_product"] is True


def test_supplement_with_no_stated_food_interaction_gets_none():
    found = food_guidance.for_nutrients(["potassium"])
    assert found == {"timing": None, "tips": [], "help": [], "lower": [], "other_supplements": [],
                     "unrecognised_supplements": []}


def test_users_own_supplement_is_matched_against_the_scanned_product():
    found = food_guidance.for_nutrients(["iron"], {"iron": 18}, ["Caltrate", "calcium tablet", "copper"])
    first = found["other_supplements"][0]
    assert first["id"] == "iron-calcium-apart" and first["with_yours"] == ["Caltrate", "calcium tablet"]
    assert found["unrecognised_supplements"] == ["copper"]


def test_a_supplement_the_product_already_has_is_not_counted_twice():
    found = food_guidance.for_nutrients(["iron", "calcium"], {"iron": 18, "calcium": 200}, ["Caltrate"])
    pair = next(s for s in found["other_supplements"] if s["id"] == "iron-calcium-apart")
    assert pair["with_yours"] == [] and pair["in_this_product"] is True
