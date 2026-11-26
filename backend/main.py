"""MediSafe AI backend. Run from the backend folder:  uvicorn main:app --host 0.0.0.0 --port 8000"""
import threading

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import settings
from routes import accounts, reports, scans
from services import ai, database, embeddings, knowledge, vision

app = FastAPI(title="MediSafe AI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
for router in (accounts.router, scans.router, reports.router):
    app.include_router(router)


@app.exception_handler(RequestValidationError)
def readable_error(request, exc: RequestValidationError):
    """One plain sentence the app can show, instead of FastAPI's list of field errors."""
    first = exc.errors()[0] if exc.errors() else {}
    message = str(first.get("msg", "Please check the details you entered.")).removeprefix("Value error, ")
    if first.get("type") in ("less_than_equal", "greater_than_equal") and first.get("loc", [""])[-1] == "age":
        message = "Age must be between 1 and 120."
    return JSONResponse(status_code=422, content={"detail": message})


@app.get("/")
def status():
    index = knowledge.index()
    return {"status": "MediSafe AI running", "ai": ai.provider(), "last_ai_problem": ai.status["problem"],
            "knowledge_base": f"{len(index.passages)} NIH passages" if index else "not built (run: python -m etl.build_knowledge)",
            "database": "Firebase" if database.enabled else "off (backend/firebase-key.json missing)"}


def warm_up():
    """Loads the models in the background so the first scan and the first report don't wait for them."""
    vision.warm_up()
    if knowledge.index():
        embeddings.encode(["warm up"], query=True)


if not settings.TESTING:
    threading.Thread(target=warm_up, daemon=True).start()
