"""Shared setup for the tests. Run from the backend folder:  python -m pytest tests -v

Test mode (MEDISAFE_TESTING=1) switches Firebase and every AI call off, so tests never touch the real database
and never send data anywhere. The camera models are replaced by fixed label text, and the embedding model by a
word-counting stand-in, so every run gives the same result without downloading a model. Tests of the AI
pharmacist replace Claude with a scripted reply (fake_claude). Everything else is the real code and the real data
in backend/data. How well the real models do is measured separately, by evals/run_evals.py."""
import hashlib
import io
import json
import os
import re
import sys

os.environ["MEDISAFE_TESTING"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main
from services import ai, embeddings, knowledge, vision

HERE = os.path.dirname(os.path.abspath(__file__))


def word_vectors(texts, query=False, size=512):
    """Stand-in for the embedding model: texts sharing words get similar vectors. Same input, same output."""
    rows = np.zeros((len(texts), size), dtype=np.float32)
    for row, text in zip(rows, texts):
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            row[int(hashlib.md5(word.encode()).hexdigest(), 16) % size] += 1
        norm = np.linalg.norm(row)
        if norm:
            row /= norm
    return rows


@pytest.fixture(autouse=True)
def no_embedding_model(monkeypatch):
    monkeypatch.setattr(embeddings, "encode", word_vectors)


@pytest.fixture
def nih_passages(monkeypatch):
    """A small knowledge base of real NIH fact sheet sentences (tests/nih_passages.json) instead of the full one."""
    with open(os.path.join(HERE, "nih_passages.json"), encoding="utf-8") as f:
        passages = json.load(f)["passages"]
    vectors = word_vectors([knowledge.heading(p) + "\n" + p["text"] for p in passages])
    index = knowledge.Index(passages, vectors)
    monkeypatch.setattr(knowledge, "_index", index)
    return index


@pytest.fixture
def fake_claude(monkeypatch):
    """fake_claude([reply, reply...]) -> Claude answers with these, in order. A reply is either
    {"tool": name, "input": {...}} (a tool call), a dict (the final JSON answer), or a function that gets the
    request and returns one of those. Returns the list of requests Claude received."""
    def install(replies):
        sent, queue = [], list(replies)

        def claude_raw(body, timeout=None):
            sent.append(json.loads(json.dumps(body)))
            reply = queue.pop(0)
            if callable(reply):
                reply = reply(body)
            if "tool" in reply:
                return {"content": [{"type": "tool_use", "id": f"call{len(sent)}", "name": reply["tool"], "input": reply["input"]}]}
            return {"content": [{"type": "text", "text": json.dumps(reply)}]}

        monkeypatch.setattr(ai, "available", lambda: True)
        monkeypatch.setattr(ai, "provider", lambda: "Claude")
        monkeypatch.setattr(ai, "claude_raw", claude_raw)
        return sent
    return install

PEOPLE = {
    "man_30": dict(age=30, sex="male"),
    "boy_8": dict(age=8, sex="male"),
    "girl_8_periods": dict(age=8, sex="female", periods="yes"),
    "woman_26_periods": dict(age=26, sex="female", periods="yes"),
    "pregnant_28": dict(age=28, sex="female", periods="yes", pregnant=True),
    "woman_60_menopause": dict(age=60, sex="female", periods="no"),
}

COLOUR = {"ok": "green", "caution": "orange", "stop": "red"}
TONE = {"Safe": "ok", "Use with caution": "caution", "Not safe": "stop"}


@pytest.fixture(scope="session")
def client():
    return TestClient(main.app)


@pytest.fixture
def scan(client, monkeypatch):
    """scan([("Centrum", 60), ("MEN", 40)]) -> the /scan-supplement result for a photo whose text reads those lines.
    Each line is (text, letter height in pixels): the biggest text is usually the product name."""
    def run(lines, is_supplement=True):
        segments = [{"text": text, "conf": 0.9, "h": height} for text, height in lines]
        monkeypatch.setattr(vision, "read_text", lambda image, turn=False: segments)
        monkeypatch.setattr(vision, "is_supplement_photo",
                            lambda image: (True, "") if is_supplement else (False, "looks like food on a plate"))
        photo = io.BytesIO()
        Image.new("RGB", (600, 800), "white").save(photo, "JPEG")
        r = client.post("/scan-supplement", files=[("files", ("pack.jpg", photo.getvalue(), "image/jpeg"))])
        assert r.status_code == 200, r.text
        return r.json()
    return run


@pytest.fixture
def search(client):
    def run(name):
        r = client.post("/search-product", json={"name": name})
        return r.json() if r.status_code == 200 else None
    return run


@pytest.fixture
def report(client):
    """report(scan_result, "woman_26_periods", reasons=["Heavy periods"]) -> (http status, response)"""
    def run(scan_result, person, reasons=(), medicines=(), **extra):
        r = client.post("/safety-report", json={"scan_id": scan_result["scan_id"], "reasons": list(reasons),
                                                "medicines": list(medicines), **PEOPLE[person], **extra})
        return r.status_code, r.json()
    return run


def colour(response: dict) -> str:
    """The colour the app shows: the headline's tone when it has one, otherwise the verdict's."""
    result = response["report"]["is_safe_to_take"]
    return COLOUR[result["tone"] or TONE[result["verdict"]]]


def check(response: dict, key: str) -> dict | None:
    return next((c for c in response["report"]["is_safe_to_take"]["checks"] if c["key"] == key), None)
