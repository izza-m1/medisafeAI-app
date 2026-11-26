"""Guests (Firebase anonymous sign-in) can get reports, but nothing of theirs is saved."""
import types

import pytest

from services import database


@pytest.fixture
def firebase(monkeypatch):
    """Turns accounts on with a stand-in for Firebase: the token text is the sign-in method."""
    saved = []

    def verify_id_token(token):
        return {"uid": f"user-{token}", "firebase": {"sign_in_provider": token}}

    monkeypatch.setattr(database, "enabled", True)
    monkeypatch.setattr(database, "auth", types.SimpleNamespace(verify_id_token=verify_id_token, InvalidIdTokenError=ValueError),
                        raising=False)
    monkeypatch.setattr(database, "history", lambda uid: [{"id": "q1"}])
    monkeypatch.setattr(database, "save_report", lambda uid, *rest: saved.append(uid) or "q2")
    monkeypatch.setattr(database, "save_profile", lambda uid, data: True)
    return saved


def test_guest_history_is_empty_and_members_see_theirs(client, firebase):
    assert client.get("/history", headers={"Authorization": "Bearer anonymous"}).json() == {"history": []}
    assert client.get("/history", headers={"Authorization": "Bearer password"}).json() == {"history": [{"id": "q1"}]}


def test_guest_cannot_save_a_profile_on_the_server(client, firebase):
    body = {"age": 30, "sex": "male"}
    assert client.put("/profile", json=body, headers={"Authorization": "Bearer anonymous"}).status_code == 403
    assert client.put("/profile", json=body, headers={"Authorization": "Bearer password"}).status_code == 200


def test_no_token_is_still_refused(client, firebase):
    assert client.get("/history").status_code == 401
