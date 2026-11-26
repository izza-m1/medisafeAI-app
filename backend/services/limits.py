"""Daily need and upper limit of a nutrient for one person, from nutrients.json (NIH ODS)."""
from datasets import NUTRIENTS

ADULT_FROM_AGE = 19


def daily_need(nutrient: str, person: dict) -> float | None:
    info, age = NUTRIENTS[nutrient], person["age"]
    no_periods = person["sex"] == "female" and person.get("periods") == "no" and not person.get("pregnant")
    if no_periods and info.get("need_without_periods"):
        for low, high, value in info["need_without_periods"]:
            if low <= age <= high:
                return value
    for low, high, male, female, pregnant, breastfeeding in info["need"]:
        if low <= age <= high:
            if person.get("pregnant") and pregnant:
                return pregnant
            if person.get("breastfeeding") and breastfeeding:
                return breastfeeding
            return female if person["sex"] == "female" else male
    return None


def upper_limit(nutrient: str, age: int) -> float | None:
    return next((value for low, high, value in NUTRIENTS[nutrient]["upper_limit"] if low <= age <= high), None)


def limit_group(nutrient: str, age: int) -> str:
    for low, high, _ in NUTRIENTS[nutrient]["upper_limit"]:
        if low <= age <= high:
            return "adults" if low >= ADULT_FROM_AGE else f"ages {low} to {high}"
    return f"age {age}"


def over_limit(amounts: dict, age: int) -> list:
    """[(nutrient, amount, limit)] for every amount above the upper limit for this age."""
    return [(n, v, upper_limit(n, age)) for n, v in amounts.items()
            if upper_limit(n, age) is not None and v > upper_limit(n, age)]
