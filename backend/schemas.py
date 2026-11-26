"""Request bodies. Each one is checked before anything is saved or sent to an AI model."""
import datetime
import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from datasets import EMAIL_RULES, MEDICATIONS
from services.privacy import clean_free_text

NAME = re.compile(r"^[A-Za-z؀-ۿ][A-Za-z؀-ۿ .'-]{1,39}$")    # English or Urdu letters, 2-40
EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
MIN_PERIODS_AGE, PREGNANCY_AGES = 8, (12, 60)
MAX_REASONS, MAX_REASON_LENGTH = 5, 80
MAX_FREE_ITEMS, MAX_FREE_ITEM_LENGTH = 8, 60       # typed health conditions and other medicines
MAX_QUESTION_LENGTH = 300
Periods = Optional[Literal["yes", "irregular", "no"]]      # irregular = oligomenorrhea, still counts as periods
BAD_EMAIL = "That email doesn't look right. Use a full address like name@gmail.com."


def age_from_dob(dob: str) -> int:
    born, today = datetime.date.fromisoformat(dob), datetime.date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def check_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL.match(email):
        raise ValueError(BAD_EMAIL)
    domain = email.split("@")[1]
    if domain in EMAIL_RULES["provider_typos"]:
        raise ValueError(f"Did you mean @{EMAIL_RULES['provider_typos'][domain]}?")
    *names, ending = domain.split(".")
    if len(ending) > 2 and ending not in EMAIL_RULES["endings"]:
        if ending in EMAIL_RULES["dotcom_typos"]:
            raise ValueError(f"\".{ending}\" isn't a real email ending. Did you mean .com?")
        raise ValueError(BAD_EMAIL)
    if not re.search("[a-z]", "".join(names)):
        raise ValueError(BAD_EMAIL)
    return email


def check_health_fields(m):
    if m.sex == "male" and (m.pregnant or m.breastfeeding or m.periods):
        raise ValueError("Periods, pregnancy and breastfeeding only apply to females.")
    if m.sex == "female" and m.periods in ("yes", "irregular") and m.age < MIN_PERIODS_AGE:
        raise ValueError(f"Periods can't be set for girls under {MIN_PERIODS_AGE}. Please check the age.")
    if m.sex == "female" and (m.pregnant or m.breastfeeding) and not PREGNANCY_AGES[0] <= m.age <= PREGNANCY_AGES[1]:
        raise ValueError(f"Pregnancy and breastfeeding can only be set for ages {PREGNANCY_AGES[0]} to {PREGNANCY_AGES[1]}.")
    return m


def clean_items(items: list, what: str) -> list:
    cleaned = list(dict.fromkeys(i for i in (clean_free_text(x) for x in items) if i))
    if len(cleaned) > MAX_FREE_ITEMS:
        raise ValueError(f"Add at most {MAX_FREE_ITEMS} {what}.")
    if any(len(i) > MAX_FREE_ITEM_LENGTH for i in cleaned):
        raise ValueError(f"Keep each of your {what} under {MAX_FREE_ITEM_LENGTH} characters.")
    return cleaned


def check_medicines(keys: list) -> list:
    unknown = [k for k in keys if k not in MEDICATIONS]
    if unknown:
        raise ValueError("Choose your medicines from the list.")
    return list(dict.fromkeys(keys))


class Person(BaseModel):
    age: int = Field(..., ge=1, le=120)
    sex: Literal["male", "female"]
    periods: Periods = None
    pregnant: bool = False
    breastfeeding: bool = False
    medicines: List[str] = []                  # keys from medications.json
    other_medicines: List[str] = []            # typed by the user, checked by the AI pharmacist
    conditions: List[str] = []                 # health conditions in the user's own words
    other_supplements: List[str] = []          # other supplements the user takes, by name ("Caltrate", "zinc")

    @field_validator("medicines")
    @classmethod
    def known_medicines(cls, v: list) -> list:
        return check_medicines(v)

    @field_validator("other_medicines")
    @classmethod
    def clean_other_medicines(cls, v: list) -> list:
        return clean_items(v, "other medicines")

    @field_validator("conditions")
    @classmethod
    def clean_conditions(cls, v: list) -> list:
        return clean_items(v, "health conditions")

    @field_validator("other_supplements")
    @classmethod
    def clean_other_supplements(cls, v: list) -> list:
        return clean_items(v, "other supplements")

    @model_validator(mode="after")
    def health_fields_agree(self):
        return check_health_fields(self)


class Profile(Person):
    name: str = Field("", max_length=40)
    dob: Optional[str] = None          # YYYY-MM-DD; age is always worked out from it
    age: Optional[int] = Field(None, ge=1, le=120)

    @field_validator("name")
    @classmethod
    def is_a_name(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v or "").strip()
        if v and not NAME.match(v):
            raise ValueError("Name can only have letters and spaces (2-40). Don't put a phone number or email in it.")
        return v

    @field_validator("dob")
    @classmethod
    def real_date(cls, v):
        if not v:
            return None
        try:
            born = datetime.date.fromisoformat(v)
        except ValueError:
            raise ValueError("Date of birth must be a real date (DD/MM/YYYY).")
        if born > datetime.date.today():
            raise ValueError("Date of birth can't be in the future.")
        if not 1 <= age_from_dob(v) <= 120:
            raise ValueError("Age must be between 1 and 120.")
        return v

    @model_validator(mode="before")
    @classmethod
    def age_from_birthday(cls, data):
        if isinstance(data, dict) and data.get("dob"):
            try:
                age = age_from_dob(data["dob"])
                data = {**data, "age": age if age >= 1 else None}
            except (ValueError, TypeError):
                pass                       # real_date reports the bad date
        if isinstance(data, dict) and data.get("age") is None and not data.get("dob"):
            raise ValueError("Please enter your date of birth.")
        return data


class ReportRequest(Person):
    scan_id: str
    reasons: List[str] = []
    supplement_name: Optional[str] = Field(None, max_length=80)    # the user's correction of the scanned name

    @field_validator("reasons")
    @classmethod
    def clean_reasons(cls, reasons: list) -> list:
        if len(reasons) > MAX_REASONS:
            raise ValueError(f"Choose at most {MAX_REASONS} reasons.")
        cleaned = [r for r in (clean_free_text(x) for x in reasons) if r]
        if any(len(r) > MAX_REASON_LENGTH for r in cleaned):
            raise ValueError(f"Each reason must be {MAX_REASON_LENGTH} characters or less.")
        return cleaned


class Question(Person):
    scan_id: str
    question: str = Field(..., min_length=3, max_length=MAX_QUESTION_LENGTH)
    supplement_name: Optional[str] = Field(None, max_length=80)

    @field_validator("question")
    @classmethod
    def clean_question(cls, v: str) -> str:
        v = clean_free_text(v)
        if len(v) < 3:
            raise ValueError("Please type your question.")
        return v


class ReasonsRequest(BaseModel):
    scan_id: str
    name: Optional[str] = None
    age: Optional[int] = Field(None, ge=1, le=120)
    sex: Optional[Literal["male", "female"]] = None
    periods: Periods = None


class ScanId(BaseModel):
    scan_id: str


class ProductName(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


class Email(BaseModel):
    email: str = Field(..., min_length=3, max_length=120)


class NewEmail(Email):
    """Sign up only: an existing account's email is never refused, even if it fails these checks."""

    @field_validator("email")
    @classmethod
    def real_email(cls, v: str) -> str:
        return check_email(v)
