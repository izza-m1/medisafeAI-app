"""Searches the knowledge base built by etl/build_knowledge.py (NIH ODS and NCCIH fact sheets).

Hybrid search, the usual way RAG systems search:
  - vector search finds passages with the same MEANING as the question ("can it hurt my baby" -> pregnancy safety)
  - keyword search (BM25) finds passages with the same rare WORDS (a medicine name like "levothyroxine")
The two rankings are merged with reciprocal rank fusion: a passage ranked high by either one comes out on top."""
import json
import os
import re
import threading

import numpy as np

import settings
from datasets import NUTRIENTS, TOPIC_OF
from services import embeddings

WORD = re.compile(r"[a-z0-9]+")
SUFFIXES = ("ations", "ation", "ions", "ion", "ing", "ed", "es", "s")    # "interactions" and "interact" match
_index = None
_lock = threading.Lock()


def heading(p: dict) -> str:
    """Title and section, put in front of each passage when it is embedded and when it is shown to the AI."""
    return " - ".join(x for x in (p["title"], p["section"], p.get("subsection")) if x)


def stem(word: str) -> str:
    for suffix in SUFFIXES:
        if len(word) - len(suffix) >= 4 and word.endswith(suffix):
            return word[:-len(suffix)]
    return word


def words(text: str) -> list:
    return [stem(w) for w in WORD.findall(text.lower())]


class Index:
    def __init__(self, passages: list, vectors: np.ndarray):
        from rank_bm25 import BM25Okapi
        self.passages = passages
        self.vectors = vectors
        self.bm25 = BM25Okapi([words(heading(p) + " " + p["text"]) for p in passages])
        self.by_topic = {}
        for i, p in enumerate(passages):
            self.by_topic.setdefault(p["topic"], []).append(i)

    def search(self, query: str, topics: list | None = None, k: int = settings.SEARCH_TOP_K) -> list:
        rows = sorted({i for t in topics or [] for i in self.by_topic.get(t, [])}) or list(range(len(self.passages)))
        rows = np.array(rows)
        similarity = self.vectors[rows] @ embeddings.encode([query], query=True)[0]
        keyword = np.array(self.bm25.get_scores(words(query)))[rows]

        by_meaning = rows[np.argsort(-similarity)][:settings.SEARCH_CANDIDATES]
        by_words = rows[np.argsort(-keyword)][:settings.SEARCH_CANDIDATES]
        by_words = [i for i, score in zip(by_words, sorted(keyword, reverse=True)) if score > 0]
        fused = {}
        for ranking in (by_meaning, by_words):
            for rank, i in enumerate(ranking):
                fused[int(i)] = fused.get(int(i), 0) + 1 / (settings.RRF_K + rank + 1)

        sim_of = dict(zip(rows.tolist(), similarity.tolist()))
        strong_words = set(int(i) for i in by_words[:3])
        keep, per_section = [], {}
        for i in sorted(fused, key=fused.get, reverse=True):
            if sim_of[i] < settings.SEARCH_MIN_SIMILARITY and i not in strong_words:
                continue
            section = (self.passages[i]["topic"], self.passages[i]["section"], self.passages[i].get("subsection"))
            if per_section.get(section, 0) < settings.SEARCH_MAX_PER_SECTION:
                per_section[section] = per_section.get(section, 0) + 1
                keep.append(i)
        return [{**self.passages[i], "similarity": round(sim_of[i], 3), "score": round(fused[i], 4)} for i in keep[:k]]


def index() -> Index | None:
    """Loaded on first use. None when the knowledge base has not been built yet."""
    global _index
    with _lock:
        if _index is None:
            chunks = os.path.join(settings.KNOWLEDGE_DIR, "chunks.json")
            vectors = os.path.join(settings.KNOWLEDGE_DIR, "vectors.npy")
            if not (os.path.exists(chunks) and os.path.exists(vectors)):
                return None
            with open(chunks, encoding="utf-8") as f:
                passages = json.load(f)["passages"]
            _index = Index(passages, np.load(vectors))
    return _index


def available() -> bool:
    return index() is not None


def search(query: str, topics: list | None = None, k: int = settings.SEARCH_TOP_K) -> list:
    found = index()
    return found.search(query, topics, k) if found and query.strip() else []


def topics_for(nutrients: list, herbs: list) -> list:
    """Knowledge base topics for what is inside a product: nutrient keys are topics already; herbs are mapped."""
    return list(dict.fromkeys([*(n for n in nutrients if n in NUTRIENTS), *(TOPIC_OF[h] for h in herbs if h in TOPIC_OF)]))


def topic_titles() -> dict:
    found = index()
    return {p["topic"]: p["title"] for p in found.passages} if found else {}
