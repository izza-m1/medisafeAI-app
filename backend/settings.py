"""Paths, secrets and tuning values. Secrets come from backend/.env and are never written in code."""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FIREBASE_KEY = os.path.join(BASE_DIR, "firebase-key.json")

load_dotenv(os.path.join(BASE_DIR, ".env"), encoding="utf-8-sig")   # utf-8-sig: Notepad may add a BOM

TESTING = os.environ.get("MEDISAFE_TESTING") == "1"   # tests switch off Firebase and every AI call

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DATA_GOV_API_KEY = os.environ.get("DATA_GOV_API_KEY") or os.environ.get("USDA_API_KEY", "")

CLAUDE_MODELS = [m for m in (os.environ.get("CLAUDE_MODEL"), "claude-haiku-5-5", "claude-haiku-4-5") if m]
GEMINI_MODELS = [m for m in (os.environ.get("GEMINI_MODEL"), "gemini-2.5-flash", "gemini-flash-latest") if m]
GROQ_MODEL = os.environ.get("GROQ_MODEL")

# Photo check: share of the "supplement pack" sentences CLIP must give a photo before it is read.
CLIP_MODEL = "openai/clip-vit-base-patch32"
CLIP_MIN_SCORE = 0.5

# Scans
MAX_PHOTOS = 4
PHOTO_SIZE = 1024            # longest side in pixels; enough for label text and much faster to read
THUMBNAIL_SIZE = 320         # the small copy saved with each report

# Name matching: names up to this length must match exactly (short names are too easy to confuse).
EXACT_MATCH_MAX_LEN = 5
FUZZY_MIN_RATIO = {7: 0.83, 99: 0.8}   # longest name length -> lowest similarity accepted

# AI
AI_TIMEOUT = 25
LABEL_READ_TIMEOUT = 12      # the scan screen waits for this one, so it is kept short
WEB_LOOKUP_TIMEOUT = 45
AI_PAUSE_AFTER_FAILURE = 300  # seconds without AI calls after one fails, so a broken key doesn't slow every scan

# Knowledge base (RAG). Built once by etl/build_knowledge.py from the NIH fact sheets.
KNOWLEDGE_DIR = os.path.join(DATA_DIR, "knowledge")
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_QUERY_PROMPT = "Represent this sentence for searching relevant passages: "   # what bge expects before a query
CHUNK_WORDS = 180             # a passage is about one paragraph or two: small enough to cite, big enough to make sense
CHUNK_OVERLAP_WORDS = 40      # a long paragraph split in two keeps some words in both halves
SEARCH_CANDIDATES = 30        # taken from each of vector search and keyword search before they are merged
SEARCH_TOP_K = 6
SEARCH_MAX_PER_SECTION = 2   # so one long section can't fill every result and hide the others
RRF_K = 60                    # reciprocal rank fusion constant (60 is the value from the original paper)
SEARCH_MIN_SIMILARITY = 0.45  # passages less similar than this to the question are not used; checked by evals/
REASON_MATCH_MIN = 0.72       # a typed reason this close to one of the product's real uses counts as that use
REASON_MATCH_MARGIN = 0.05    # ...and it must beat the next closest use by this much (measured: right 0.75-0.92, wrong up to 0.71)

# AI pharmacist agent
AGENT_MAX_STEPS = 6           # tool calls before it has to answer
AGENT_TIMEOUT = 60
AGENT_MAX_TOKENS = 2500
MAX_PASSAGES_IN_PROMPT = 14

DSLD_API ="https://api.ods.od.nih.gov/dsld/v9"
DSLD_LABEL_URL = "https://dsld.od.nih.gov/label/{}"

HISTORY_LIMIT = 30
