"""TC-10  The AI part: the knowledge base (RAG), the AI pharmacist agent and its guardrails, and Ask MediSafe.
Claude is replaced by scripted replies, so these tests check the app's own logic around the model: what it sends,
how it runs the tools, and what it refuses to pass on to the user."""
import re

from conftest import check, colour
from etl import build_knowledge
from services import ai, embeddings, pharmacist
import settings

SANGOBION = [("Sangobion", 60), ("Each capsule contains: Iron 30 mg", 10)]
ASHWAGANDHA = [("Ashwagandha", 60), ("Ashwagandha root extract 500 mg", 10)]


def source_id(body: dict, words: str) -> str:
    """The id (S1, S2...) the app gave the passage whose heading contains these words, in what Claude was sent."""
    text = str(body["messages"])
    return re.search(rf"\[(S\d+)\] [^\[]*{words}", text).group(1)


# ---- building the knowledge base ------------------------------------------------------------------------------

PAGE = """<html><body><nav><a href="/">Home</a> <a href="/fs">Fact sheets</a></nav><main>
<h1>Iron</h1>
<h2>Table of Contents</h2><ul><li><a href="#a">Introduction</a></li><li><a href="#b">Health Risks</a></li></ul>
<h2>Introduction</h2><p>Iron is a mineral that is naturally present in many foods [1,2].</p>
<h2>Health Risks from Excessive Iron</h2>
<table><caption>Table 3: Tolerable Upper Intake Levels (ULs) for Iron</caption>
<tr><th>Age</th><th>Male</th><th>Female</th></tr><tr><td>14+ years</td><td>45 mg</td><td>45 mg</td></tr></table>
<h3>Interactions with zinc</h3><p>High doses of iron supplements can reduce zinc absorption in the body [12].</p>
<h2>References</h2><ol><li>Some journal article about iron, 2019, pages 1-10.</li></ol>
</main><footer><p>Office of Dietary Supplements, Bethesda, Maryland</p></footer></body></html>"""


def test_fact_sheet_is_split_into_cited_sections():
    found = build_knowledge.sections(PAGE)
    headings = [(section, sub) for section, sub, _ in found]
    assert ("Introduction", None) in headings
    assert ("Health Risks from Excessive Iron", None) in headings
    assert ("Health Risks from Excessive Iron", "Interactions with zinc") in headings
    text = " ".join(p for _, _, paragraphs in found for p in paragraphs)
    assert "References" not in str(headings) and "journal article" not in text      # reference list dropped
    assert "Home" not in text and "Bethesda" not in text                              # menu and footer dropped
    assert "[1,2]" not in text and "[12]" not in text                                 # citation marks removed
    assert "14+ years | 45 mg | 45 mg" in text                                        # tables kept as text


def test_long_sections_become_overlapping_passages():
    paragraph = " ".join(f"word{i}" for i in range(400))
    passages = build_knowledge.chunk([paragraph, "A short last paragraph about iron."])
    assert all(len(p.split()) <= settings.CHUNK_WORDS for p in passages)
    first, second = passages[0].split(), passages[1].split()
    assert first[-settings.CHUNK_OVERLAP_WORDS:] == second[:settings.CHUNK_OVERLAP_WORDS]
    assert passages[-1].endswith("A short last paragraph about iron.")


def test_keyword_search_finds_a_medicine_name(nih_passages):
    found = nih_passages.search("can I take it with levothyroxine", ["iron"])
    assert found[0]["subsection"] == "Levothyroxine"
    assert all(p["topic"] == "iron" for p in found)


# ---- the AI pharmacist in the report --------------------------------------------------------------------------

def test_agent_researches_a_typed_medicine_and_adds_a_cited_concern(client, scan, report, nih_passages, fake_claude):
    sent = fake_claude([
        {"tool": "search_nih", "input": {"query": "iron and levothyroxine", "topic": "iron"}},
        lambda body: {"summary": {"text": "You can take it, but not with your thyroid tablet.", "sources": [source_id(body, "Levothyroxine")]},
                      "concerns": [{"title": "Thyroid medicine", "about": "Thyroxine 50", "level": "caution",
                                    "text": "Iron lowers the absorption of levothyroxine. Keep them 4 hours apart.",
                                    "sources": [source_id(body, "Levothyroxine")]}],
                      "benefits": [{"text": "Iron helps carry oxygen in the blood.", "sources": [source_id(body, "Introduction")]}],
                      "side_effects": []}])
    status, body = report(scan(SANGOBION), "woman_26_periods", other_medicines=["Thyroxine 50"])
    assert status == 200
    assert "Thyroxine 50" in str(sent[0]["messages"])                    # the typed medicine reached the agent
    assert sent[1]["messages"][-1]["content"][0]["type"] == "tool_result"  # its search result was fed back
    assert body["report"]["ai_research"] == [{"tool": "search_nih", "query": "iron and levothyroxine", "topic": "iron"}]
    concern = check(body, "ai_concern")
    assert concern["status"] == "caution" and concern["citations"][0]["url"].endswith("Iron-HealthProfessional/")
    assert colour(body) == "orange"                                      # Safe without it; the concern made it stricter
    assert body["report"]["benefits"][0]["sources"][0]["title"] == "Iron - Introduction"
    assert body["ai"]["mode"] == "agent"


def test_claims_without_a_real_source_or_with_invented_numbers_are_dropped(client, scan, report, nih_passages, fake_claude):
    fake_claude([lambda body: {
        "summary": {"text": "Fine for you.", "sources": ["S1"]},
        "concerns": [{"title": "Made up", "level": "stop", "text": "Iron causes hair loss.", "sources": ["S99"]}],
        "benefits": [{"text": "Raises energy by 40 percent.", "sources": ["S1"]},
                     {"text": "Has no source.", "sources": []}],
        "side_effects": [{"text": "More than 20 mg/kg at once can upset the stomach.", "sources": [source_id(body, "Excessive")]}]}])
    _, body = report(scan(SANGOBION), "woman_26_periods")
    assert check(body, "ai_concern") is None                             # S99 does not exist
    assert body["report"]["benefits"] == []                              # 40 is in no passage; the other has no source
    assert [s["text"] for s in body["report"]["side_effects"]] == ["More than 20 mg/kg at once can upset the stomach."]
    assert colour(body) == "green"


def test_ai_can_never_make_a_verdict_safer(client, scan, report, nih_passages, fake_claude):
    fake_claude([{"summary": {"text": "Completely safe for children.", "sources": ["S1"]}, "concerns": []}])
    _, body = report(scan(SANGOBION), "boy_8")
    assert body["report"]["is_safe_to_take"]["verdict"] == "Not safe"


def test_agent_must_answer_when_out_of_steps(client, scan, report, nih_passages, fake_claude):
    search = {"tool": "search_nih", "input": {"query": "iron"}}
    sent = fake_claude([search] * settings.AGENT_MAX_STEPS + [{"summary": None}])
    report(scan(SANGOBION), "woman_26_periods")
    assert len(sent) == settings.AGENT_MAX_STEPS + 1
    assert sent[-1]["tool_choice"] == {"type": "none"} and "tool_choice" not in sent[0]


def test_limits_tool_gives_this_persons_numbers(nih_passages):
    evidence = pharmacist.Evidence()
    shown = pharmacist.run_tool("get_limits", {"nutrient": "iron"}, {"age": 26, "sex": "female", "periods": "yes"}, evidence)
    assert "recommended daily amount 18 mg" in shown and "upper limit 45 mg" in shown


def test_without_claude_one_answer_is_written_from_the_passages(client, scan, report, nih_passages, monkeypatch):
    prompts = []
    monkeypatch.setattr(ai, "available", lambda: True)
    monkeypatch.setattr(ai, "provider", lambda: "Groq")
    monkeypatch.setattr(ai, "ask", lambda content, max_tokens, timeout=0: prompts.append(content) or
                        {"summary": {"text": "Suits you.", "sources": ["S1"]}})
    _, body = report(scan(ASHWAGANDHA), "man_30")
    text = prompts[-1][0]["text"]
    assert "NIH PASSAGES" in text and "Ashwagandha - Safety" in text
    assert body["ai"]["mode"] == "single answer"


def test_report_still_works_with_no_ai_at_all(client, scan, report, nih_passages):
    status, body = report(scan(SANGOBION), "woman_26_periods")
    assert status == 200 and body["ai"]["used"] is False and colour(body) == "green"


# ---- typed conditions and medicines -----------------------------------------------------------------------------

def test_typed_conditions_are_checked(client, search):
    s = search("Sangobion")
    r = client.post("/safety-report", json={"scan_id": s["scan_id"], "age": 30, "sex": "male",
                                            "conditions": [f"condition {i}" for i in range(9)]})
    assert r.status_code == 422 and "at most" in r.json()["detail"]


# ---- Ask MediSafe -----------------------------------------------------------------------------------------------

def ask(client, scan_result, question, person="woman_26_periods"):
    from conftest import PEOPLE
    r = client.post("/ask", json={"scan_id": scan_result["scan_id"], "question": question, **PEOPLE[person]})
    assert r.status_code == 200, r.text
    return r.json()


def test_answer_keeps_only_cited_and_grounded_sentences(client, scan, nih_passages, fake_claude):
    fake_claude([lambda body: {"answer": (f"Iron lowers how much levothyroxine you absorb [{source_id(body, 'Levothyroxine')}]. "
                                          f"Keep them 4 hours apart [{source_id(body, 'Levothyroxine')}]. "
                                          f"Some say 6 hours is better [{source_id(body, 'Levothyroxine')}]. "
                                          "It also cures thyroid disease."), "covered": True}])
    out = ask(client, scan(SANGOBION), "Can I take this with my thyroid tablet levothyroxine?")
    assert out["answer"] == "Iron lowers how much levothyroxine you absorb. [1] Keep them 4 hours apart. [1]"
    assert out["covered"] and out["sources"][0]["title"] == "Iron - Interactions with Medications - Levothyroxine"


def test_question_the_sources_dont_cover(client, scan, nih_passages, fake_claude):
    fake_claude([{"answer": "Probably fine with coffee.", "covered": True}])
    out = ask(client, scan(SANGOBION), "Is it fine with coffee?")
    assert out["covered"] is False and out["answer"] == pharmacist.NOT_COVERED and out["sources"] == []


def test_without_ai_ask_returns_the_matching_passages(client, scan, nih_passages):
    out = ask(client, scan(SANGOBION), "levothyroxine")
    assert out["mode"] == "search only" and out["sources"][0]["title"].endswith("Levothyroxine")


# ---- reasons in the user's own words ------------------------------------------------------------------------------

def test_reason_with_the_same_meaning_as_a_real_use(client, scan, report, monkeypatch):
    monkeypatch.setattr(embeddings, "similarity",
                        lambda text, uses: [0.9 if "tired" in u.lower() or "energy" in u.lower() else 0.1 for u in uses])
    _, body = report(scan(SANGOBION), "woman_26_periods", reasons=["I feel exhausted all day"])
    result = body["report"]["purpose_check"]["results"][0]
    assert result["result"] == "helps" and "which matches your reason" in result["text"]


def test_off_topic_question_is_not_covered_even_with_a_citation(client, scan, nih_passages, fake_claude):
    fake_claude([lambda body: {"answer": f"These passages are about iron, not cricket [{source_id(body, 'Introduction')}].",
                               "covered": False}])
    out = ask(client, scan(SANGOBION), "Who won the cricket world cup?")
    assert out["covered"] is False and out["answer"] == pharmacist.NOT_COVERED and out["sources"] == []


def test_concern_not_about_the_persons_profile_is_dropped(client, scan, report, nih_passages, fake_claude):
    fake_claude([lambda body: {"concerns": [
        {"title": "Stomach", "about": "everyone", "level": "caution", "text": "Iron can upset the stomach.",
         "sources": [source_id(body, "Excessive")]}]}])
    _, body = report(scan(SANGOBION), "woman_26_periods")
    assert check(body, "ai_concern") is None and colour(body) == "green"
