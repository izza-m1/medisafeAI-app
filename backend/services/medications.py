"""Supplement and medicine interactions the user's own medicines may have, from medications.json (NIH ODS)."""
from datasets import MEDICATIONS


def choices() -> list:
    return [{"key": m["key"], "name": m["name"]} for m in MEDICATIONS.values()]


def checks(medicine_keys: list, nutrients: list) -> list:
    """One check per interaction between a medicine the user takes and a nutrient in this product."""
    out = []
    for key in medicine_keys:
        medicine = MEDICATIONS.get(key)
        for interaction in (medicine or {}).get("interactions", []):
            if interaction["nutrient"] in nutrients:
                out.append({"key": "medicine", "title": medicine["name"], "status": interaction["status"],
                            "text": interaction["text"], "source": interaction["source"]})
    return out
