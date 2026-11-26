"""Finds the full ingredient list of a product when the photo shows only the front of the pack:
first in the NIH Dietary Supplement Label Database, then on the brand's own page (Claude web search).
Only the same brand's label is ever used, and amounts are never guessed."""
import json
import re
import urllib.parse
import urllib.request

import settings
from services import ai

IGNORED_WORDS = {"mg", "mcg", "iu", "capsules", "tablets"}
MIN_NAME_OVERLAP = 0.5


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 1 and w not in IGNORED_WORDS}


def _dsld(path: str, **params) -> dict | None:
    if settings.DATA_GOV_API_KEY:
        params["api_key"] = settings.DATA_GOV_API_KEY
    request = urllib.request.Request(f"{settings.DSLD_API}/{path}?" + urllib.parse.urlencode(params),
                                     headers={"User-Agent": "MediSafe/2.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())
    except (OSError, ValueError):
        return None


def from_dsld(brand: str, product: str) -> dict | None:
    data = _dsld("search-filter", q=f"{brand} {product}".strip(), size=10, status=1)
    hits = (data or {}).get("hits", [])
    hits = hits.get("hits", []) if isinstance(hits, dict) else hits
    wanted = _words(product) - _words(brand)
    best, best_score = None, 0.0
    for hit in hits:
        source = hit.get("_source") or {}
        if brand and brand.lower() not in (source.get("brandName") or "").lower():
            continue
        score = len(wanted & _words(source.get("fullName"))) / max(1, len(wanted))
        if score > best_score:
            best, best_score = hit, score
    if not best or best_score < MIN_NAME_OVERLAP:
        return None
    label = _dsld(f"label/{best.get('_id')}")
    if not label:
        return None
    lines = []

    def collect(rows):
        for row in rows or []:
            quantity = next((q for q in row.get("quantity") or [] if q.get("quantity")), None)
            if quantity and row.get("name"):
                unit = str(quantity.get("unit") or "").split()[0] if quantity.get("unit") else ""
                amount = f"{quantity['quantity']:g}" if isinstance(quantity["quantity"], (int, float)) else quantity["quantity"]
                lines.append(f"{row['name']} {amount} {unit}")
            collect(row.get("nestedRows"))

    collect(label.get("ingredientRows"))
    inactive = [i["name"] for i in (label.get("otheringredients") or {}).get("ingredients") or [] if i.get("name")]
    return {"lines": lines, "inactive": inactive, "name": (label.get("fullName") or "").strip(),
            "source": "NIH Dietary Supplement Label Database", "url": settings.DSLD_LABEL_URL.format(best.get("_id"))}


WEB_PROMPT = """Find the official "Supplement Facts" (ingredients and amounts per serving) of this exact product: "{product}".
Use the brand's own website or a large online pharmacy. Answer ONLY with JSON:
{{"found": true, "product_name": "...", "source_url": "...", "ingredients": ["each active ingredient with its amount per serving"],
"other_ingredients": ["inactive ingredients"]}}
If you are not sure it is this exact product, answer {{"found": false}}. Never guess amounts."""


def from_web(brand: str, product: str) -> dict | None:
    if not settings.ANTHROPIC_API_KEY or not ai.available():
        return None
    body = {"max_tokens": 1200, "messages": [{"role": "user", "content": WEB_PROMPT.format(product=f"{brand} {product}".strip())}],
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]}
    try:
        data = ai.claude_messages(body, settings.WEB_LOOKUP_TIMEOUT)
    except OSError as e:
        print(f"Web lookup failed: {e.__class__.__name__}")
        return None
    text = ai.response_text(data or {})
    found = ai.read_json(text[text.rfind('{"found"'):] if '{"found"' in text else text)
    if not found or not found.get("found") or not found.get("ingredients"):
        return None
    return {"lines": [str(x) for x in found["ingredients"]][:30], "inactive": [str(x) for x in found.get("other_ingredients") or []][:20],
            "name": found.get("product_name") or "", "source": "the product's page online", "url": found.get("source_url")}


def look_up(brand: str | None, product: str | None) -> dict | None:
    if not (brand or product):
        return None
    product = re.sub(r"\s*supplement$", "", product or "", flags=re.I)
    if brand and product.lower().startswith(brand.lower()):
        product = product[len(brand):].strip()
    return from_dsld(brand or "", product) or from_web(brand or "", product)
