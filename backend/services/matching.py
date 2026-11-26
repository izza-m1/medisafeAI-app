"""Fuzzy name matching for text read by OCR, which often swaps letters (NEUROB1ON, FEFO1-VIT)."""
import re
from difflib import SequenceMatcher

from settings import EXACT_MATCH_MAX_LEN, FUZZY_MIN_RATIO

DIGITS_AS_LETTERS = str.maketrans("0158", "oisb")   # inside a word, OCR reads o, i, s, b as 0, 1, 5, 8
LOOKALIKES = str.maketrans("l1i0", "iiio")           # FEFO1 / FEFOI / FEFOL are the same word


def norm(text: str) -> str:
    text = (text or "").lower().replace("'", "").replace("’", "")
    return " ".join(re.sub(r"[^a-z0-9&]+", " ", text).split())


def word_grams(segments: list) -> list:
    """OCR segments -> every 1, 2 and 3 word sequence, each weighted so bigger, clearer text counts more
    (the product name is usually the largest text on a pack)."""
    tallest = max((s["h"] for s in segments), default=1) or 1
    words = []
    for s in segments:
        weight = (0.6 + 0.4 * s["h"] / tallest) * (0.5 + 0.5 * s["conf"])
        for token in norm(s["text"]).split():
            if re.search("[a-z]", token):
                token = token.translate(DIGITS_AS_LETTERS)
            words.append((token, weight))
    return [(tuple(t for t, _ in words[i:i + n]), min(w for _, w in words[i:i + n]))
            for n in (1, 2, 3) for i in range(len(words) - n + 1)]


def grams_of(text: str) -> list:
    return word_grams([{"text": text, "h": 1, "conf": 1}])


def _min_ratio(length: int) -> float:
    return next(ratio for max_len, ratio in sorted(FUZZY_MIN_RATIO.items()) if length <= max_len)


def similarity(word: str, name: str) -> float:
    if len(name) <= EXACT_MATCH_MAX_LEN:
        return 1.0 if word.translate(LOOKALIKES) == name.translate(LOOKALIKES) else 0.0
    if abs(len(word) - len(name)) > 2:
        return 0.0
    ratio = SequenceMatcher(None, word, name).ratio()
    return ratio if ratio >= _min_ratio(len(name)) else 0.0


def gram_score(gram: tuple, name: str) -> float:
    """A one-word name also matches words OCR split apart ("NEURO BION").
    A longer name is matched word by word, so "SURBEX" alone never matches "surbex z"."""
    name_words = norm(name).split()
    if len(name_words) == 1:
        return similarity("".join(gram), name_words[0])
    if len(gram) != len(name_words):
        joined = "".join(gram).translate(LOOKALIKES)
        return 1.0 if joined == "".join(name_words).translate(LOOKALIKES) else 0.0
    return min(similarity(g, n) for g, n in zip(gram, name_words))


def best_match(grams: list, names) -> tuple:
    """(best name, score) or (None, 0). On a tie the longer, more specific name wins ("surbex z" over "surbex")."""
    scores = {}
    for name in names:
        for gram, weight in grams:
            score = gram_score(gram, name)
            if score:
                scores[name] = max(scores.get(name, 0), score * weight)
    if not scores:
        return None, 0.0
    best = max(scores, key=lambda n: (round(scores[n], 2), len(n)))
    return best, round(scores[best], 3)
