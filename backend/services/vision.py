"""The two image models: CLIP checks a photo shows a supplement pack, EasyOCR reads its text.
Both load on first use (they take a few seconds), and warm_up() does that at server start."""
import numpy as np
from PIL import Image, ImageDraw

from datasets import VISION_LABELS
from settings import CLIP_MIN_SCORE, CLIP_MODEL

SENTENCES = VISION_LABELS["valid"] + VISION_LABELS["invalid"]
_models = {}


def _clip():
    if "clip" not in _models:
        import torch
        from transformers import CLIPModel, CLIPProcessor
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _models["clip"] = (CLIPModel.from_pretrained(CLIP_MODEL).to(device), CLIPProcessor.from_pretrained(CLIP_MODEL), device)
    return _models["clip"]


def _ocr():
    if "ocr" not in _models:
        import easyocr
        _models["ocr"] = easyocr.Reader(["en"], gpu=False)
    return _models["ocr"]


def is_supplement_photo(image: Image.Image) -> tuple:
    """(True, "") or (False, why). Zero-shot: CLIP scores the photo against every sentence in vision_labels.json."""
    import torch
    model, processor, device = _clip()
    inputs = processor(text=SENTENCES, images=image, return_tensors="pt", padding=True).to(device)
    with torch.no_grad():
        scores = model(**inputs).logits_per_image.softmax(dim=1)[0].cpu().numpy()
    pack_score = float(scores[:len(VISION_LABELS["valid"])].sum())
    if pack_score >= CLIP_MIN_SCORE:
        return True, ""
    closest = SENTENCES[int(np.argmax(scores))].replace("a photo of ", "")
    return False, f"looks like {closest}, not a supplement ({pack_score:.0%} supplement)."


def read_text(image: Image.Image, turn: bool = False) -> list:
    """Text boxes on the photo: [{"text", "conf", "h"}], h = text height (bigger text is more likely the name).
    turn=True also tries the photo turned 90, 180 and 270 degrees, for packs photographed sideways."""
    rotations = [90, 180, 270] if turn else None
    segments = []
    for box, text, confidence in _ocr().readtext(np.array(image), detail=1, rotation_info=rotations):
        ys = [point[1] for point in box]
        segments.append({"text": text, "conf": float(confidence), "h": max(ys) - min(ys)})
    return segments


def warm_up():
    """The first run of each model is slow, so do it once now instead of on the user's first scan."""
    image = Image.new("RGB", (400, 160), "white")
    ImageDraw.Draw(image).text((20, 60), "Vitamin C 500 mg", fill="black")
    read_text(image)
    is_supplement_photo(image)
    print("OCR and photo check ready")
