"""The AI pharmacist: an agent that researches one person's case in the NIH knowledge base and writes the
personal part of the report, or answers a question about a supplement.

How it works (retrieval-augmented generation with tool use):
  1. Evidence first: the app searches the knowledge base for the product's risks, interactions and uses, and for
     the person's own conditions, medicines and reasons. Each passage gets an id (S1, S2...).
  2. Claude reads the case and the passages. It can call two tools while it thinks:
       search_nih(query, topic)  -> more passages from the knowledge base
       get_limits(nutrient)      -> this person's daily need and upper limit from nutrients.json
  3. Claude answers in JSON, listing the passage ids behind every item.
  4. Guardrails, in code: an item with no real passage id is dropped, an item with a number that is not in its
     passages is dropped, and the AI can only add concerns (make the verdict stricter), never remove a rule's check.
Without Claude (Groq or Gemini key only) step 2 runs once without tools, on the passages from step 1."""
import json
import os
import re

import settings
from datasets import NUTRIENTS
from services import ai, food_guidance, knowledge, limits
from services.privacy import redact

PROMPTS_DIR = os.path.join(settings.BASE_DIR, "prompts")
SOURCE_ID = re.compile(r"\[(S\d+)\]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
LEVELS = ("caution", "stop")
NOT_COVERED = "Our NIH sources don't answer this question. Please ask a pharmacist or your doctor."
SEED_PER_QUERY = 2
SEED_QUESTIONS = {      # what is always looked up for each ingredient; {t} is the ingredient
    "always": ["{t} health risks of too much, side effects and toxicity", "{t} interactions with medications",
               "{t} what it is used for and health benefits"],
    "pregnant": ["{t} safety in pregnancy"],
    "breastfeeding": ["{t} safety while breastfeeding"],
    "child": ["{t} use in children"],
}


def prompt(name: str) -> str:
    with open(os.path.join(PROMPTS_DIR, f"{name}.md"), encoding="utf-8") as f:
        return f.read()


class Evidence:
    """Every passage the AI has seen in this conversation, under a short id it can cite."""

    def __init__(self):
        self.passages = {}

    def add(self, passages: list) -> list:
        """Adds new passages and returns the ids of all of them (a passage seen before keeps its id)."""
        ids = []
        for p in passages:
            known = next((i for i, q in self.passages.items() if q.get("id") == p.get("id") and p.get("id")), None)
            if not known:
                known = f"S{len(self.passages) + 1}"
                self.passages[known] = p
            ids.append(known)
        return ids

    def show(self, ids: list) -> str:
        return "\n\n".join(f"[{i}] {knowledge.heading(self.passages[i])} ({self.passages[i]['publisher']})\n"
                           f"{self.passages[i]['text']}" for i in ids)

    def cite(self, source_id: str) -> dict:
        p = self.passages[source_id]
        return {"id": source_id, "title": knowledge.heading(p), "url": p["url"], "publisher": p["publisher"],
                "excerpt": p["text"][:300]}

    def numbers(self, ids: list) -> set:
        return numbers_in(" ".join(self.passages[i]["text"] for i in ids))


def numbers_in(text: str) -> set:
    return {n.replace(",", "") for n in NUMBER.findall(text or "")}


def grounded(text: str, ids: list, evidence: Evidence, allowed: set) -> bool:
    """Every number in the AI's sentence must appear in the passages it cites (or be the user's own data)."""
    return numbers_in(text) <= evidence.numbers(ids) | allowed


def supported(item, evidence: Evidence, allowed: set) -> dict | None:
    """An AI item kept only if it cites real passages and its numbers come from them."""
    if not isinstance(item, dict) or not str(item.get("text") or "").strip():
        return None
    ids = [s for s in dict.fromkeys(item.get("sources") or []) if s in evidence.passages]
    if not ids or not grounded(item["text"], ids, evidence, allowed):
        return None
    return {**{k: v for k, v in item.items() if k != "sources"}, "text": item["text"].strip(),
            "sources": [evidence.cite(i) for i in ids]}


# ---- tools the agent can call ----------------------------------------------------------------------------------

def tool_definitions(topics: dict) -> list:
    return [
        {"name": "search_nih",
         "description": "Search the NIH Office of Dietary Supplements and NCCIH fact sheets. Returns passages with "
                        "ids you can cite. Use it for the person's conditions, medicines, pregnancy, and anything "
                        "you want to check before writing it.",
         "input_schema": {"type": "object", "properties": {
             "query": {"type": "string", "description": "what to look for, e.g. 'iron kidney disease'"},
             "topic": {"type": "string", "enum": list(topics),
                       "description": "limit the search to one ingredient's fact sheets (optional)"}},
             "required": ["query"]}},
        {"name": "get_limits",
         "description": "This person's recommended daily amount and tolerable upper limit for one nutrient, "
                        "from the NIH tables. Returns a passage you can cite.",
         "input_schema": {"type": "object", "properties": {
             "nutrient": {"type": "string", "enum": list(NUTRIENTS)}}, "required": ["nutrient"]}},
    ]


def run_tool(name: str, args: dict, person: dict, evidence: Evidence) -> str:
    if name == "search_nih":
        topic = args.get("topic")
        found = knowledge.search(str(args.get("query", ""))[:200], [topic] if topic else None)
        return evidence.show(evidence.add(found)) if found else "No passage in the NIH fact sheets matches this."
    if name == "get_limits" and args.get("nutrient") in NUTRIENTS:
        return evidence.show(evidence.add([limits_passage(args["nutrient"], person)]))
    return "Unknown tool."


def limits_passage(nutrient: str, person: dict) -> dict:
    info = NUTRIENTS[nutrient]
    need, limit = limits.daily_need(nutrient, person), limits.upper_limit(nutrient, person["age"])
    who = describe_person(person)
    text = (f"For a {who}: recommended daily amount {need if need is not None else 'not set'} {info['unit']}; "
            f"tolerable upper limit {limit if limit is not None else 'not set'} {info['unit']} "
            f"({limits.limit_group(nutrient, person['age'])}).")
    return {"id": f"limits-{nutrient}-{person['age']}-{person['sex']}", "topic": nutrient, "title": info["name"],
            "section": "Recommended intakes and upper limit", "subsection": None, "url": info["fact_sheet"],
            "publisher": "NIH Office of Dietary Supplements", "text": text}


# ---- the conversation with the model ---------------------------------------------------------------------------

def describe_person(p: dict) -> str:
    parts = [f"{p['age']}-year-old {p['sex']}"]
    if p["sex"] == "female":
        if p.get("periods"):
            parts.append("periods started" if p["periods"] == "yes" else "no periods")
        parts += [state for state in ("pregnant", "breastfeeding") if p.get(state)]
    return ", ".join(parts)


def personal_facts(person: dict) -> list:
    """What an AI concern can be about: the person's own conditions, medicines and other supplements, and their life
    stage."""
    stage = [state for state in ("pregnant", "breastfeeding") if person.get(state)]
    if person["age"] < 18:
        stage.append(f"age {person['age']}")
    return [*person.get("conditions", []), *person.get("medicine_names", []), *person.get("supplements", []), *stage]


def run_agent(system: str, case: str, person: dict, evidence: Evidence, topics: dict) -> tuple:
    """(the model's JSON answer or None, the list of tool calls it made)."""
    research = []
    if ai.provider() != "Claude":
        answer = ai.ask([{"type": "text", "text": system + "\n\n" + case}], settings.AGENT_MAX_TOKENS, settings.AGENT_TIMEOUT)
        return answer, research
    messages = [{"role": "user", "content": case}]
    for step in range(settings.AGENT_MAX_STEPS + 1):
        body = {"max_tokens": settings.AGENT_MAX_TOKENS, "system": system, "messages": messages,
                "tools": tool_definitions(topics)}
        if step == settings.AGENT_MAX_STEPS:
            body["tool_choice"] = {"type": "none"}        # out of steps: it must answer now
        data = ai.claude_raw(body, settings.AGENT_TIMEOUT)
        if data is None:
            return None, research
        content = data.get("content", [])
        calls = [b for b in content if b.get("type") == "tool_use"]
        if not calls:
            return ai.read_json(ai.response_text(data)), research
        messages.append({"role": "assistant", "content": content})
        results = []
        for call in calls:
            research.append({"tool": call["name"], **call.get("input", {})})
            results.append({"type": "tool_result", "tool_use_id": call["id"],
                            "content": run_tool(call["name"], call.get("input", {}), person, evidence)})
        messages.append({"role": "user", "content": results})
    return None, research


def seed(evidence: Evidence, topics: dict, person: dict, extra: list) -> list:
    """The evidence found before the model starts: per ingredient, and per condition, medicine and reason."""
    kinds = ["always"] + [k for k in ("pregnant", "breastfeeding") if person.get(k)] + (["child"] if person["age"] < 18 else [])
    queries = [(q.format(t=title), [topic]) for topic, title in topics.items() for kind in kinds for q in SEED_QUESTIONS[kind]]
    queries += [(f"{words} {title}", [topic]) for words in extra for topic, title in topics.items()]
    ids = []
    for query, scope in queries:
        ids += evidence.add(knowledge.search(query, scope, SEED_PER_QUERY))
    return list(dict.fromkeys(ids))[:settings.MAX_PASSAGES_IN_PROMPT]


def product_topics(nutrients: list, herbs: list) -> dict:
    titles = knowledge.topic_titles()
    return {t: titles[t] for t in knowledge.topics_for(nutrients, herbs) if t in titles}


# ---- the two jobs ----------------------------------------------------------------------------------------------

def write_report(product: dict, maker: str | None, label: dict, person: dict, reasons: list, checks: list,
                 dosage: dict | None, nutrients: list, herbs: list) -> dict | None:
    """The cited, personal part of the report. None when no AI or no knowledge base is available."""
    topics = product_topics(nutrients, herbs)
    if not (ai.available() and knowledge.available() and topics):
        return None
    evidence = Evidence()
    personal = [*person.get("conditions", []), *person.get("medicine_names", []), *person.get("supplements", []), *reasons]
    first = seed(evidence, topics, person, personal)
    case = "\n".join([
        f"PERSON: {describe_person(person)}",
        f"THEIR HEALTH CONDITIONS (their own words): {', '.join(person.get('conditions', [])) or 'none given'}",
        f"THEIR MEDICINES: {', '.join(person.get('medicine_names', [])) or 'none given'}",
        f"OTHER SUPPLEMENTS THEY TAKE: {', '.join(person.get('supplements', [])) or 'none given'}",
        f"THEIR PERSONAL FACTS (a concern can only be about one of these): {json.dumps(personal_facts(person)) if personal_facts(person) else 'none, so give no concerns'}",
        f"WHY THEY TAKE IT: {', '.join(redact(r) for r in reasons) or 'not given'}",
        f"SUPPLEMENT: {product['name']}, maker: {maker or 'not confirmed'}",
        f"STRENGTH PER TABLET: {json.dumps(label.get('strength', []), ensure_ascii=False)}",
        f"INGREDIENT TOPICS YOU CAN SEARCH: {json.dumps(topics)}",
        f"SAFETY CHECKS ALREADY MADE BY THE RULES: {json.dumps([{k: c[k] for k in ('title', 'status', 'text')} for c in checks], ensure_ascii=False)}",
        f"DOSAGE FROM THE LABEL: {json.dumps(dosage or {}, ensure_ascii=False)}",
        "", "NIH PASSAGES:", evidence.show(first)])
    answer, research = run_agent(prompt("pharmacist"), case, person, evidence, topics)
    if not isinstance(answer, dict):
        return None
    allowed = numbers_in(json.dumps(label.get("strength", []))) | {str(person["age"])}
    count = {"kept": 0, "dropped": 0}

    def keep(item):
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            return None                                   # an empty field is not a dropped claim
        checked = supported(item, evidence, allowed)
        count["kept" if checked else "dropped"] += 1
        return checked

    one = lambda key: keep(answer.get(key))
    many = lambda key: [x for x in (keep(i) for i in answer.get(key) or []) if x]
    facts = {f.lower() for f in personal_facts(person)}
    concerns = [{**c, "level": c.get("level") if c.get("level") in LEVELS else "caution"} for c in many("concerns")
                if str(c.get("about", "")).strip().lower() in facts]          # only about this person, never general
    written = {"summary": one("summary"), "concerns": concerns, "benefits": many("benefits"),
               "side_effects": many("side_effects"), "usage": one("usage"), "purpose_note": one("purpose_note"),
               "dosage_note": one("dosage_note")}
    return {**written, "research": research, "claims": count, "mode": "agent" if ai.provider() == "Claude" else "single answer"}


def answer_question(question: str, product: dict, label: dict, person: dict, nutrients: list, herbs: list) -> dict:
    """{"answer", "sources", "covered", "mode"} for one question about a scanned supplement."""
    question = redact(question)
    topics = product_topics(nutrients, herbs)
    if not knowledge.available():
        return {"answer": NOT_COVERED, "sources": [], "covered": False, "mode": "no knowledge base"}
    evidence = Evidence()
    first = evidence.add(knowledge.search(question, list(topics) or None))
    first += evidence.add(food_guidance.as_passages(nutrients))      # the NIH food sentences for this product
    if not ai.available():
        found = [i for i in first if not evidence.passages[i]["id"].startswith("food-")][:3]
        return {"answer": "From the NIH fact sheets:" if found else NOT_COVERED,
                "sources": [evidence.cite(i) for i in found], "covered": bool(found), "mode": "search only"}
    case = "\n".join([
        f"PERSON: {describe_person(person)}; conditions: {', '.join(person.get('conditions', [])) or 'none given'}; "
        f"medicines: {', '.join(person.get('medicine_names', [])) or 'none given'}; "
        f"other supplements: {', '.join(person.get('supplements', [])) or 'none given'}",
        f"SUPPLEMENT: {product['name']}; strength per tablet: {json.dumps(label.get('strength', []), ensure_ascii=False)}",
        f"INGREDIENT TOPICS YOU CAN SEARCH: {json.dumps(topics)}",
        f"EVERYDAY FOODS AND THE NIH FOOD GROUPS THEY BELONG TO: {food_guidance.everyday_foods_text()}",
        f"QUESTION: {question}", "", "NIH PASSAGES:", evidence.show(first) or "none found yet"])
    result, research = run_agent(prompt("ask"), case, person, evidence, topics or knowledge.topic_titles())
    if (result or {}).get("covered") is False:        # the model itself says the passages don't answer it
        return {"answer": NOT_COVERED, "sources": [], "covered": False, "research": research,
                "mode": "agent" if ai.provider() == "Claude" else "single answer"}
    return {**cited_answer((result or {}).get("answer", ""), evidence,
                           numbers_in(json.dumps(label.get("strength", []))) | {str(person["age"])}),
            "research": research, "mode": "agent" if ai.provider() == "Claude" else "single answer"}


def cited_answer(text: str, evidence: Evidence, allowed: set) -> dict:
    """Keeps only the sentences that cite a real passage and whose numbers are in it; renumbers the citations
    1, 2, 3 in the order the user will see them."""
    kept, order = [], []
    for sentence in re.split(r"(?<=[.!?\]])\s+", text.strip()):
        ids = [i for i in SOURCE_ID.findall(sentence) if i in evidence.passages]
        plain = re.sub(r"\s+([.!?,;])", r"\1", SOURCE_ID.sub("", sentence)).strip()
        if not ids or not plain or not grounded(plain, ids, evidence, allowed):
            continue
        for i in ids:
            if i not in order:
                order.append(i)
        kept.append(plain.rstrip() + " " + "".join(f"[{order.index(i) + 1}]" for i in dict.fromkeys(ids)))
    if not kept:
        return {"answer": NOT_COVERED, "sources": [], "covered": False}
    return {"answer": " ".join(kept), "sources": [evidence.cite(i) for i in order], "covered": True}
