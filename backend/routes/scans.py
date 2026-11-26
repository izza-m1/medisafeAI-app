"""Scanning a pack, searching by name, and the steps before the report (full label lookup, reasons)."""
import io
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image, ImageOps

import settings
from schemas import ProductName, ReasonsRequest, ScanId
from services import products, reasons, scanner, vision

router = APIRouter()


def load_scan(scan_id: str) -> dict:
    scan = scanner.get(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found. Please scan the supplement again.")
    return scan


@router.post("/scan-supplement")
def scan_supplement(files: List[UploadFile] = File(...)):
    """1-4 photos of one pack (front, back, blister strip). Every photo must pass the CLIP check first."""
    if not 1 <= len(files) <= settings.MAX_PHOTOS:
        raise HTTPException(400, f"Upload 1-{settings.MAX_PHOTOS} photos of the same supplement.")
    images, problems = [], []
    for i, file in enumerate(files, 1):
        try:
            image = ImageOps.exif_transpose(Image.open(io.BytesIO(file.file.read()))).convert("RGB")
        except (OSError, ValueError):
            problems.append(f"Photo {i}: not a readable image file.")
            continue
        image.thumbnail((settings.PHOTO_SIZE, settings.PHOTO_SIZE))
        ok, why = vision.is_supplement_photo(image)
        if not ok:
            problems.append(f"Photo {i}: {why}")
        images.append(image)
    if problems:
        return {"success": False, "message": "Please upload photos of a supplement pack only.", "details": problems}
    return {"success": True, **scanner.scan_photos(images)}


@router.post("/search-product")
def search_product(data: ProductName):
    scan = scanner.scan_name(data.name)
    if not scan:
        raise HTTPException(404, f"We don't have {data.name.strip()} in our data.")
    return {"success": True, **scan}


@router.post("/check-name")
def check_name(data: ProductName):
    return {"status": scanner.name_status(data.name.strip())}


@router.get("/products")
def product_names():
    return {"products": scanner.known_names()}


@router.post("/lookup-composition")
def lookup_composition(data: ScanId):
    scan = load_scan(data.scan_id)
    if scan["product"].get("medicine"):
        raise HTTPException(422, "This is a medicine, not a supplement.")
    if not scanner.add_full_label(scan):
        raise HTTPException(404, "We couldn't find the full ingredient list for this product online.")
    return {"success": True, **scanner.public(scan)}


@router.post("/suggest-reasons")
def suggest_reasons(data: ReasonsRequest):
    """Options for 'Why do you take it?': only what this product is really used for."""
    scan = load_scan(data.scan_id)
    name = (data.name or "").strip() or scan["product"]["name"] or ""
    product_key = scan["product"]["product_key"]
    if name != scan["product"]["name"]:
        product_key = products.product_for_name(name, scan["product"]["ingredients"])
    person = {"age": data.age or 30, "sex": data.sex, "periods": "yes" if data.periods == "irregular" else data.periods}
    return {"reasons": reasons.suggested_reasons(name, product_key, scan["label"].get("amounts", {}), person)}
