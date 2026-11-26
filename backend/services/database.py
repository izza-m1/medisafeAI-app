"""Firebase: who is signed in (Authentication) and the saved data (Firestore).
Collections: users/<uid> = profile; search_query_data and search_response = one scan's input and its report,
sharing one document id. Without backend/firebase-key.json the app runs without accounts or history."""
import os

from fastapi import Header, HTTPException

import settings

enabled = os.path.exists(settings.FIREBASE_KEY) and not settings.TESTING
if enabled:
    import firebase_admin
    from firebase_admin import auth, credentials, firestore
    firebase_admin.initialize_app(credentials.Certificate(settings.FIREBASE_KEY))
    db = firestore.client()

LOCAL_USER = "local"


def current_account(authorization: str = Header(None)) -> dict:
    """The app sends 'Authorization: Bearer <Firebase ID token>'. Returns {"uid", "guest"}.
    guest: the user tapped "Try without an account" (Firebase anonymous sign-in); nothing of theirs is saved here."""
    if not enabled:
        return {"uid": LOCAL_USER, "guest": False}
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please sign in again.")
    try:
        token = auth.verify_id_token(authorization.split(" ", 1)[1])
    except (ValueError, auth.InvalidIdTokenError):
        raise HTTPException(401, "Your sign-in has expired. Please sign in again.")
    return {"uid": token["uid"], "guest": token.get("firebase", {}).get("sign_in_provider") == "anonymous"}


def current_user(authorization: str = Header(None)) -> str:
    """The signed-in user's uid (guests included)."""
    return current_account(authorization)["uid"]


def account_holder(authorization: str = Header(None)) -> str:
    """The uid of a user with a real account; guests are told to create one."""
    account = current_account(authorization)
    if account["guest"]:
        raise HTTPException(403, "Create a free account to save your profile and history.")
    return account["uid"]


def email_in_use(email: str) -> bool | None:
    """None when it can't be checked (no database)."""
    if not enabled:
        return None
    try:
        auth.get_user_by_email(email)
        return True
    except auth.UserNotFoundError:
        return False


def account_email(uid: str) -> str | None:
    return auth.get_user(uid).email if enabled and uid != LOCAL_USER else None


def load_profile(uid: str) -> dict | None:
    if not enabled:
        return None
    doc = db.collection("users").document(uid).get()
    return doc.to_dict() if doc.exists else None


def save_profile(uid: str, profile: dict) -> bool:
    if enabled:
        db.collection("users").document(uid).set({**profile, "updated": firestore.SERVER_TIMESTAMP}, merge=True)
    return enabled


def save_report(uid: str, scan: dict, product: dict, company: dict, person: dict, reasons: list, response: dict) -> str | None:
    """The scan's input in search_query_data, its report in search_response, both under the same new id."""
    if not enabled:
        return None
    query = db.collection("search_query_data").document()
    query.set({"user_id": uid, "input_image": scan["thumb"], "supplement_name": product["name"], "company": company.get("name"),
               "age": person["age"], "sex": person["sex"], "female_status": person.get("female_status"),
               "medicines": person.get("medicines", []), "reason_to_taking": reasons, "timestamp": firestore.SERVER_TIMESTAMP})
    report = response["report"]
    db.collection("search_response").document(query.id).set({
        "query_id": query.id, "user_id": uid, "is_safe_to_take": report["is_safe_to_take"],
        "actual_supplement_usage": report["actual_usage"], "benefits": report["benefits"],
        "recommended_dosage": report["recommended_dosage"], "side_effects": report["side_effects"],
        "recommended_foods": report["recommended_foods"], "foods_to_avoid": report["foods_to_avoid"],
        "full_report": {**response, "query_id": query.id}, "timestamp": firestore.SERVER_TIMESTAMP})
    return query.id


def history(uid: str) -> list:
    if not enabled:
        return []
    queries = list(db.collection("search_query_data").where(filter=firestore.FieldFilter("user_id", "==", uid)).stream())
    stamp = lambda d: d.to_dict().get("timestamp")
    queries.sort(key=lambda d: stamp(d).timestamp() if stamp(d) else 0, reverse=True)
    queries = queries[:settings.HISTORY_LIMIT]
    reports = {r.id: r for r in db.get_all([db.collection("search_response").document(q.id) for q in queries])} if queries else {}
    items = []
    for q in queries:
        data, report = q.to_dict(), reports.get(q.id)
        verdict = (report.get("is_safe_to_take") or {}).get("verdict") if report and report.exists else None
        items.append({"id": q.id, "name": data.get("supplement_name"), "verdict": verdict,
                      "date": data["timestamp"].isoformat() if data.get("timestamp") else None,
                      "for": f"{'Female' if data.get('sex') == 'female' else 'Male'}, {data.get('age')}"})
    return items


def saved_report(uid: str, query_id: str) -> dict | None:
    if not enabled:
        return None
    doc = db.collection("search_response").document(query_id).get()
    if not doc.exists or doc.get("user_id") != uid:
        return None
    return {**doc.get("full_report"), "thumb": db.collection("search_query_data").document(query_id).get().get("input_image")}
