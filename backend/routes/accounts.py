"""Sign up checks, the user's profile and the list of medicines they can choose from."""
from fastapi import APIRouter, Depends

from schemas import Email, NewEmail, Profile, age_from_dob
from services import database, medications
from services.database import account_holder, current_user

router = APIRouter()


@router.post("/auth/available")
def email_available(data: NewEmail):
    """Sign up: is the email real-looking (checked by NewEmail) and not used by another account?"""
    return {"email_taken": database.email_in_use(data.email)}


@router.post("/account-exists")
def account_exists(data: Email):
    """Forgot password: say so when no account uses this email, instead of a silent 'we sent it'."""
    return {"exists": database.email_in_use(data.email.strip())}


@router.get("/profile")
def get_profile(user: str = Depends(current_user)):
    profile = database.load_profile(user)
    if not profile:
        return {"profile": None}
    profile.pop("updated", None)
    if profile.get("dob"):
        profile["age"] = age_from_dob(profile["dob"])          # always today's age
    return {"profile": {**profile, "email": database.account_email(user)}}


@router.put("/profile")
def save_profile(data: Profile, user: str = Depends(account_holder)):
    return {"saved": database.save_profile(user, data.model_dump())}


@router.get("/medicines")
def medicine_choices():
    return {"medicines": medications.choices()}
