"""Decides if a product suits this person. Every check is ok, caution or stop, and the verdict is the most
serious one. The rules and numbers come from backend/data (NIH ODS and NIH NCCIH), never from the AI."""
from datasets import GROUPS, NUTRIENTS
from services import dosage, limits
from services.label_reader import format_amount
from services.products import product_info

RANK = {"ok": 0, "info": 0, "caution": 1, "stop": 2}
VERDICT = {"ok": "Safe", "info": "Safe", "caution": "Use with caution", "stop": "Not safe"}
RULE_STATUS = {"ok": "ok", "ask_doctor": "caution", "avoid": "stop"}
ADULT_AGE = 18
CHILD_AGE = 14               # groups can set their own child_age in product_groups.json
YOUNG_CHILD_AGE = 12         # most adult supplements are labelled for ages 12 and over
MULTIVITAMIN_MIN_NUTRIENTS = 5
SEX_WORD = {"male": "men", "female": "women"}
PACK = "the pack's label"


def worst(checks: list) -> str:
    return max((c["status"] for c in checks), key=RANK.get, default="ok")


def verdict_of(checks: list) -> str:
    return VERDICT[worst(checks)]


def assess(product_key: str | None, label: dict, person: dict) -> dict:
    product = product_info(product_key)
    group = GROUPS[product["group"]]
    checks, notes = [], []

    def add(key, title, status, text, source):
        checks.append({"key": key, "title": title, "status": status, "text": text, "source": source})

    if product["group"] == "not_supplement":
        add("product", "Product", "stop", group["all"]["text"], group["source"])
        return {"checks": checks, "dosage": None, "notes": [], "verdict": "Not safe"}

    amounts = {n: v for n, v in label.get("amounts", {}).items() if n in NUTRIENTS}
    over = limits.over_limit(amounts, person["age"])
    _age_checks(add, product_key, product, group, label, person, amounts, over)
    _sex_and_pregnancy_checks(add, product, group, label, person)
    if product.get("note"):
        notes.append(product["note"])
    return {"checks": checks, "dosage": dosage.plan(amounts, label.get("directions"), person, over),
            "notes": notes, "verdict": verdict_of(checks)}


def _age_checks(add, product_key, product, group, label, person, amounts, over):
    age, target = person["age"], label.get("target")
    child_age = group.get("child_age", CHILD_AGE)
    many_nutrients = len(product.get("nutrients", [])) >= MULTIVITAMIN_MIN_NUTRIENTS or product["group"] == "prenatal"

    if target and target.get("sex") and person["sex"] != target["sex"]:
        you = ({"male": "Boys", "female": "Girls"} if age < ADULT_AGE else {"male": "Men", "female": "Women"})[person["sex"]]
        better = "children" if age < YOUNG_CHILD_AGE else SEX_WORD[person["sex"]]
        add("target", "Made for", "caution",
            f"Take with care: this is made for {SEX_WORD[target['sex']]}, and your gender is {person['sex']}. "
            f"{you} need different amounts (for example of iron), so a {better}'s or general formula suits you better.", PACK)

    if age < 1:
        add("age", "Age", "stop", "Supplements for babies under 1 year should only be given on a doctor's advice.", group["source"])
    elif target and target.get("min_age") and age < target["min_age"]:
        who = "adults" if target["min_age"] == ADULT_AGE else f"ages {target['min_age']} and over"
        advice = "Children need a children's formula with smaller amounts." if age < ADULT_AGE else "A general adult formula fits you better."
        add("age", "Age", "stop" if age < ADULT_AGE else "caution",
            f"This {target.get('phrase', target['label'])} formula is made for {who}. You are {age}. {advice}", PACK)
    elif target and target.get("max_age") and age > target["max_age"]:
        add("age", "Age", "caution", f"This is a {target.get('phrase', target['label'])} formula, made for ages up to "
            f"{target['max_age']}. At {age}, an adult formula fits your needs better.", PACK)
    elif label.get("min_age") and age < label["min_age"]:
        add("age", "Age", "stop", f"The pack says: \"{label['age_text']}\". You are {age}, so this product is not for you.", PACK)
    elif over:
        nutrient, amount, limit = over[0]
        unit, times = NUTRIENTS[nutrient]["unit"], amount / limit
        how_much = "twice" if 1.8 <= times <= 2.2 else f"{times:.0f} times" if times >= 2.5 else "more than"
        text = (f"One tablet has {format_amount(amount, unit)} of {NUTRIENTS[nutrient]['name']}, {how_much} the upper daily "
                f"limit for {limits.limit_group(nutrient, age)} ({format_amount(limit, unit)}).")
        if age < ADULT_AGE:
            add("age", "Age", "stop", text + " It is not suitable for you unless a doctor prescribed it.", NUTRIENTS[nutrient]["fact_sheet"])
        else:
            add("age", "Dose strength", "caution", text + " Fine for a short course. Taking it every day for months can cause harm, "
                "so use it long-term only if a doctor advises.", NUTRIENTS[nutrient]["fact_sheet"])
    elif (age < YOUNG_CHILD_AGE and not amounts and not (target and target.get("max_age"))
          and product["group"] in ("vitamin_mineral", "iron", "prenatal")):
        strict = many_nutrients or product["group"] == "iron"
        add("age", "Age", "stop" if strict else "caution",
            "This is an adult multivitamin. Children under 12 need a children's formula with smaller amounts." if many_nutrients else
            "Most adult supplements are for ages 12 and over. Use a children's formula, or the children's dose printed on the pack, "
            "and ask a doctor first.", group["source"])
    elif age < child_age and group.get("child"):
        add("age", "Age", RULE_STATUS[group["child"]["status"]], group["child"]["text"], group["source"])
    elif not product_key and not amounts and not label.get("min_age"):
        add("age", "Age", "caution", "We don't have age data for this product. Follow the age directions on the pack.", PACK)
    else:
        text = f"Suitable for age {age}."
        if label.get("min_age"):
            text += f" The pack says it is for ages {label['min_age']} and over."
        add("age", "Age", "ok", text, PACK if label.get("min_age") else group["source"])


def _sex_and_pregnancy_checks(add, product, group, label, person):
    age, female, kind = person["age"], person["sex"] == "female", product["group"]
    child_age = group.get("child_age", CHILD_AGE)

    if kind == "prenatal" and age >= child_age:
        if not female:
            add("sex", "Made for", RULE_STATUS[group["male"]["status"]], group["male"]["text"], group["source"])
        elif person.get("pregnant") or person.get("breastfeeding"):
            rule = group["pregnant"] if person.get("pregnant") else group["breastfeeding"]
            add("sex", "Made for", "ok", rule["text"], group["source"])
        else:
            rule = group["female_not_pregnant"]
            add("sex", "Made for", RULE_STATUS[rule["status"]], rule["text"], group["source"])
    elif kind == "iron" and age >= child_age and not person.get("pregnant"):
        if female and person.get("periods") in ("yes", "no"):
            add("periods", "Periods and iron", "ok" if person["periods"] == "yes" else "caution",
                group["periods"][person["periods"]], group["source"])
        elif not female and age > ADULT_AGE:
            add("sex", "Iron need", "caution", group["male_adult"], group["source"])

    if female and person.get("pregnant"):
        rule = product.get("pregnant") or group.get("pregnant")
        if label.get("pregnancy_warning"):
            add("pregnancy", "Pregnancy", "stop", f"The pack says: \"{label['pregnancy_warning']}\".", PACK)
        elif kind != "prenatal" and rule:
            add("pregnancy", "Pregnancy", RULE_STATUS[rule["status"]], rule["text"], group["source"])
    if female and person.get("breastfeeding") and kind != "prenatal":
        rule = product.get("breastfeeding") or group.get("breastfeeding")
        if rule:
            add("breastfeeding", "Breastfeeding", RULE_STATUS[rule["status"]], rule["text"], group["source"])
