"""'Why do you take it?': the reasons a product is really used for (from what is inside it), and whether
the user's own reasons fit. Reasons come from reasons.json, which follows the NIH ODS and NCCIH fact sheets."""
import re

import settings
from datasets import NUTRIENTS, REASONS
from services import embeddings, limits
from services.products import product_info

STRONG_SHARE_OF_NEED = 0.5      # a nutrient counts as a main one at half a day's need or more
MAX_MAIN_NUTRIENTS = 3
MAX_SUGGESTIONS = 9
MULTIVITAMIN_MIN_NUTRIENTS = 5
MENOPAUSE_AGE = 35
REFERENCE_ADULT = {"age": 30, "sex": "female", "periods": "yes", "pregnant": False, "breastfeeding": False}
PREGNANCY_REASONS = ("Pregnancy", "Planning a pregnancy", "Breastfeeding")


def _short_name(nutrient: str) -> str:
    return NUTRIENTS[nutrient]["name"].split(" (")[0].lower()


def _contents(product: dict, amounts: dict) -> list:
    return list(dict.fromkeys([*product.get("nutrients", []), *(n for n in amounts if n in NUTRIENTS)]))


def main_nutrients(product: dict, amounts: dict) -> list:
    """What the product is mainly for: strong doses only, so a little vitamin C added to iron doesn't count."""
    amounts = {n: v for n, v in amounts.items() if n in NUTRIENTS}
    share = {n: v / (limits.daily_need(n, REFERENCE_ADULT) or float("inf")) for n, v in amounts.items()}
    strong = sorted((n for n in share if share[n] >= STRONG_SHARE_OF_NEED), key=share.get, reverse=True)
    return strong[:MAX_MAIN_NUTRIENTS] or _contents(product, {})[:2]


def _fits_person(reason: dict, person: dict | None) -> bool:
    if not person:
        return True
    if reason.get("female") and person.get("sex") != "female":
        return False
    if reason.get("min_age") and person.get("age", 0) < reason["min_age"]:
        return False
    if reason.get("max_age") and person.get("age", 0) > reason["max_age"]:
        return False
    after_menopause = person.get("periods") == "no" and person.get("age", 0) >= MENOPAUSE_AGE
    if reason["label"] == "Heavy periods" and person.get("periods") == "no":
        return False
    return not (reason["label"] in PREGNANCY_REASONS and after_menopause)


def product_reasons(name: str, product_key: str | None, amounts: dict, person: dict | None = None) -> list:
    product = product_info(product_key)
    contents = _contents(product, amounts)
    text = f"{name} {product_key or ''} {' '.join(product.get('herbs', []))}".lower()
    rows = [r for word, items in REASONS["products"].items() if word in text for r in items]
    if product["group"] == "prenatal":
        rows += REASONS["products"]["prenatal"]
    if len(contents) >= MULTIVITAMIN_MIN_NUTRIENTS:
        rows += [r for r in REASONS["multivitamin"] if not r.get("needs_any") or set(r["needs_any"]) & set(contents)]
    else:
        rows += [r for n in main_nutrients(product, amounts) for r in REASONS["nutrients"].get(n, [])]
    return list(dict.fromkeys(r["label"] for r in rows if _fits_person(r, person)))


def suggested_reasons(name: str, product_key: str | None, amounts: dict, person: dict) -> list:
    return product_reasons(name, product_key, amounts, person)[:MAX_SUGGESTIONS] or [REASONS["everyday_label"]]


def closest_use(reason: str, uses: list) -> str | None:
    """The product's real use that means the same as the user's reason ("always tired" -> "Tiredness from low
    iron"), by embedding similarity. None when nothing is close enough or the model can't be loaded."""
    if not uses:
        return None
    try:
        scores = embeddings.similarity(reason, uses)
    except (ImportError, OSError, ValueError, RuntimeError) as e:
        print(f"Reason matching without the embedding model: {e}")
        return None
    ranked = sorted(range(len(uses)), key=scores.__getitem__, reverse=True)
    best, runner_up = scores[ranked[0]], (scores[ranked[1]] if len(ranked) > 1 else 0)
    clear = best >= settings.REASON_MATCH_MIN and best - runner_up >= settings.REASON_MATCH_MARGIN
    return uses[ranked[0]] if clear else None


def check_reasons(name: str, product_key: str | None, amounts: dict, reasons: list) -> list:
    """Each reason -> helps / no / unsure, with one plain sentence."""
    product = product_info(product_key)
    contents = set(_contents(product, amounts))
    herbal = product["group"] in ("herbal", "hormone")
    uses = product_reasons(name, product_key, amounts)
    known = {r.lower() for r in uses}
    results = []
    for reason in reasons:
        r = reason.lower()
        named = [n for n, pattern in REASONS["needs"].items() if re.search(pattern, r)]
        missing = [n for n in named if n not in contents]
        unsupported = next((u for u in REASONS["not_supported"] if u["nutrient"] in contents and re.search(u["pattern"], r)), None)
        if re.search(REASONS["general_use"], r):
            result, text = "helps", "Fine for general daily use, within the daily upper limits."
        elif r in known:
            result, text = "helps", f"{name} is used for {r}, based on what is inside it."
        elif named and herbal:
            n = _short_name(named[0])
            result, text = "no", f"{name} is a herbal product, not a measured {n} supplement. Ask your doctor about a proper {n} supplement."
        elif missing:
            n = _short_name(missing[0])
            result, text = "no", f"{name} has no {n}, so it won't help with this. Ask your doctor about a {n} supplement."
        elif named:
            result, text = "helps", f"{name} contains {_short_name(named[0])}, which is used for this."
        elif re.search(REASONS["needs_doctor"], r):
            result, text = "no", (f"{name} does not treat {r}. This needs a doctor's care and the right medicine, "
                                  "not a supplement.")
        elif unsupported:
            result, text = "no", unsupported["text"]
        elif match := closest_use(reason, uses):
            result, text = "helps", f"{name} is used for {match.lower()}, which matches your reason."
        else:
            result, text = "unsure", f"There is no good evidence that {name} helps with {r}."
        results.append({"reason": reason, "result": result, "text": text})
    return results


def summary_check(results: list) -> dict | None:
    """One row for the safety checks list: a reason it won't help with turns the report red."""
    not_helping = next((r for r in results if r["result"] in ("no", "unsure")), None)
    if not_helping:
        return {"key": "reason", "title": "Your reason", "status": "stop", "text": not_helping["text"],
                "source": REASONS["source"]}
    if results:
        return {"key": "reason", "title": "Your reason", "status": "ok", "text": "It is used for the reasons you gave.",
                "source": REASONS["source"]}
    return None
