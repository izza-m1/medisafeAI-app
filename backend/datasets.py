"""Loads every file in backend/data once, when the server starts. Other modules import from here."""
import json
import os

from settings import DATA_DIR


def load(filename: str) -> dict:
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


NUTRIENTS = load("nutrients.json")["nutrients"]
GROUPS = load("product_groups.json")["groups"]
PRODUCTS = {p["name"]: p for p in load("products.json")["products"]}
TARGETS = load("targets.json")["groups"]
COMPANIES = load("companies.json")["companies"]
REASONS = load("reasons.json")
FOOD_INTERACTIONS = load("food_interactions.json")["interactions"]
_foods = load("foods.json")
FOODS, FOOD_GROUPS = _foods["foods"], _foods["groups"]
MEDICATIONS = {m["key"]: m for m in load("medications.json")["medicines"]}
MEDICINE_NAMES = load("medicine_names.json")
VISION_LABELS = load("vision_labels.json")
EMAIL_RULES = load("email_rules.json")
LABEL_WORDS = load("label_words.json")
DSLD = {p["name"]: p for p in load("dsld_products.json")["products"]}
KNOWLEDGE_SOURCES = load("knowledge_sources.json")

# Every brand name or label word that identifies a product: "neurobion" -> ("Neurobion", "Neurobion")
BRAND_ALIASES = {}       # alias -> (brand name, product name)
INGREDIENT_ALIASES = {}  # alias -> product name, e.g. "ferrous sulphate" -> "Iron Supplement"
for product in PRODUCTS.values():
    for brand, info in product.get("brands", {}).items():
        for alias in info["aliases"]:
            BRAND_ALIASES[alias] = (brand, product["name"])
    for alias in product["aliases"]:
        INGREDIENT_ALIASES[alias] = product["name"]

# Ingredient name -> knowledge base topic, e.g. "Turmeric/Curcumin" -> "turmeric", "Iron" -> "iron"
TOPIC_OF = {n["name"]: key for key, n in NUTRIENTS.items()}
for t in KNOWLEDGE_SOURCES["topics"]:
    for name in t["names"]:
        TOPIC_OF[name] = t["topic"]
