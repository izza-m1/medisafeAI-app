"""Builds the safety report for one scan and one person.

Two layers decide the verdict:
  1. checks made from NIH numbers and rules (safety_rules, medications, reasons): age, dose, sex, pregnancy...
  2. the AI pharmacist (pharmacist.py), which researches the person's own conditions and medicines in the NIH
     knowledge base and can add concerns, each one citing the passage it comes from.
The verdict is the most serious check of both layers, so the AI can make it stricter but never safer."""
from datasets import DSLD, NUTRIENTS
from settings import DSLD_LABEL_URL
from services import food_guidance, medications, pharmacist, reasons, safety_rules
from services.products import herbs_of, product_info

NOT_HEALTH_CHECKS = {"reason": 1, "maker": 2, "label": 3, "composition": 4}
AI_CHECK_KEY = "ai_concern"   # shown after the health checks
BUY_TIP = "Buy from a licensed pharmacy."


def maker_check(company: dict, product_name: str, searched: bool) -> dict:
    """Only a maker that doesn't match the brand counts against the verdict; one we couldn't read is a buying tip."""
    status_text = {
        "verified": ("ok", f"The pack shows {company['name']}, "
                     + ("the official maker of this brand." if company.get("official") else "a registered manufacturer.")),
        "verified_by_brand": ("ok", f"The official maker of {product_name} is {' or '.join(company.get('official') or [])}. "
                              "Check that your pack shows this name. If it shows a different company, it may be fake."),
        "mismatch": ("caution", f"{product_name} is usually made by {company.get('expected')}, but this pack says {company['name']}. "
                     "Some brands are made under licence by another company. If your pack does not say \"under licence\", "
                     f"it may not be genuine. {BUY_TIP}"),
        "brand_seen": ("info", f"The pack shows the brand {company['name']}, which is not in our list of verified manufacturers, "
                       f"so we can't confirm it is genuine. {BUY_TIP}"),
        "unregistered": ("caution", f"The company on the pack ({company.get('printed_name')}) is not in our list of registered "
                         f"manufacturers, so we can't confirm it is genuine. {BUY_TIP}"),
    }
    fallback = (f"We don't have this product's maker in our data, so we can't confirm it is genuine. {BUY_TIP}" if searched else
                f"We couldn't see the maker's name in the photo, so we can't confirm it is genuine. {BUY_TIP}")
    status, text = status_text.get(company["status"], ("info", fallback))
    if company.get("registration_no"):
        text += f" Registration number on the pack: {company['registration_no']}. You can check it in the DRAP product registry."
    return {"key": "maker", "title": "Manufacturer", "status": status, "text": text, "source": "the pack's label"}


def label_check(label: dict, searched: bool, product_key: str | None) -> dict:
    """Says plainly where the amounts came from, or that the dose could not be checked."""
    nih = DSLD.get(product_key or "")
    if searched and nih:
        return {"key": "label", "title": "Label", "status": "info", "source": DSLD_LABEL_URL.format(nih["id"]),
                "text": "Strength and directions from the product's label in the NIH Dietary Supplement Label Database. "
                        "Check that they match the pack you have."}
    if not label.get("amounts"):
        how = "You searched by name and we have no official label for this product" if searched else \
              "We couldn't read the amounts on your pack and couldn't find its ingredient list"
        return {"key": "label", "title": "Label", "status": "caution", "source": "the pack's label",
                "text": f"{how}, so the dose was NOT checked. Only the general checks (age, pregnancy, maker) were done. "
                        "Scan the back of the pack, where the ingredient list is, or ask a pharmacist."}
    source = label.get("composition_source")
    extra = [i["name"] + (f" {i['amount']}" if i.get("amount") else "") for i in label.get("all_ingredients", []) if not i["checked"]]
    text = (f"Checked with the full ingredient list from {source['name']}: " if source else "Checked with the amounts printed on your pack: ") \
        + "; ".join(f"{s['nutrient']} {s['amount']}" for s in label["strength"]) \
        + ". Each amount is compared with the NIH limits for your age and sex."
    if extra:
        text += " Also on the label: " + ", ".join(extra[:8]) + ". These have no NIH limit, so they are listed, not checked."
    if source:
        text += " Your photo showed only the front, so we looked this product up. Check that the strength on your pack matches."
    if not label.get("facts_seen", True):
        text += " We only saw the front of the pack. Scan the back too, where the full ingredient list usually is."
    return {"key": "composition", "title": "What's in your pack", "status": "ok" if label.get("facts_seen", True) else "info",
            "text": text, "source": (source or {}).get("url") or "the pack's label"}


def headline(checks: list, verdict: str, ai_summary: str | None) -> tuple:
    """(title, tone, reason) for the top of the report: the most serious health problem first."""
    problems = sorted((c for c in checks if c["status"] in ("caution", "stop")),
                      key=lambda c: (c["key"] in NOT_HEALTH_CHECKS, c["status"] != "stop", NOT_HEALTH_CHECKS.get(c["key"], 0)))
    health = [c for c in problems if c["key"] not in NOT_HEALTH_CHECKS]
    reason_row = next((c for c in problems if c["key"] == "reason"), None)
    if reason_row and not health and verdict == "Use with caution":
        return "Not right for your reason", reason_row["status"], reason_row["text"]
    first = problems[0]["text"] if problems else None
    return None, None, ai_summary or first or "Based on your age and profile, this supplement suits you."


def ai_checks(concerns: list) -> list:
    """The AI's cited concerns, as rows of the safety checks list."""
    return [{"key": AI_CHECK_KEY, "title": c.get("title") or "From NIH research", "status": c["level"], "text": c["text"],
             "source": c["sources"][0]["url"], "citations": c["sources"], "ai": True} for c in concerns]


def build(scan: dict, product: dict, company: dict, label: dict, person: dict, user_reasons: list, medicine_keys: list) -> tuple:
    """(report, how the AI took part: None when it didn't)"""
    product_key = product["product_key"]
    info = product_info(product_key)
    nutrients = list(dict.fromkeys([*info.get("nutrients", []), *label.get("amounts", {})]))
    searched = scan["product"]["source"] == "search"

    personal = safety_rules.assess(product_key, label, person)
    reason_results = reasons.check_reasons(product["name"], product_key, label.get("amounts", {}), user_reasons)
    reason_row = reasons.summary_check(reason_results)
    checks = [maker_check(company, product["name"], searched), *([reason_row] if reason_row else []),
              label_check(label, searched, product_key), *medications.checks(medicine_keys, nutrients), *personal["checks"]]

    written = pharmacist.write_report(product, company.get("name"), label, person, user_reasons, checks,
                                      personal["dosage"], nutrients, herbs_of(info)) or {}
    checks += ai_checks(written.get("concerns", []))

    # A product that won't help with the user's reason is not unsafe: it gets "Use with caution" and the headline
    # "Not right for your reason" (shown red), so the user knows not to rely on it.
    verdict = safety_rules.verdict_of([c for c in checks if c["key"] != "reason"])
    if reason_row and reason_row["status"] != "ok" and verdict == "Safe":
        verdict = "Use with caution"
    summary = written.get("summary")
    title, tone, reason = headline(checks, verdict, summary["text"] if summary else None)

    foods = food_guidance.for_nutrients(nutrients, label.get("amounts", {}), person.get("supplements", []))
    dosage = dict(personal["dosage"] or {})
    if written.get("dosage_note"):
        dosage["note"] = written["dosage_note"]["text"]
    if dosage.get("summary") and not dosage["summary"].get("doctor_only") and foods["timing"]:
        dosage["summary"] = {**dosage["summary"], "when": foods["timing"]["text"]}     # from NIH facts, not the AI
    return {
        "is_safe_to_take": {"verdict": verdict, "title": title, "tone": tone, "reason": reason, "checks": checks,
                            "summary_sources": summary["sources"] if summary else []},
        "recommended_dosage": dosage,
        "notes": personal["notes"],
        "purpose_check": {"results": reason_results, "ai_note": (written.get("purpose_note") or {}).get("text"),
                          "ai_sources": (written.get("purpose_note") or {}).get("sources", [])},
        "actual_usage": written.get("usage") or None,
        "benefits": written.get("benefits", []),
        "side_effects": written.get("side_effects", []),
        "timing": foods["timing"],
        "tips": foods["tips"],
        "recommended_foods": foods["help"],
        "foods_to_avoid": foods["lower"],
        "other_supplements": foods["other_supplements"],
        "unrecognised_supplements": foods["unrecognised_supplements"],
        "fact_sheets": [{"nutrient": NUTRIENTS[n]["name"], "url": NUTRIENTS[n]["fact_sheet"]} for n in nutrients if n in NUTRIENTS],
        "ai_research": written.get("research", []),
        "ai_claims": written.get("claims"),
    }, (written.get("mode") if written else None)
