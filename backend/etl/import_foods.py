"""Adds official nutrient values from USDA FoodData Central to the everyday foods in data/foods.json.

Two steps, because the best USDA entry for a food has to be chosen by a person, not by the first search result
("lobia" must not become "green peas"):

  python -m etl.import_foods --candidates   writes etl/usda_candidates.json: the top USDA entries for each food
  (choose the right one and write its number as usda_fdc_id in data/foods.json)
  python -m etl.import_foods                fetches each chosen entry and saves its values in data/foods.json

Saved per food: the FDC id, USDA's own description, and the amounts per 100 g that the food interactions are about
(calcium, iron, vitamin C, fat, caffeine, fibre). Needs DATA_GOV_API_KEY (or USDA_API_KEY) in backend/.env."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import settings

FDC_API = "https://api.nal.usda.gov/fdc/v1"
FDC_PAGE = "https://fdc.nal.usda.gov/food-details/{}/nutrients"
DATA_TYPES = "Foundation,SR Legacy"          # USDA's generic foods; branded and mixed dishes are left out
NUTRIENT_IDS = {1087: "calcium_mg", 1089: "iron_mg", 1162: "vitamin_c_mg", 1004: "fat_g", 1057: "caffeine_mg", 1079: "fiber_g"}
FOODS_FILE = os.path.join(settings.DATA_DIR, "foods.json")
CANDIDATES_FILE = os.path.join(settings.BASE_DIR, "etl", "usda_candidates.json")
CANDIDATES_PER_FOOD = 8
RETRIES = 6


def get(path: str, **params) -> dict:
    """One FoodData Central request. USDA's server refuses some requests at random (400 from nginx), so retry."""
    url = f"{FDC_API}/{path}?{urllib.parse.urlencode({'api_key': settings.DATA_GOV_API_KEY, **params})}"
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            if e.code not in (400, 429, 500, 502, 503) or attempt == RETRIES - 1:
                raise
        except (urllib.error.URLError, TimeoutError):        # slow or dropped connection to USDA
            if attempt == RETRIES - 1:
                raise
        time.sleep(3 * (attempt + 1))
    return {}


def amounts(food: dict) -> dict:
    found = {}
    for n in food.get("foodNutrients", []):
        number = n.get("nutrient", {}).get("id") or n.get("nutrientId")
        if number in NUTRIENT_IDS:
            found[NUTRIENT_IDS[number]] = n.get("amount", n.get("value"))
    return {name: found.get(name) for name in NUTRIENT_IDS.values()}


def candidates(data: dict) -> None:
    """Saved after every food, so a run that stops halfway carries on from where it stopped."""
    out = {}
    if os.path.exists(CANDIDATES_FILE):
        with open(CANDIDATES_FILE, encoding="utf-8") as f:
            out = json.load(f)
    for food in data["foods"]:
        if out.get(food["name"]):
            continue
        try:
            found = get("foods/search", query=food["usda_query"], dataType=DATA_TYPES, pageSize=CANDIDATES_PER_FOOD)
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  {food['name']}: USDA did not answer ({getattr(e, 'code', e)}), run again to retry it")
            continue
        out[food["name"]] = [{"fdc_id": f["fdcId"], "description": f["description"], "type": f["dataType"]}
                             for f in found.get("foods", [])]
        with open(CANDIDATES_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"  {food['name']}: {len(out[food['name']])} candidates")
    missing = [f["name"] for f in data["foods"] if not out.get(f["name"])]
    print(f"Saved {CANDIDATES_FILE}" + (f". Still missing: {', '.join(missing)}" if missing else ". All foods done."))


def save(data: dict) -> None:
    with open(FOODS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def values(data: dict) -> None:
    """Saved after every food; foods that already have the chosen entry's values are not fetched again."""
    for food in data["foods"]:
        if not food.get("usda_fdc_id"):
            print(f"  {food['name']}: no usda_fdc_id chosen yet, skipped")
            continue
        if (food.get("usda") or {}).get("fdc_id") == food["usda_fdc_id"]:
            continue
        try:
            entry = get(f"food/{food['usda_fdc_id']}")
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  {food['name']}: USDA did not answer ({getattr(e, 'code', e)}), run again later")
            continue
        food["usda"] = {"fdc_id": food["usda_fdc_id"], "description": entry.get("description"),
                        "per_100g": amounts(entry), "url": FDC_PAGE.format(food["usda_fdc_id"])}
        save(data)
        print(f"  {food['name']:28} -> {entry.get('description')}")
    missing = [f["name"] for f in data["foods"] if f.get("usda_fdc_id") and not f.get("usda")]
    print("All chosen foods have their USDA values." if not missing else f"Still missing: {', '.join(missing)}. Run again.")


def main():
    if not settings.DATA_GOV_API_KEY:
        sys.exit("Add DATA_GOV_API_KEY (or USDA_API_KEY) to backend/.env first (free from https://api.data.gov/signup).")
    with open(FOODS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    if "--candidates" in sys.argv:
        candidates(data)
        return
    values(data)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
