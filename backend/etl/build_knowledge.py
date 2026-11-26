"""Builds the knowledge base the AI answers from (the "R" in RAG).

  1. Read every official page listed in data/nutrients.json (fact_sheet) and data/knowledge_sources.json from
     data/knowledge/pages/ (saved from a browser, because the NIH ODS site blocks scripts), or download it.
  2. Keep the text of each section (Introduction, Health Risks from Excessive..., Interactions with Medications...),
     dropping menus, reference lists and disclaimers.
  3. Cut each section into passages of about settings.CHUNK_WORDS words.
  4. Turn every passage into a vector with the embedding model.
  5. Save data/knowledge/chunks.json (the passages and where they came from) and data/knowledge/vectors.npy.

Run from the backend folder:  python -m etl.build_knowledge
Run it again whenever the NIH updates a fact sheet or a topic is added."""
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

import numpy as np
from bs4 import BeautifulSoup

import settings
from datasets import KNOWLEDGE_SOURCES, NUTRIENTS
from services import embeddings
from services.knowledge import heading

REFERENCE_MARK = re.compile(r"\s*\[\s*\d+(?:\s*[-–,]\s*\d+)*\s*\]")
NOT_CONTENT = ["script", "style", "nav", "header", "footer", "aside", "noscript", "button"]   # not "form": ODS pages sit inside one


def topics() -> list:
    """Every topic and its pages: one per nutrient, then the herbs and other ingredients."""
    found = [{"topic": key, "title": n["name"].split(" (")[0], "names": [n["name"]], "pages": [n["fact_sheet"]]}
             for key, n in NUTRIENTS.items()]
    return found + KNOWLEDGE_SOURCES["topics"]


PAGES_DIR = os.path.join(settings.KNOWLEDGE_DIR, "pages")
BLOCKED_PAGE = re.compile(r"<title>\s*(Attention Required|Just a moment)", re.I)


def page_key(url: str) -> str:
    """The same page written different ways (http/https, www, trailing slash, case) gives the same key."""
    parts = urlparse(url.strip())
    return (parts.netloc.lower().removeprefix("www.") + parts.path.rstrip("/").lower())


def read_saved(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    for encoding in ("utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def saved_pages(wanted: list) -> dict:
    """{page key: html} for the pages saved in data/knowledge/pages. A page is recognised by its own address,
    written inside it (canonical link, og:url, or links to itself), so the file can have any name."""
    found = {}
    if not os.path.isdir(PAGES_DIR):
        return found
    keys = {page_key(u): urlparse(u).path.rstrip("/") for u in wanted}
    for name in sorted(os.listdir(PAGES_DIR)):
        if not name.lower().endswith((".html", ".htm")):
            continue
        html = read_saved(os.path.join(PAGES_DIR, name))
        if BLOCKED_PAGE.search(html):
            print(f"  {name}: this is a 'please wait / attention required' page, not the fact sheet. Save it again.")
            continue
        own = re.findall(r'(?:rel="canonical"[^>]*href|property="og:url"[^>]*content)="([^"]+)"', html)
        match = next((k for k in keys if any(page_key(u) == k for u in own)), None)
        if not match:      # no address of its own: the page whose address it mentions most is itself
            counts = {k: html.lower().count(path.lower()) for k, path in keys.items() if path}
            best = max(counts, key=counts.get, default=None)
            match = best if best and counts[best] else None
        if match and match not in found:
            found[match] = html
        elif not match:
            print(f"  {name}: not one of the pages in nutrients.json or knowledge_sources.json, skipped")
    return found


def download(url: str) -> str | None:
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "MediSafe/2.0 (university project)"})
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.read().decode("utf-8", errors="ignore")
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"    attempt {attempt + 1} failed: {e}")
            time.sleep(2 * (attempt + 1))
    return None


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", REFERENCE_MARK.sub("", text)).strip()


def only_links(element) -> bool:
    """Menus and tables of contents are lists of links with no other text."""
    links = "".join(a.get_text(" ") for a in element.find_all("a"))
    return bool(links.strip()) and clean(links) == clean(element.get_text(" "))


def table_text(table) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [clean(c.get_text(" ")) for c in tr.find_all(["th", "td"])]
        if any(cells):
            rows.append(" | ".join(cells))
    caption = table.find("caption")
    return (clean(caption.get_text(" ")) + ": " if caption else "") + "; ".join(rows)


def sections(html: str) -> list:
    """[(section heading, subheading, [paragraphs])] in page order."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(NOT_CONTENT):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    skip = set(KNOWLEDGE_SOURCES["skip_sections"])
    found, section, sub, skipping = [], "Introduction", None, False
    for el in root.find_all(["h2", "h3", "h4", "p", "li", "table"]):
        if el.name in ("h2", "h3", "h4"):
            title = clean(el.get_text(" "))
            if el.name == "h2":
                section, sub, skipping = title, None, title.lower() in skip
            elif not skipping:
                sub = title if title.lower() not in skip else sub
            continue
        if skipping or el.find_parent("table") or (el.name == "p" and el.find_parent("li")):
            continue
        text = table_text(el) if el.name == "table" else clean(el.get_text(" "))
        if len(text.split()) < 4 or only_links(el):
            continue
        if not found or found[-1][:2] != (section, sub):
            found.append((section, sub, []))
        found[-1][2].append(text)
    return found


def split_words(text: str) -> list:
    words, size, step = text.split(), settings.CHUNK_WORDS, settings.CHUNK_WORDS - settings.CHUNK_OVERLAP_WORDS
    return [" ".join(words[i:i + size]) for i in range(0, max(len(words) - settings.CHUNK_OVERLAP_WORDS, 1), step)]


def chunk(paragraphs: list) -> list:
    """Whole paragraphs are kept together up to CHUNK_WORDS; only a paragraph longer than that is split."""
    chunks, current = [], []
    for paragraph in paragraphs:
        for piece in split_words(paragraph) if len(paragraph.split()) > settings.CHUNK_WORDS else [paragraph]:
            if current and len(" ".join(current + [piece]).split()) > settings.CHUNK_WORDS:
                chunks.append(" ".join(current))
                current = []
            current.append(piece)
    if current:
        chunks.append(" ".join(current))
    return chunks


def publisher(url: str) -> str:
    host = urlparse(url).netloc.removeprefix("www.")
    return KNOWLEDGE_SOURCES["publishers"].get(host, host)


def build() -> None:
    passages, failed = [], []
    saved = saved_pages([u for t in topics() for u in t["pages"]])
    print(f"{len(saved)} pages found in {PAGES_DIR}")
    for t in topics():
        for url in t["pages"]:
            print(f"{t['title']}: {url}")
            html = saved.get(page_key(url)) or download(url)
            if html and BLOCKED_PAGE.search(html):
                html = None
            if not html:
                failed.append(url)
                continue
            count = 0
            for section, sub, paragraphs in sections(html):
                for text in chunk(paragraphs):
                    passages.append({"id": f"{t['topic']}-{len(passages)}", "topic": t["topic"], "title": t["title"],
                                     "section": section, "subsection": sub, "url": url, "publisher": publisher(url),
                                     "text": text})
                    count += 1
            print(f"    {count} passages" + ("   <- very few, check this page" if count < 5 else ""))
    if not passages:
        raise SystemExit("Nothing was downloaded. Check the internet connection and run again.")

    print(f"\nEmbedding {len(passages)} passages with {settings.EMBEDDING_MODEL} ...")
    vectors = embeddings.encode([heading(p) + "\n" + p["text"] for p in passages])

    os.makedirs(settings.KNOWLEDGE_DIR, exist_ok=True)
    with open(os.path.join(settings.KNOWLEDGE_DIR, "chunks.json"), "w", encoding="utf-8") as f:
        json.dump({"built": datetime.date.today().isoformat(), "model": settings.EMBEDDING_MODEL,
                   "chunk_words": settings.CHUNK_WORDS, "passages": passages}, f, ensure_ascii=False, indent=1)
    np.save(os.path.join(settings.KNOWLEDGE_DIR, "vectors.npy"), vectors)
    print(f"Saved {len(passages)} passages from {len({p['url'] for p in passages})} pages to {settings.KNOWLEDGE_DIR}")
    if failed:
        print("Missing (save these from a browser into data/knowledge/pages and run again):\n  " + "\n  ".join(failed))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # Windows consoles are not UTF-8 by default
    build()
