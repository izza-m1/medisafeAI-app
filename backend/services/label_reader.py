"""Reads what a supplement label says: amounts per tablet, age limits, pregnancy warnings, directions,
who the product is made for, the maker and every listed ingredient."""
import re

from datasets import LABEL_WORDS, NUTRIENTS, TARGETS

AMOUNT = r"(\d+(?:[.,]\d+)?)\s*(mg|mcg|µg|ug|iu|i\.u\.?|g)\b"
SALT = "(?:" + "|".join(LABEL_WORDS["mineral_salts"]) + ")"
TO_MG = {"g": 1e3, "mg": 1, "mcg": 1e-3}
MCG_TO_IU_VITAMIN_D = 40


def format_amount(value: float, unit: str) -> str:
    return f"{value:,.1f}".rstrip("0").rstrip(".") + f" {unit}"


def convert(value: float, unit: str, nutrient: str) -> float | None:
    """An amount as printed -> the unit nutrients.json uses for this nutrient, or None if it can't be converted."""
    unit = unit.lower().replace("µg", "mcg").replace("ug", "mcg").replace("i.u.", "iu").replace("i.u", "iu")
    wanted = NUTRIENTS[nutrient]["unit"].lower()
    if unit == "iu":
        per_iu = NUTRIENTS[nutrient].get("per_iu")
        if not per_iu:
            return None
        unit, value = per_iu["unit"], value * per_iu["factor"]
    if unit in TO_MG and wanted in TO_MG:
        return value * TO_MG[unit] / TO_MG[wanted]
    if nutrient == "vitamin_d" and unit == "mcg":
        return value * MCG_TO_IU_VITAMIN_D
    return value if unit == wanted else None


def parse_amounts(text: str) -> dict:
    """'Vitamin B6 200 mg' -> {'vitamin_b6': 200.0}. A mineral salt's weight ("ferrous sulphate 200 mg") is not
    the amount of the mineral, so only an 'equivalent to ... elemental' or '(as ...)' amount is trusted for those."""
    text = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", text)    # 10,000 IU -> 10000
    text = text.replace(",", ".")                          # 2,5 mg -> 2.5
    found = {}
    for nutrient, info in NUTRIENTS.items():
        for m in re.finditer(info["label_names"], text, re.I):
            after = text[m.end(): m.end() + 70]
            is_salt = (re.search(SALT, m.group(0), re.I) or re.match(rf"\s*\(?\s*(?:as\s+)?\w*\s*{SALT}", after, re.I)
                       or re.match(SALT, after.strip(), re.I))
            elemental = re.search(rf"(?:equivalent|equiv\.?|eq\.?)\s*to\s*(?:elemental\s*\w+\s*)?{AMOUNT}", after, re.I)
            as_form = re.match(rf"\s*\(\s*as\s+[^)]{{1,40}}\)\s*{AMOUNT}", after, re.I)
            if as_form and not re.search(SALT, m.group(0), re.I):
                number, unit = as_form.groups()
            elif elemental:
                number, unit = elemental.groups()
            elif is_salt:
                continue
            else:
                direct = (re.match(rf"[^0-9a-z]{{0,25}}?(?:\([^)]{{0,30}}\)\s*)?{AMOUNT}", after, re.I)
                          or re.search(rf"{AMOUNT}\s*(?:of\s+)?(?:dl?-?\s*)?$", text[max(0, m.start() - 25): m.start()], re.I))
                if not direct:
                    continue
                number, unit = direct.groups()
            value = convert(float(number), unit, nutrient)
            if value:
                found[nutrient] = round(value, 3)
                break
    return found


AGE_LIMITS = [
    r"not\s+(?:recommended|suitable|intended|to\s+be\s+(?:used|given)|for\s+use)\s+(?:for|in|to|by)\s+children\s+(?:under|below|less\s+than|younger\s+than)\s+(\d{1,2})",
    r"not\s+for\s+(?:use\s+(?:by|in)\s+)?children\s+(?:under|below|less\s+than|younger\s+than)\s+(?:the\s+age\s+of\s+)?(\d{1,2})",
    r"children\s+(?:under|below|less\s+than)\s+(\d{1,2})\s*(?:years?|yrs?)?\s*[:\-–]?\s*(?:do\s+not|should\s+not|not\s+recommended)",
    r"adults?\s+and\s+children\s+(?:over|above|aged)\s+(\d{1,2})",
    r"for\s+(?:adults|children)\s+(?:over|above|aged)\s+(\d{1,2})",
]
ADULTS_ONLY = r"\b(?:for\s+adults?\s+only|adults?\s+only|not\s+for\s+(?:use\s+(?:by|in)\s+)?children)\b"
ADULT_AGE = 18


def parse_age_limit(text: str) -> tuple:
    """('Not recommended for children under 12 years') -> (12, the printed words)."""
    for pattern in AGE_LIMITS:
        m = re.search(pattern, text, re.I)
        if m:
            return int(m.group(1)), m.group(0)
    m = re.search(ADULTS_ONLY, text, re.I)
    return (ADULT_AGE, m.group(0)) if m else (None, None)


def parse_pregnancy_warning(text: str) -> str | None:
    m = re.search(r"(?:not\s+(?:recommended|suitable|to\s+be\s+used)|do\s+not\s+(?:use|take)|avoid)[^.]{0,40}"
                  r"(?:pregnan|breast\s*feed|lactat)\w*", text, re.I)
    return m.group(0) if m else None


def parse_directions(text: str) -> str | None:
    m = re.search(r"(?:take\s+)?(?:\d|one|two|three|1/2|half)\s+(?:tablets?|capsules?|caplets?|sachets?|softgels?|teaspoons?|tsp)"
                  r"\s+(?:[a-z]+\s+){0,3}?(?:(?:once|twice|thrice|\d\s*times)\s+(?:a|per)\s+day|(?:once|twice|thrice)\s+daily"
                  r"|daily|a\s+day|per\s+day)", text, re.I)
    return m.group(0).strip() if m else None


def read_label(text: str) -> dict:
    min_age, age_text = parse_age_limit(text)
    return {"amounts": parse_amounts(text), "min_age": min_age, "age_text": age_text,
            "pregnancy_warning": parse_pregnancy_warning(text), "directions": parse_directions(text)}


def strength_list(amounts: dict) -> list:
    return [{"nutrient": NUTRIENTS[n]["name"], "amount": format_amount(v, NUTRIENTS[n]["unit"])} for n, v in amounts.items()]


def find_target(*texts: str) -> dict | None:
    """Who the product is made for (Men, Women, Kids, 50+, Teens). "Centrum Silver 50+ Women" is both
    an age group and a sex. "Men and women" or "adults and children" means a general product."""
    text = " ".join(t for t in texts if t).lower()
    if re.search(r"\bmen\b.{0,12}\bwomen\b|\bwomen\b.{0,12}\bmen\b|adults? and children", text):
        text = re.sub(r"\b(wo)?men'?s?\b|\bchildren\b", " ", text)
    found = [{k: g[k] for k in ("key", "label", "phrase", "sex", "min_age", "max_age") if k in g}
             for g in TARGETS if re.search(g["pattern"], text)]
    if not found:
        return None
    target = found[0]
    for_one_sex = next((g for g in found[1:] if g.get("sex")), None)
    if for_one_sex and not target.get("sex"):
        target = {**target, "sex": for_one_sex["sex"], "label": f"{for_one_sex['label']} {target['label']}",
                  "phrase": f"{for_one_sex['phrase']} {target['phrase']}",
                  "min_age": max(target.get("min_age", 0), for_one_sex.get("min_age", 0))}
    return target


INGREDIENT_LINE = re.compile(r"([A-Za-z][A-Za-z0-9 ()\-/.,'%]{2,60}?)\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*(mg|mcg|µg|ug|iu|i\.u\.|g)\b", re.I)
NOT_INGREDIENT = re.compile(r"^(?:" + "|".join(LABEL_WORDS["not_an_ingredient"]) + r")\b", re.I)
FACTS_HEADING = re.compile(r"supplement\s*facts|nutrition\s*facts|each\s+(?:tablet|capsule|caplet|softgel|sachet)\s+contains|"
                           r"composition|ingredients|contains\s*:", re.I)
MAX_INGREDIENTS = 25


def all_ingredients(texts: list, inactive: list) -> list:
    """Every ingredient with an amount, plus inactive ones. checked = it has an NIH limit, so its amount is compared."""
    out, seen = [], set()
    for text in texts:
        for m in INGREDIENT_LINE.finditer(text or ""):
            name = re.sub(r"\s+", " ", m.group(1)).strip(" ,.-:")
            name = re.sub(r"^.*\b(?:supplement\s+facts|nutrition\s+facts|contains?|ingredients|composition)\b\s*:?\s*", "",
                          name, flags=re.I).strip()
            name = " ".join(name.split()[-5:])
            if len(name) < 3 or NOT_INGREDIENT.match(name) or name.lower() in seen:
                continue
            seen.add(name.lower())
            checked = bool(parse_amounts(f"{name} {m.group(2)} {m.group(3)}"))
            out.append({"name": name, "amount": f"{m.group(2)} {m.group(3)}", "checked": checked})
    for name in inactive or []:
        name = str(name).strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append({"name": name, "amount": None, "checked": False})
    return out[:MAX_INGREDIENTS]


def shows_full_list(raw_text: str, ingredients: list) -> bool:
    return bool(FACTS_HEADING.search(raw_text)) or len(ingredients) >= 3


CITIES = "|".join(LABEL_WORDS["pakistani_cities"])


def printed_maker(raw_text: str) -> str | None:
    m = re.search(r"(?:manufactured|marketed|mfd|mkt|made)\.?\s*(?:by|for)\s*:?\s*([a-z][a-z&.'() -]{2,40}?)"
                  rf"(?=\s*(?:,|\.\s|reg\b|{CITIES}|\d|$))", raw_text, re.I)
    return m.group(1).strip() if m else None


def registration_number(raw_text: str) -> str | None:
    """DRAP registration or enlistment number printed on Pakistani packs."""
    m = re.search(r"(?:reg(?:istration)?\.?\s*(?:no|#)|enlistment\s*no|drap)\.?\s*[:#\-]?\s*([a-z0-9][a-z0-9\-/]{3,})",
                  raw_text, re.I)
    return m.group(1).upper() if m else None


NOT_A_BRAND = set(LABEL_WORDS["not_a_brand"])


def brand_on_pack(segments: list, is_medicine) -> str | None:
    """For an unknown product: the first word near the top of the pack that isn't a vitamin, unit or common label word."""
    for segment in segments[:6]:
        for word in re.findall(r"[A-Za-z][A-Za-z'&-]{3,20}", segment["text"]):
            if word.lower() not in NOT_A_BRAND and not is_medicine(word):
                return word.capitalize() if word.islower() or word.isupper() else word
    return None


def label_order(amounts: dict, raw_text: str) -> list:
    """Nutrients in the order the label prints them; the first is usually the main one."""
    def position(n):
        m = re.search(NUTRIENTS[n]["label_names"], raw_text or "", re.I)
        return m.start() if m else len(raw_text or "")
    return sorted(amounts, key=position)
