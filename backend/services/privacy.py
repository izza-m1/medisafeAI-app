"""Removes personal details from free text before it is saved or sent to an AI model.
The AI only ever gets age, sex, periods, pregnancy, breastfeeding, the reasons and the label text:
never the name, email, date of birth, photo or account id."""
import re

PERSONAL_DETAILS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"(?:https?://|www\.)\S+|\S+\.(?:com|pk|org|net)/\S*", re.I), "[link]"),
    (re.compile(r"\b\d{5}-\d{7}-\d\b"), "[id number]"),          # Pakistani CNIC
    (re.compile(r"\+?\d[\d\s-]{8,}\d"), "[number]"),             # phone numbers and other long numbers
]


def redact(text: str) -> str:
    for pattern, mask in PERSONAL_DETAILS:
        text = pattern.sub(mask, text or "")
    return text


def clean_free_text(text: str) -> str:
    """User-typed text: control characters and brackets removed, personal details masked."""
    return redact(re.sub(r"[\x00-\x1f<>{}]", "", str(text))).strip()
