"""Measures how well the AI parts work, with the real embedding model and the real AI (not the test stand-ins).

  retrieval   for each question, is a right NIH passage in the top results? (hit@1, hit@3, hit@5, MRR)
  reports     does the AI pharmacist catch the person's typed conditions and medicines, without false alarms,
              and how many of its claims survive the citation checks? (needs an AI key in .env)
  questions   does Ask MediSafe answer what the NIH covers, and say so when it doesn't? (needs an AI key)

Run from the backend folder, after python -m etl.build_knowledge:   python -m evals.run_evals
The results are printed and saved to evals/results.json."""
import datetime
import json
import os
import sys
import time

from PIL import Image

import settings
from schemas import Person
from routes.reports import person_of
from services import ai, knowledge, pharmacist, products, report, scanner, vision

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = json.load(open(os.path.join(HERE, "cases.json"), encoding="utf-8"))
ORDER = ["Safe", "Use with caution", "Not safe"]
TOP_K = 5


def contains_any(text: str, words: list) -> bool:
    text = text.lower()
    return any(w.lower() in text for w in words)


def retrieval() -> dict:
    ranks = []
    for case in CASES["retrieval"]:
        found = knowledge.search(case["question"], [case["topic"]] if case["topic"] else None, TOP_K)
        rank = next((i + 1 for i, p in enumerate(found)
                     if contains_any(knowledge.heading(p) + " " + p["text"], case["expect"])), None)
        ranks.append(rank)
        print(f"  {'ok  ' if rank else 'MISS'} {case['question']}" + (f"  (rank {rank})" if rank else
              f"  top: {knowledge.heading(found[0]) if found else 'nothing found'}"))
    n = len(ranks)
    return {"cases": n, **{f"hit@{k}": round(sum(1 for r in ranks if r and r <= k) / n, 3) for k in (1, 3, 5)},
            "mrr": round(sum(1 / r for r in ranks if r) / n, 3)}


def pack(lines: list) -> dict:
    """A scan made from pack text, so the eval tests the AI layers and not the camera."""
    segments = [{"text": text, "conf": 0.9, "h": height} for text, height in lines]
    original = vision.read_text, scanner._read_with_ai
    vision.read_text = lambda image, turn=False: segments
    scanner._read_with_ai = lambda images, text: {}          # a blank photo: nothing for the AI to read
    try:
        return scanner.scan_photos([Image.new("RGB", (600, 800), "white")])
    finally:
        vision.read_text, scanner._read_with_ai = original


def reports() -> dict:
    results, kept, dropped = [], 0, 0
    for case in CASES["reports"]:
        scan = pack(case["label"])
        data = Person(**case["person"])
        person = person_of(data)
        info = products.product_info(scan["product"]["product_key"])
        start = time.time()
        built, mode = report.build(scan, scan["product"], scan["company"], scan["label"], person, [], data.medicines)
        seconds = round(time.time() - start, 1)
        verdict = built["is_safe_to_take"]["verdict"]
        concerns = " ".join(c["text"] for c in built["is_safe_to_take"]["checks"] if c["key"] == report.AI_CHECK_KEY)
        claims = built.get("ai_claims") or {"kept": 0, "dropped": 0}
        kept, dropped = kept + claims["kept"], dropped + claims["dropped"]
        problems = []
        if case.get("expect_verdict_at_least") and ORDER.index(verdict) < ORDER.index(case["expect_verdict_at_least"]):
            problems.append(f"verdict {verdict}, expected at least {case['expect_verdict_at_least']}")
        if case.get("expect_verdict_at_most") and ORDER.index(verdict) > ORDER.index(case["expect_verdict_at_most"]):
            problems.append(f"verdict {verdict}, expected at most {case['expect_verdict_at_most']}")
        if case["expect_concern_words"] and not contains_any(concerns, case["expect_concern_words"]):
            problems.append(f"no AI concern about {case['expect_concern_words']}")
        if not mode:
            problems.append("the AI did not take part: " + str(ai.status["problem"]))
        results.append({"case": case["name"], "product": info["name"], "verdict": verdict, "mode": mode, "seconds": seconds,
                        "tool_calls": len(built.get("ai_research", [])), "claims": claims, "passed": not problems,
                        "problems": problems})
        print(f"  {'ok  ' if not problems else 'FAIL'} {case['name']}: {verdict}, {seconds}s, "
              f"{len(built.get('ai_research', []))} searches, claims kept {claims['kept']} dropped {claims['dropped']}"
              + ("".join(f"\n         {p}" for p in problems)))
    return {"cases": len(results), "passed": sum(r["passed"] for r in results),
            "claims_kept_share": round(kept / (kept + dropped), 3) if kept + dropped else None, "details": results}


def questions() -> dict:
    results = []
    for case in CASES["questions"]:
        scan = pack(case["label"])
        info = products.product_info(scan["product"]["product_key"])
        nutrients = list(dict.fromkeys([*info.get("nutrients", []), *scan["label"].get("amounts", {})]))
        person = person_of(Person(age=30, sex="female", periods="yes"))
        out = pharmacist.answer_question(case["question"], scan["product"], scan["label"], person, nutrients, products.herbs_of(info))
        problems = []
        if out["covered"] != case["expect_covered"]:
            problems.append(f"covered={out['covered']}, expected {case['expect_covered']}")
        if case["expect_words"] and not contains_any(out["answer"], case["expect_words"]):
            problems.append(f"answer does not mention {case['expect_words']}")
        results.append({"question": case["question"], "answer": out["answer"], "sources": len(out["sources"]),
                        "passed": not problems, "problems": problems})
        print(f"  {'ok  ' if not problems else 'FAIL'} {case['question']}\n         {out['answer'][:160]}"
              + ("".join(f"\n         {p}" for p in problems)))
    return {"cases": len(results), "passed": sum(r["passed"] for r in results), "details": results}


def main():
    if not knowledge.available():
        sys.exit("Build the knowledge base first:  python -m etl.build_knowledge")
    out = {"date": datetime.datetime.now().isoformat(timespec="minutes"), "embedding_model": settings.EMBEDDING_MODEL,
           "ai": ai.provider(), "passages": len(knowledge.index().passages)}
    print(f"Retrieval ({len(CASES['retrieval'])} questions, top {TOP_K}):")
    out["retrieval"] = retrieval()
    print(json.dumps(out["retrieval"]))
    if ai.provider() == "off":
        print("\nNo AI key in .env: skipping the report and question evals.")
    else:
        print(f"\nReports ({ai.provider()}):")
        out["reports"] = reports()
        print(f"passed {out['reports']['passed']}/{out['reports']['cases']}, claims kept: {out['reports']['claims_kept_share']}")
        print("\nQuestions:")
        out["questions"] = questions()
        print(f"passed {out['questions']['passed']}/{out['questions']['cases']}")
    with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"\nSaved to {os.path.join(HERE, 'results.json')}")


if __name__ == "__main__":
    main()
