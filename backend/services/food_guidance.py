"""How to take a product, and which foods, drinks and other supplements change how much of it you absorb.

The facts come from data/food_interactions.json (exact NIH sentences) and data/foods.json (everyday foods in
Pakistan and the NIH food groups they belong to). This file only combines them for one product:

  - timing: one instruction ("Take it with a meal that has some fat"), from every how-to-take fact that applies
  - foods: one row per everyday food, listing every nutrient in the product it helps or lowers. A food that lowers
    any of them is shown only under "can lower", never also under "helps", so the report can't contradict itself
  - other supplements: one line each, and first the ones that meet a supplement the user says they take

An interaction with a min_amount (for example "iron 25 mg or more") is left out when the label shows a smaller
amount, and kept when the amount is unknown, because its advice already says the dose it applies to."""
from datasets import FOOD_GROUPS, FOOD_INTERACTIONS, FOODS, NUTRIENTS
from services.products import nutrients_of_typed

FOOD_KINDS = ("food", "drink")
FAT = "fat"


def name_of(nutrient: str) -> str:
    return NUTRIENTS[nutrient]["name"].split(" (")[0] if nutrient in NUTRIENTS else nutrient.capitalize()


def applies(entry: dict, nutrients: list, amounts: dict) -> bool:
    if not set(entry["supplements"]) & set(nutrients):
        return False
    rule = entry.get("min_amount")
    return not (rule and rule["nutrient"] in amounts and amounts[rule["nutrient"]] < rule["amount"])


def why(entry: dict) -> dict:
    return {"text": entry["advice"], "quotes": entry["quotes"]}


def foods_in(groups: list) -> list:
    """Everyday foods in these groups; a group with no everyday food (alcohol) is shown by its own name."""
    found = [f["name"] for f in FOODS if set(f["groups"]) & set(groups)]
    return found + [FOOD_GROUPS[g] for g in groups if not any(g in f["groups"] for f in FOODS)]


def food_rows(entries: list, nutrients: list) -> dict:
    rows = {"help": {}, "lower": {}}
    for e in entries:
        side = "help" if e["effect"] == "raises" else "lower"
        for food in foods_in(e["groups"]):
            row = rows[side].setdefault(food, {"food": food, "nutrients": [], "why": []})
            for n in e["supplements"]:
                if n in nutrients and name_of(n) not in row["nutrients"]:
                    row["nutrients"].append(name_of(n))
            if why(e) not in row["why"]:
                row["why"].append(why(e))
    order = lambda r: (-len(r["nutrients"]), r["food"])
    lower = sorted(rows["lower"].values(), key=order)
    help_ = sorted((r for f, r in rows["help"].items() if f not in rows["lower"]), key=order)
    return {"help": help_, "lower": lower}


def timing(found: list, nutrients: list, lowering: set) -> dict | None:
    """One instruction for when to take it, and the NIH facts behind it."""
    effects = {e["effect"] for e in found if e["kind"] == "how_to_take"}
    fat = [e for e in found if e["kind"] in FOOD_KINDS and e["effect"] == "raises" and FAT in e["groups"]]
    reasons = [why(e) for e in found if e["kind"] == "how_to_take" and e["effect"] != "split_dose"] + [why(e) for e in fat]
    if fat:
        examples = [f for f in foods_in([FAT]) if f not in lowering][:2]
        text = "Take it with a meal that has some fat" + (f", for example {' or '.join(e.lower() for e in examples)}." if examples else ".")
    elif "with_food" in effects:
        text = "Take it with a meal."
    elif "with_food_if_upset" in effects:
        text = "You can take it with food if it upsets your stomach."
    elif "either" in effects:
        text = "You can take it with or without food."
    else:
        return None
    return {"text": text, "why": reasons}


def supplement_row(entry: dict, nutrients: list, taken: dict) -> dict:
    """taken: {supplement the user typed: its nutrients}. A pair is "yours" when this product has one side of it and
    one of the user's own supplements has the other."""
    pair = [n for n in entry.get("pair", []) if n in NUTRIENTS]
    both = all(n in nutrients for n in pair)
    yours = [name for name, has in taken.items() for a in pair for b in pair
             if a != b and a in nutrients and b in has and b not in nutrients]
    text = entry.get("in_product_advice") if both and entry.get("in_product_advice") else entry["advice"]
    return {"id": entry["id"], "effect": entry["effect"], "in_this_product": both, "with_yours": list(dict.fromkeys(yours)),
            "text": text, "quotes": entry["quotes"]}


def taken_supplements(names: list) -> dict:
    """{name the user typed: nutrients it contains}; names we can't recognise are kept with no nutrients."""
    return {name: nutrients_of_typed(name) for name in names}


def for_nutrients(nutrients: list, amounts: dict | None = None, my_supplements: list | None = None) -> dict:
    """{"timing", "tips", "help", "lower", "other_supplements", "unrecognised_supplements"} for what is in a
    product, checked against the other supplements the user takes."""
    nutrients, amounts = list(dict.fromkeys(nutrients)), amounts or {}
    taken = taken_supplements(my_supplements or [])
    found = [e for e in FOOD_INTERACTIONS if applies(e, nutrients, amounts)]
    rows = food_rows([e for e in found if e["kind"] in FOOD_KINDS], nutrients)
    lowering = {r["food"] for r in rows["lower"]}
    return {
        "timing": timing(found, nutrients, lowering),
        "tips": [why(e) for e in found if e["kind"] == "how_to_take" and e["effect"] == "split_dose"],   # cooking tips stay for Ask MediSafe
        "help": rows["help"],
        "lower": rows["lower"],
        "other_supplements": sorted((supplement_row(e, nutrients, taken) for e in found if e["kind"] == "supplement"),
                                    key=lambda row: not row["with_yours"]),
        "unrecognised_supplements": [name for name, has in taken.items() if not has],
    }


def as_passages(nutrients: list) -> list:
    """The interactions as knowledge-base passages, so the AI can cite them when answering a food question."""
    passages = []
    for e in FOOD_INTERACTIONS:
        if set(e["supplements"]) & set(nutrients):
            for i, quote in enumerate(e["quotes"]):
                passages.append({"id": f"food-{e['id']}-{i}", "topic": e["supplements"][0], "title": name_of(e["supplements"][0]),
                                 "section": quote["section"], "subsection": None, "url": quote["url"],
                                 "publisher": "NIH Office of Dietary Supplements", "text": quote["text"]})
    return passages


def everyday_foods_text() -> str:
    """One line per everyday food and its NIH food groups, for the AI's context."""
    return "; ".join(f"{f['name']} ({f['made_of']}): {', '.join(FOOD_GROUPS[g] for g in f['groups'])}" for f in FOODS)
