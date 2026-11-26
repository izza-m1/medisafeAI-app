"""Sends a prompt (text and photos) to an AI model and returns its JSON answer.
Claude is used when ANTHROPIC_API_KEY is set; Groq or Gemini only as free backups. With no key, or after a
failure, the app keeps working: every safety decision is made by the rules, not by the AI."""
import base64
import io
import json
import time
import urllib.error
import urllib.request

from PIL import Image

import settings

status = {"ok": None, "problem": None}       # shown on the home endpoint and in reports made without AI
_paused_until = 0.0


def available() -> bool:
    return not settings.TESTING and time.time() >= _paused_until


def provider() -> str:
    if settings.ANTHROPIC_API_KEY:
        return "Claude"
    if settings.GROQ_API_KEY:
        return "Groq"
    if settings.GEMINI_API_KEY:
        return "Gemini"
    return "off"


def image_block(image: Image.Image) -> dict:
    img = image.copy()
    img.thumbnail((settings.PHOTO_SIZE, settings.PHOTO_SIZE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(buf.getvalue()).decode()}}


def ask(content: list, max_tokens: int, timeout: int = settings.AI_TIMEOUT) -> dict | None:
    """content = Claude-style blocks: {"type": "text", ...} and image_block(...). None if no answer."""
    global _paused_until
    if not available():
        return None
    send = {"Claude": _claude, "Groq": _groq, "Gemini": _gemini}.get(provider())
    if not send:
        return _failed("No AI key in backend/.env (ANTHROPIC_API_KEY, or GROQ_API_KEY / GEMINI_API_KEY as backups)")
    try:
        result = send(content, max_tokens, timeout)
    except urllib.error.HTTPError as e:
        result = _failed(f"{provider()} API error {e.code}: {e.read().decode(errors='ignore')[:200]}")
    except (urllib.error.URLError, TimeoutError) as e:
        result = _failed(f"Could not reach the {provider()} API ({e.__class__.__name__})")
    if result is None:
        _paused_until = time.time() + settings.AI_PAUSE_AFTER_FAILURE
    else:
        status.update(ok=True, problem=None)
    return result


def claude_raw(body: dict, timeout: int = settings.AI_TIMEOUT) -> dict | None:
    """One raw Claude Messages API call (used by the agent, which needs tool calls, not just JSON).
    None when Claude is not the provider, is paused after a failure, or fails now."""
    global _paused_until
    if not available() or provider() != "Claude":
        return None
    try:
        data = claude_messages(body, timeout)
        result = data or _failed("None of the Claude models in settings.py are available for this key")
    except urllib.error.HTTPError as e:
        result = _failed(f"Claude API error {e.code}: {e.read().decode(errors='ignore')[:200]}")
    except (urllib.error.URLError, TimeoutError) as e:
        result = _failed(f"Could not reach the Claude API ({e.__class__.__name__})")
    if result is None:
        _paused_until = time.time() + settings.AI_PAUSE_AFTER_FAILURE
    else:
        status.update(ok=True, problem=None)
    return result


def _failed(problem: str):
    status.update(ok=False, problem=problem)
    print(f"AI unavailable: {problem}")
    return None


def _post(url: str, body: dict, headers: dict, timeout: int) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def read_json(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    try:
        return json.loads(text[start:end + 1]) if start != -1 else None
    except json.JSONDecodeError:
        return None


def claude_messages(body: dict, timeout: int) -> dict | None:
    """Tries each model in settings.CLAUDE_MODELS until one exists for this key. Returns the raw API response."""
    for model in settings.CLAUDE_MODELS:
        try:
            return _post("https://api.anthropic.com/v1/messages", {**body, "model": model},
                         {"anthropic-version": "2023-06-01", "x-api-key": settings.ANTHROPIC_API_KEY}, timeout)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
    return None


def response_text(data: dict) -> str:
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def _claude(content: list, max_tokens: int, timeout: int) -> dict | None:
    data = claude_messages({"max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]}, timeout)
    if data is None:
        return _failed("None of the Claude models in settings.py are available for this key")
    return read_json(response_text(data)) or _failed("Claude's answer could not be read")


def _gemini(content: list, max_tokens: int, timeout: int) -> dict | None:
    parts = [{"inline_data": {"mime_type": b["source"]["media_type"], "data": b["source"]["data"]}} if b["type"] == "image"
             else {"text": b["text"]} for b in content]
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"maxOutputTokens": max(max_tokens, 2048), "temperature": 0.2, "responseMimeType": "application/json"}}
    for model in settings.GEMINI_MODELS:
        try:
            data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", body,
                         {"x-goog-api-key": settings.GEMINI_API_KEY}, timeout)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        text = "".join(p.get("text", "") for c in data.get("candidates", [])[:1] for p in c.get("content", {}).get("parts", []))
        return read_json(text) or _failed("Gemini's answer could not be read")
    return _failed("None of the Gemini models in settings.py are available for this key")


def _groq(content: list, max_tokens: int, timeout: int) -> dict | None:
    """Groq's text models can't see photos, so only the text blocks are sent."""
    model = settings.GROQ_MODEL or "llama-3.3-70b-versatile"
    prompt = "\n\n".join(b["text"] for b in content if b["type"] == "text")
    body = {"model": model, "max_tokens": max(max_tokens, 800), "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": "Reply with one JSON object only."}, {"role": "user", "content": prompt}]}
    data = _post("https://api.groq.com/openai/v1/chat/completions", body, {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}, timeout)
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    return read_json(text) or _failed("Groq's answer could not be read")
