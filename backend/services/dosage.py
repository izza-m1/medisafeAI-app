"""How to take the product: a table of each nutrient (per tablet, your daily need, the upper limit),
plain steps, and the dose card. The dose comes from the pack's directions and is never guessed."""
import re

from datasets import NUTRIENTS
from services import limits
from services.label_reader import format_amount

ADULT_AGE = 18
CHILD_DOSE_AGE = 14
NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "half": "½", "1/2": "½"}


def plan(amounts: dict, directions: str | None, person: dict, over: list) -> dict:
    rows = []
    for n, value in amounts.items():
        need, limit, unit = limits.daily_need(n, person), limits.upper_limit(n, person["age"]), NUTRIENTS[n]["unit"]
        rows.append({"nutrient": NUTRIENTS[n]["name"], "per_tablet": format_amount(value, unit),
                     "daily_need": format_amount(need, unit) if need else None,
                     "percent_of_need": round(100 * value / need) if need else None,
                     "safe_limit": format_amount(limit, unit) if limit else "No limit set",
                     "over_limit": bool(limit and value > limit), "source": NUTRIENTS[n]["fact_sheet"]})
    child, doctor_only = person["age"] < ADULT_AGE, bool(over) and person["age"] < ADULT_AGE
    if doctor_only:
        steps = ["Don't take this product unless a doctor prescribed it for you.",
                 "If a doctor did prescribe it, take exactly the dose they gave and no more."]
    elif over:
        steps = [f"The pack says: {directions}." if directions else "Take no more than 1 tablet a day.",
                 "Use it for a short course only, as your doctor or pharmacist advises."]
    else:
        if directions:
            steps = [f"The pack says: {directions}."]
        elif rows:
            steps = ["Take the dose printed on the pack, or as your doctor advises."]
        else:
            steps = ["Take the dose printed on the pack. We couldn't read its strength, so we can't check it against your age."]
        if person["age"] < CHILD_DOSE_AGE:
            steps.append("Use the children's dose on the pack. If the pack has no children's dose, ask a pharmacist before giving it.")
        steps.append("Don't take more than the pack says. The upper limit counts what you get from food too.")
    return {"steps": steps, "nutrients": rows, "strength_source": "label" if rows else None,
            "summary": dose_card(directions, doctor_only=doctor_only, short_course=bool(over) and not child)}


def dose_card(directions: str | None, doctor_only: bool, short_course: bool) -> dict:
    """Big-type card: amount and how often, read from the pack's directions."""
    if doctor_only:
        return {"doctor_only": True}
    amount = how_often = None
    if directions:
        m = re.search(r"(\d|one|two|three|1/2|half)\s+(tablet|capsule|caplet|sachet|softgel|teaspoon|tsp)", directions, re.I)
        if m:
            count = NUMBER_WORDS.get(m.group(1).lower(), m.group(1))
            amount = f"{count} {m.group(2).lower()}{'s' if count not in ('1', '½') else ''}"
        d = directions.lower()
        how_often = ("3 times a day" if re.search(r"thrice|3\s*times", d) else "twice a day" if re.search(r"twice|2\s*times", d)
                     else "once a day" if re.search(r"once|daily|a\s+day|per\s+day", d) else None)
    return {"doctor_only": False, "short_course": short_course, "amount": amount, "how_often": how_often, "when": None,
            "usual": False}
