"""Turns photos of a pack (or a name typed in search) into a scan: which product it is, who made it,
and what its label says. Scans wait in memory until the user asks for the report."""
import base64
import io
import re
import uuid

from PIL import Image

import settings
from datasets import BRAND_ALIASES, DSLD, INGREDIENT_ALIASES
from services import ai, composition, label_reader as labels, products, vision
from services.matching import grams_of, word_grams
from services.privacy import redact

_scans = {}

READ_LABEL_PROMPT = """These photos show ONE supplement or medicine pack (front, back or blister strip).
OCR text from the photos (may contain errors): "{ocr_text}"

Return ONLY this JSON:
{{"product_name": "name exactly as printed", "brand": "the brand name alone", "manufacturer": "company after 'Manufactured by' or 'Marketed by'",
"active_ingredients": ["each ingredient with its amount per tablet as printed"], "other_ingredients": ["inactive ingredients if printed"],
"warnings": "age or pregnancy warnings exactly as printed", "directions": "dosage directions as printed",
"is_supplement": "true for a vitamin, mineral or herbal supplement, false for a medicine"}}
Read only what is printed. Use null for anything not clearly readable. Never guess a brand from the ingredients."""


def get(scan_id: str) -> dict | None:
    return _scans.get(scan_id) if re.fullmatch(r"[0-9a-f]{32}", scan_id or "") else None


def _save(result: dict, photo: Image.Image | None) -> dict:
    scan_id = uuid.uuid4().hex
    result = {"scan_id": scan_id, **result}
    _scans[scan_id] = {**result, "thumb": _thumbnail(photo) if photo else None}
    return result


def public(scan: dict) -> dict:
    return {k: v for k, v in scan.items() if k != "thumb"}


def _thumbnail(image: Image.Image) -> str:
    img = image.copy()
    img.thumbnail((settings.THUMBNAIL_SIZE, settings.THUMBNAIL_SIZE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _read_with_ai(images: list, ocr_text: str) -> dict:
    """Only used when OCR found no product name (blurry or scratched packs)."""
    prompt = READ_LABEL_PROMPT.format(ocr_text=redact(ocr_text)[:1500])
    content = [*(ai.image_block(i) for i in images[:2]), {"type": "text", "text": prompt}]
    return ai.ask(content, 400, timeout=settings.LABEL_READ_TIMEOUT) or {}


def _found_anything(segments: list) -> bool:
    text = " ".join(s["text"] for s in segments)
    return bool(products.match_brand(word_grams(segments))[0] or products.find_ingredients(text)
                or products.is_medicine(text) or labels.parse_amounts(text))


def scan_photos(images: list) -> dict:
    segments = [s for image in images for s in vision.read_text(image)]
    if not _found_anything(segments):
        segments = vision.read_text(images[0], turn=True)       # the pack may be sideways or upside down
    raw_text = " ".join(s["text"] for s in segments)

    brand, product_key, score = products.match_brand(word_grams(segments))
    ingredients = products.find_ingredients(raw_text)
    read_by_ai = {} if brand else _read_with_ai(images, raw_text)

    if brand:
        name, source = brand, "ocr"
    elif read_by_ai.get("product_name"):
        name, source = read_by_ai["product_name"], "ai_vision"
        product_key = products.product_for_name(name, ingredients)
    elif ingredients:
        name = " + ".join(re.sub(r"\s*supplement$", "", i, flags=re.I) for i in ingredients[:2]) + " supplement"
        source, product_key = "ingredients", ingredients[0]
    else:
        name, source = None, "not_found"

    label = labels.read_label(raw_text)
    if read_by_ai:
        seen = labels.read_label(" ".join([*(read_by_ai.get("active_ingredients") or []),
                                           read_by_ai.get("warnings") or "", read_by_ai.get("directions") or ""]))
        label["amounts"] = {**seen["amounts"], **label["amounts"]}
        for key in ("min_age", "age_text", "pregnancy_warning", "directions"):
            label[key] = label[key] or seen[key]
    label["strength"] = labels.strength_list(label["amounts"])
    if label["amounts"] and not product_key:
        product_key = products.product_for_amounts(label["amounts"], raw_text)
    if label["amounts"] and not name:
        name, source = products.name_from_amounts(label["amounts"], raw_text), "composition"

    label["target"] = labels.find_target(name or "", raw_text)
    if name and label["target"] and label["target"]["label"].lower().rstrip("s") not in name.lower():
        name = f"{name} {label['target']['label']}"
    label["all_ingredients"] = labels.all_ingredients([*(s["text"] for s in segments), *(read_by_ai.get("active_ingredients") or [])],
                                                      read_by_ai.get("other_ingredients") or [])
    label["facts_seen"] = labels.shows_full_list(raw_text, label["all_ingredients"])

    brand_seen = None if brand else (read_by_ai.get("brand") or labels.brand_on_pack(segments, products.is_medicine))
    if brand_seen and source == "composition" and brand_seen.lower() not in name.lower():
        name = f"{brand_seen} {name.replace(' supplement', '')}"
    printed = labels.printed_maker(raw_text) or read_by_ai.get("manufacturer")
    registered = products.match_company(raw_text) or products.match_company(printed)
    if not brand and name and source != "ingredients":
        brand, matched_product, _ = products.match_brand(grams_of(name))
        product_key = product_key or matched_product
    maker = products.verify_maker(products.brand_owners(brand, product_key), registered, printed,
                                  bool(re.search(r"licen[cs]", raw_text, re.I)), brand_seen)

    medicine = read_by_ai.get("is_supplement") is False or (not brand and products.is_medicine(raw_text))
    supported = not medicine and bool(product_key or ingredients or label["amounts"] or read_by_ai.get("is_supplement") is True)
    return _save({
        "product": {"name": name, "identified": name is not None, "source": source, "supported": supported,
                    "medicine": medicine, "match_score": score if brand else None, "from_label": bool(label["amounts"]),
                    "product_key": product_key, "ingredients": ingredients or (read_by_ai.get("active_ingredients") or [])},
        "company": {**maker, "printed_name": printed, "registration_no": labels.registration_number(raw_text)},
        "label": label,
        "ocr_text": raw_text,
    }, images[0])


def scan_name(name: str) -> dict | None:
    """Search on the home screen. A product picked by name goes through the same report as a scanned one,
    with its strength from the NIH label database when the product is there."""
    name = name.strip()
    brand = next((b for b, _ in BRAND_ALIASES.values() if b.lower() == name.lower()), None)
    product_key = products.product_for_name(name)
    if not product_key or products.is_medicine(name):
        return None
    nih = DSLD.get(product_key)
    label = labels.read_label(nih["label_text"] if nih else "")
    label["amounts"] = dict(nih["strength"]) if nih else {}
    label["strength"] = labels.strength_list(label["amounts"])
    label["target"] = labels.find_target(name)
    owners = products.brand_owners(brand, product_key) or ([nih["maker"]] if nih and nih.get("maker") else [])
    return _save({
        "product": {"name": brand or name, "identified": True, "source": "search", "supported": True, "medicine": False,
                    "match_score": None, "product_key": product_key, "ingredients": [], "from_label": bool(nih)},
        "company": {**products.verify_maker(owners, None, None), "printed_name": None, "registration_no": None},
        "label": label,
        "ocr_text": "",
    }, None)


def add_full_label(scan: dict) -> bool:
    """Front-only photo: look up the full ingredient list and add it. The photo's own amounts always win."""
    company = scan["company"]
    brand = company.get("name") if company.get("status") in ("brand_seen", "verified", "verified_by_brand", "unregistered") else None
    found = composition.look_up(brand, scan["product"].get("name"))
    if not found:
        return False
    text = " ".join(found["lines"])
    looked_up = labels.read_label(text)
    if not looked_up["amounts"]:
        return False
    label = scan["label"]
    label["amounts"] = {**looked_up["amounts"], **label.get("amounts", {})}
    label["strength"] = labels.strength_list(label["amounts"])
    label["all_ingredients"] = labels.all_ingredients(found["lines"], found["inactive"])
    label["facts_seen"] = True
    label["composition_source"] = {"name": found["source"], "url": found.get("url"), "product": found.get("name")}
    product = scan["product"]
    product["product_key"] = product.get("product_key") or products.product_for_amounts(label["amounts"], text)
    if not product.get("name"):
        product.update(name=found.get("name") or products.name_from_amounts(label["amounts"], text), identified=True,
                       source="composition")
    product.update(supported=True, from_label=True)
    return True


def name_status(name: str) -> str:
    """Typed name -> "medicine", "ok" (we can check it) or "unknown"."""
    if products.is_medicine(name):
        return "medicine"
    return "ok" if products.product_for_name(name) else "unknown"


def known_names() -> list:
    names = {brand for brand, _ in BRAND_ALIASES.values()} | set(INGREDIENT_ALIASES.values()) | set(DSLD)
    return sorted(names, key=str.lower)
