"""The safety report, questions about a scanned supplement, and the user's saved reports."""
from fastapi import APIRouter, Depends, HTTPException

from datasets import MEDICATIONS
from schemas import Person, Question, ReportRequest
from services import ai, database, label_reader, pharmacist, products, report
from services.matching import grams_of
from services.database import account_holder, current_account, current_user
from routes.scans import load_scan

router = APIRouter()


def corrected_product(scan: dict, typed: str) -> tuple:
    """The user changed the scanned name: work out the product (and maybe its maker) again from what they typed."""
    product, company, label = dict(scan["product"]), dict(scan["company"]), dict(scan["label"])
    product.update(name=typed, source="user", product_key=products.product_for_name(typed, product["ingredients"])
                   or (products.product_for_amounts(label["amounts"], scan["ocr_text"]) if label.get("amounts") else None))
    label["target"] = label_reader.find_target(typed) or label.get("target")
    if company["status"] in ("not_found", "unregistered"):
        brand, product_key, _ = products.match_brand(grams_of(typed))
        company.update(products.verify_maker(products.brand_owners(brand, product_key), None, company.get("printed_name")))
    return product, company, label


def person_of(data: Person) -> dict:
    """What the checks and the AI get about the user: never their name, email or date of birth."""
    female = data.sex == "female"
    return {"age": data.age, "sex": data.sex, "pregnant": female and data.pregnant, "breastfeeding": female and data.breastfeeding,
            "periods": ("yes" if data.periods == "irregular" else data.periods) if female else None,
            "conditions": data.conditions,
            "medicine_names": [MEDICATIONS[k]["name"] for k in data.medicines] + data.other_medicines,
            "supplements": data.other_supplements}


def product_for(data, scan: dict) -> tuple:
    """(product, company, label) with the user's correction of the name applied, if they typed one."""
    product, company, label = scan["product"], scan["company"], scan["label"]
    typed = (data.supplement_name or "").strip()
    if typed and typed != product["name"]:
        if products.is_medicine(typed):
            raise HTTPException(422, f"{typed} is a medicine, not a supplement. MediSafe only checks vitamins, minerals "
                                     "and herbal supplements.")
        product, company, label = corrected_product(scan, typed)
        product["supported"] = bool(product["product_key"] or label.get("amounts"))
    return product, company, label


@router.post("/safety-report")
def safety_report(data: ReportRequest, account: dict = Depends(current_account)):
    scan = load_scan(data.scan_id)
    product, company, label = product_for(data, scan)
    supported = product.get("supported")
    if not product["name"]:
        raise HTTPException(400, "Product name unknown. Please type the supplement name.")
    if not supported:
        raise HTTPException(422, f"We don't have information on {product['name']}. MediSafe checks vitamins, minerals "
                                 "and herbal supplements only, not medicines.")

    female = data.sex == "female"
    person = person_of(data)
    result, ai_mode = report.build(scan, product, company, label, person, data.reasons, data.medicines)
    response = {"query_id": None, "product": product, "company": company, "profile": person, "reasons": data.reasons,
                "report": result, "ai": {"used": bool(ai_mode), "mode": ai_mode, "problem": None if ai_mode else ai.status["problem"]}}
    saved = {**person, "medicines": data.medicines,
             "female_status": {"periods": data.periods, "pregnant": person["pregnant"], "breastfeeding": person["breastfeeding"]} if female else None}
    if not account["guest"]:                                   # a guest's reports are not kept
        response["query_id"] = database.save_report(account["uid"], scan, product, company, saved, data.reasons, response)
    return response


@router.post("/ask")
def ask(data: Question, user: str = Depends(current_user)):
    """A question about the scanned supplement, answered only from the NIH knowledge base, with citations."""
    scan = load_scan(data.scan_id)
    product, _, label = product_for(data, scan)
    info = products.product_info(product["product_key"])
    nutrients = list(dict.fromkeys([*info.get("nutrients", []), *label.get("amounts", {})]))
    return pharmacist.answer_question(data.question, product, label, person_of(data), nutrients, products.herbs_of(info))


@router.get("/history")
def history(account: dict = Depends(current_account)):
    return {"history": [] if account["guest"] else database.history(account["uid"])}


@router.get("/report/{query_id}")
def saved_report(query_id: str, user: str = Depends(account_holder)):
    found = database.saved_report(user, query_id)
    if not found:
        raise HTTPException(404, "Report not found.")
    return found
