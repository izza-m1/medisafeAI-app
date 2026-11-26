"""TC-1  Profiles and sign up: wrong or personal data is refused before it is saved."""
import datetime

import pytest

from schemas import age_from_dob

VALID = [
    ("adult woman", dict(name="Izza Maryam", age=26, sex="female", periods="yes")),
    ("date of birth instead of age", dict(name="Izza", dob="2001-05-14", sex="female", periods="yes")),
    ("with a medicine", dict(name="Ali", age=40, sex="male", medicines=["levothyroxine"])),
]
INVALID = [
    ("phone number as name", dict(name="0300-1234567", age=26, sex="female"), "Name can only have letters"),
    ("pregnant man", dict(name="Ali", age=30, sex="male", pregnant=True), "only apply to females"),
    ("birthday in the future", dict(name="Ali", dob="2999-01-01", sex="male"), "future"),
    ("medicine not on the list", dict(name="Ali", age=30, sex="male", medicines=["aspirin"]), "from the list"),
]


@pytest.mark.parametrize("case,profile", VALID, ids=[c for c, _ in VALID])
def test_valid_profile_is_saved(client, case, profile):
    assert client.put("/profile", json=profile).status_code == 200


@pytest.mark.parametrize("case,profile,message", INVALID, ids=[c for c, _, _ in INVALID])
def test_invalid_profile_is_refused(client, case, profile, message):
    r = client.put("/profile", json=profile)
    assert r.status_code == 422 and message.lower() in r.json()["detail"].lower()


def test_age_is_worked_out_from_date_of_birth():
    today = datetime.date.today()
    ten_years_ago = today.replace(year=today.year - 10)
    assert age_from_dob(ten_years_ago.isoformat()) == 10
    assert age_from_dob((ten_years_ago + datetime.timedelta(days=1)).isoformat()) == 9    # birthday is tomorrow


@pytest.mark.parametrize("email,message", [
    ("izza@gmail", "doesn't look right"),
    ("izza@gmial.com", "did you mean @gmail.com"),
    ("hello1@012.con", "isn't a real email ending"),
], ids=["no ending", "typo in gmail", "fake ending"])
def test_wrong_email_is_refused_at_sign_up(client, email, message):
    r = client.post("/auth/available", json={"email": email})
    assert r.status_code == 422 and message in r.json()["detail"].lower()


def test_university_email_is_accepted(client):
    assert client.post("/auth/available", json={"email": "49360@students.riphah.edu.pk"}).status_code == 200
