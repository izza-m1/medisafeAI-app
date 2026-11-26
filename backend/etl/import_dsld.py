"""Downloads real supplement labels from the NIH Dietary Supplement Label Database (https://dsld.od.nih.gov)
into backend/data/dsld_products.json. Free; an api.data.gov key (DATA_GOV_API_KEY in backend/.env) raises the limit.

Run from the backend folder:  python etl/import_dsld.py
Downloaded labels are cached in etl/dsld_cache.json, so a stopped run carries on where it stopped."""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import settings
from datasets import NUTRIENTS
from services import limits
from services.label_reader import convert

HERE = os.path.dirname(os.path.abspath(__file__))
SEARCH = json.load(open(os.path.join(HERE, "dsld_search.json"), encoding="utf-8"))
CACHE = os.path.join(HERE, "dsld_cache.json")
OUT = os.path.join(settings.DATA_DIR, "dsld_products.json")
REFERENCE_ADULT = {"age": 30, "sex": "female", "periods": "yes", "pregnant": False, "breastfeeding": False}
MULTIVITAMIN_MIN_NUTRIENTS = 5


class RateLimited(Exception):
    pass


def get(path: str, **params) -> dict | None:
    if settings.DATA_GOV_API_KEY:
        params["api_key"] = settings.DATA_GOV_API_KEY
    url = f"{settings.DSLD_API}/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "MediSafe/2.0", "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=40) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimited()
        except (OSError, ValueError):
            pass
        time.sleep(1.5 * (attempt + 1))
    print(f"  could not read {path}")
    return None


def ingredient_rows(rows: list):
    for row in rows or []:
        yield row
        yield from ingredient_rows(row.get("nestedRows"))


def strength_of(row: dict) -> tuple:
    """(nutrient, amount in our unit) for one ingredient row, or (None, None)."""
    text = f"{row.get('ingredientGroup') or ''} {row.get('name') or ''}"
    nutrient = next((n for n, info in NUTRIENTS.items() if re.search(info["label_names"], text, re.I)), None)
    for quantity in row.get("quantity") or [] if nutrient else []:
        try:
            value = float(quantity.get("quantity"))
        except (TypeError, ValueError):
            continue
        unit = (quantity.get("unit") or "").split()[0].lower() if quantity.get("unit") else ""
        if value > 0 and unit:
            return nutrient, convert(value, unit, nutrient)
    return None, None


def group_of(name: str, strength: dict, herbs: list) -> str:
    if re.search(r"prenatal|pregnan", name, re.I):
        return "prenatal"
    if herbs and len(strength) <= 1:
        return "herbal"
    if "iron" in strength and len(strength) < MULTIVITAMIN_MIN_NUTRIENTS:
        return "iron"
    return "vitamin_mineral" if strength else "general"


def product_of(label: dict) -> dict | None:
    brand, full = (label.get("brandName") or "").strip(), (label.get("fullName") or "").strip()
    if not full or label.get("offMarket") in (1, True, "1"):
        return None
    name = re.sub(r"\s+", " ", full if full.lower().startswith(brand.lower()) else f"{brand} {full}")[:70]
    strength, herbs = {}, []
    for row in ingredient_rows(label.get("ingredientRows")):
        nutrient, amount = strength_of(row)
        if nutrient and amount and nutrient not in strength:
            strength[nutrient] = round(amount, 3)
        text = f"{row.get('ingredientGroup') or ''} {row.get('name') or ''}"
        herbs += [herb for pattern, herb in SEARCH["herbs"].items() if re.search(pattern, text, re.I) and herb not in herbs]
    if not strength and not herbs:
        return None
    maker = next((str((c.get("contactDetails") or c)["name"]).strip() for c in label.get("contacts") or []
                  if (c.get("contactDetails") or c).get("name")), None)
    statements = " ".join(f"{s.get('type') or ''}: {s.get('notes')}" for s in label.get("statements") or [] if s.get("notes"))
    serving = (label.get("servingSizes") or [{}])[0]
    per = serving.get("minQuantity") or serving.get("quantity")
    return {"id": label.get("id"), "name": name, "brand": brand, "maker": maker, "group": group_of(name, strength, herbs),
            "nutrients": sorted(strength, key=lambda n: -strength[n] / (limits.daily_need(n, REFERENCE_ADULT) or float("inf"))),
            "strength": strength, "herbs": herbs,
            "serving": f"{per:g} {serving.get('unit') or ''}".strip() if isinstance(per, (int, float)) else None,
            "label_text": statements[:1500], "source": f"NIH DSLD label {label.get('id')}"}


def main():
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    ids = dict.fromkeys(cache.get("_ids", []))
    try:
        if not ids:
            for term in SEARCH["terms"]:
                data = get("search-filter", q=term, size=SEARCH["per_term"], status=1) or {}
                hits = data.get("hits", [])
                for hit in hits.get("hits", []) if isinstance(hits, dict) else hits:
                    ids.setdefault(str(hit["_id"]))
                print(f"  {term}: {len(ids)} products so far")
            cache["_ids"] = list(ids)
        missing = [i for i in ids if i not in cache]
        print(f"Reading {len(missing)} labels ({len(ids) - len(missing)} already cached)")
        with ThreadPoolExecutor(2) as pool:
            for label_id, label in zip(missing, pool.map(lambda i: get(f"label/{i}"), missing)):
                if label:
                    cache[label_id] = label
    except RateLimited:
        print("NIH rate limit reached. Run this again later, or add DATA_GOV_API_KEY to backend/.env.")
    finally:
        json.dump(cache, open(CACHE, "w", encoding="utf-8"))

    products, seen = [], set()
    for key, label in cache.items():
        product = product_of(label) if key != "_ids" and label else None
        if product and product["name"].lower() not in seen:
            seen.add(product["name"].lower())
            products.append(product)
    products.sort(key=lambda p: p["name"].lower())
    about = json.load(open(OUT, encoding="utf-8"))["_about"] if os.path.exists(OUT) else ""
    json.dump({"_about": about, "imported": time.strftime("%Y-%m-%d"), "products": products},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Saved {len(products)} products to {OUT}. Restart the backend to use them.")


if __name__ == "__main__":
    main()
