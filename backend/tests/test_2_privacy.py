"""TC-2  Privacy: the AI never gets a name, email, phone or ID number, and tests never write to Firebase."""
import json

import pytest

from services import database
from services.privacy import redact


@pytest.mark.parametrize("text,hidden,mask", [
    ("contact me at someone@example.com", "someone@example.com", "[email]"),
    ("CNIC 35202-1234567-1", "35202-1234567-1", "[id number]"),
    ("call 0300-1234567", "0300-1234567", "[number]"),
])
def test_personal_details_are_removed(text, hidden, mask):
    out = redact(text)
    assert hidden not in out and mask in out


def test_ai_prompt_has_no_personal_details(client, search, nih_passages, fake_claude):
    sent = fake_claude([{"summary": None}])
    s = search("Sangobion")
    r = client.post("/safety-report", json={"scan_id": s["scan_id"], "age": 26, "sex": "female", "periods": "yes",
                                            "reasons": ["hair fall, email me someone@example.com or 0300-1234567"],
                                            "conditions": ["thyroid, my number is 0321-7654321"]})
    assert r.status_code == 200
    prompt = json.dumps(sent)
    for private in ("someone@example.com", "0300-1234567", "0321-7654321"):
        assert private not in prompt
    assert "26-year-old female" in prompt


def test_test_mode_never_writes_to_firebase():
    assert database.enabled is False
