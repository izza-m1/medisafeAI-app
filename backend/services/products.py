"""Which product a pack or a typed name is: its brand, its kind (group), whether it is a medicine,
and whether the maker printed on it is the brand's real owner."""
import re
from difflib import get_close_matches

from datasets import BRAND_ALIASES, COMPANIES, DSLD, INGREDIENT_ALIASES, MEDICINE_NAMES, NUTRIENTS, PRODUCTS
from services.label_reader import label_order
from services.matching import best_match, grams_of, norm

DSLD_BY_LOWER = {name.lower(): name for name in DSLD}
PRODUCTS_BY_LOWER = {name.lower(): name for name in PRODUCTS}

_stems = "|".join(rf"\w+{s}" for s in MEDICINE_NAMES["stems"])
_exceptions = "".join(rf"(?!{w}\b)" for w in MEDICINE_NAMES["not_medicines"])
MEDICINE = re.compile(rf"\b{_exceptions}(?:{'|'.join(MEDICINE_NAMES['generic_names'])}|{_stems})\b", re.I)

# The main nutrient of an unknown product decides which shared rules apply to it.
MULTIVITAMIN_MIN_NUTRIENTS = 4
GENERIC_PRODUCT = {p["generic_for"]: name for name, p in PRODUCTS.items() if p.get("generic_for")}


def is_medicine(text: str) -> bool:
    return bool(MEDICINE.search(text or ""))


def match_brand(grams: list) -> tuple:
    """(brand name, product name, score) for the best brand found in the text, or (None, None, 0)."""
    alias, score = best_match(grams, list(BRAND_ALIASES))
    if not alias:
        return None, None, 0.0
    brand, product = BRAND_ALIASES[alias]
    return brand, product, score


def find_ingredients(text: str) -> list:
    """Products named by ingredient words on the label (iron, folic acid...), in the order they are printed."""
    text_n = norm(text)
    hits = {}
    for alias in sorted(INGREDIENT_ALIASES, key=len, reverse=True):
        m = re.search(rf"\b{re.escape(norm(alias))}\b", text_n)
        if m and INGREDIENT_ALIASES[alias] not in hits:
            hits[INGREDIENT_ALIASES[alias]] = m.start()
    return sorted(hits, key=hits.get)


def product_for_name(name: str, ingredients: list | None = None) -> str | None:
    """A product name typed or read from a photo -> the product it is in our data, if any."""
    ingredients = ingredients or []
    if not name:
        return ingredients[0] if ingredients else None
    key = name.strip().lower()
    if key in DSLD_BY_LOWER:
        return DSLD_BY_LOWER[key]
    _, product, _ = match_brand(grams_of(name))
    if product:
        return product
    close = get_close_matches(key, list(PRODUCTS_BY_LOWER), n=1, cutoff=0.75)
    if close:
        return PRODUCTS_BY_LOWER[close[0]]
    found = find_ingredients(name)
    return (found or ingredients or [None])[0]


def product_for_amounts(amounts: dict, raw_text: str) -> str | None:
    """An unknown brand: decide its kind from the nutrients on its own label."""
    if len(amounts) >= MULTIVITAMIN_MIN_NUTRIENTS:
        return "Multivitamin"
    if "iron" in amounts:
        return GENERIC_PRODUCT["iron"]
    return next((GENERIC_PRODUCT[n] for n in label_order(amounts, raw_text) if n in GENERIC_PRODUCT), None)


def name_from_amounts(amounts: dict, raw_text: str) -> str:
    names = [NUTRIENTS[n]["name"] for n in label_order(amounts, raw_text)]
    return "Multivitamin" if len(names) >= MULTIVITAMIN_MIN_NUTRIENTS else " + ".join(names[:3]) + " supplement"


def product_info(product_name: str | None) -> dict:
    """Group, nutrients and notes of a product, from our products list or the NIH label database."""
    if product_name in PRODUCTS:
        return PRODUCTS[product_name]
    if product_name in DSLD:
        label = DSLD[product_name]
        return {"name": product_name, "group": label["group"], "nutrients": label["nutrients"], "herbs": label.get("herbs", [])}
    return {"name": product_name, "group": "general", "nutrients": []}


def nutrients_of_typed(text: str) -> list:
    """What a supplement the user typed in their profile contains: an exact product name first, then ingredient
    words ("calcium tablet" -> calcium), then a brand ("Sangobion" -> iron, folate...). [] when not recognised."""
    key = (text or "").strip().lower()
    exact = DSLD_BY_LOWER.get(key) or PRODUCTS_BY_LOWER.get(key)
    if exact:
        return product_info(exact).get("nutrients", [])
    by_ingredient = [n for product in find_ingredients(text) for n in product_info(product).get("nutrients", [])]
    if by_ingredient:
        return list(dict.fromkeys(by_ingredient))
    product = product_for_name(text)
    return product_info(product).get("nutrients", []) if product else []


def herbs_of(info: dict) -> list:
    """Herbs and other non-vitamin ingredients: a herbal product in products.json is named after its herb."""
    return list(dict.fromkeys([*info.get("herbs", []), *([info["name"]] if info.get("name") else [])]))


def match_company(text: str) -> str | None:
    if not text:
        return None
    text_n, grams = norm(text), grams_of(text)
    for company, printed_names in COMPANIES.items():
        for printed in printed_names:
            p = norm(printed)
            if len(p.replace(" ", "")) <= 5:
                if re.search(rf"\b{re.escape(p)}\b", text_n):
                    return company
            elif best_match(grams, [printed])[0]:
                return company
    return None


def brand_owners(brand: str | None, product_name: str | None) -> list:
    if not brand or product_name not in PRODUCTS:
        return []
    return PRODUCTS[product_name].get("brands", {}).get(brand, {}).get("makers", [])


def verify_maker(owners: list, registered: str | None, printed: str | None, under_licence: bool = False,
                 brand_seen: str | None = None) -> dict:
    """verified: the printed maker is registered (and owns the brand, when we know the owner)
    verified_by_brand: we know the brand's owner but no maker could be read
    mismatch: a known brand printed with a different registered maker, which may mean a fake
    unregistered: a maker is printed but is not in our list
    brand_seen: no maker line, only an unknown brand (often the brand is the company)
    not_found: nothing readable"""
    if registered:
        if owners and registered not in owners and not under_licence:
            return {"status": "mismatch", "name": registered, "expected": owners[0], "official": owners}
        return {"status": "verified", "name": registered, "official": owners, "licence": bool(owners) and registered not in owners}
    if owners:
        return {"status": "verified_by_brand", "name": owners[0], "official": owners}
    if printed:
        return {"status": "unregistered", "name": printed, "official": owners}
    if brand_seen:
        return {"status": "brand_seen", "name": brand_seen, "official": owners}
    return {"status": "not_found", "name": None, "official": owners}
