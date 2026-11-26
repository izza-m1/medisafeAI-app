# MediSafe AI

A mobile app that checks whether a vitamin, mineral or herbal supplement suits a person, using their age,
sex, periods, pregnancy, breastfeeding, medicines and health conditions. The user photographs the pack (or
searches by name) and gets a report: a verdict, the reasons for it with their sources, how to take it, foods to
keep apart, and answers to their own questions.

## Where the AI is

| Part | Model | What it does |
|---|---|---|
| Photo check | CLIP (`openai/clip-vit-base-patch32`), zero-shot | is this photo a supplement pack? |
| Label reading | EasyOCR, then Claude vision for hard labels | the text on the pack |
| Knowledge base (RAG) | `BAAI/bge-small-en-v1.5` embeddings + BM25 | finds the right NIH passages for any question |
| AI pharmacist | Claude with tool use (an agent) | researches the person's own conditions and medicines, writes the report, every claim cited |
| Ask MediSafe | the same agent | answers questions about the product from NIH text, or says it can't |
| Reason matching | the same embeddings | "always tired" matches "tiredness from low iron" |

Safety numbers (daily needs, upper limits) are not left to the AI: they are checked against the NIH tables in
`data/nutrients.json`. The AI adds what tables can't check (a condition typed in the user's own words, a
medicine not in our list) and it can only make a verdict stricter, with a cited NIH passage, never safer.

## How a scan becomes a report

```
Phone (Expo app)                     Backend (FastAPI)
----------------                     -----------------
ScanScreen.js  --POST /scan-supplement-->  routes/scans.py
                                            services/vision.py       CLIP: is this a supplement pack?
                                            services/vision.py       EasyOCR: read the text
                                            services/products.py     brand, kind of product, medicine?, maker
                                            services/label_reader.py amounts, age limits, warnings, directions
                                            services/scanner.py      puts it together, keeps the scan in memory
ConfirmScreen.js --POST /lookup-composition--> services/composition.py  front-only photo: NIH DSLD, then brand site
ReasonsScreen.js --POST /suggest-reasons-->   services/reasons.py
ReportScreen.js --POST /safety-report-->     routes/reports.py
                                            services/report.py       builds the report from:
                                              services/safety_rules.py   age, dose, sex, pregnancy -> ok/caution/stop
                                              services/medications.py    medicines chosen from the list
                                              services/reasons.py        does it fit their reason?
                                              services/pharmacist.py     AI agent: researches and writes, with citations
                                                services/knowledge.py      hybrid search over the NIH passages
                                                services/embeddings.py     text -> vectors
                                              services/food_guidance.py  food, drink and supplement interactions
                                            services/database.py     saves it to Firestore
ReportScreen.js --POST /ask-->               routes/reports.py -> services/pharmacist.py (answer_question)
```

The verdict is the most serious check: one `stop` makes it "Not safe", otherwise one `caution` makes it
"Use with caution", otherwise "Safe" (`services/safety_rules.py`: `worst`, `verdict_of`). The AI's concerns are
checks too (`key: ai_concern`), so they count, but only after they pass the guardrails below.

## How the AI pharmacist works (services/pharmacist.py)

1. **Retrieve.** For each ingredient the app searches the knowledge base for its risks, interactions and uses,
   and for each of the person's conditions, medicines and reasons. Each passage gets an id: S1, S2...
2. **Reason with tools.** Claude gets the case, the rule checks and the passages. While it works it can call
   `search_nih(query, topic)` for more passages and `get_limits(nutrient)` for this person's NIH limits
   (at most `AGENT_MAX_STEPS` calls, then it must answer).
3. **Answer** in JSON, with the passage ids behind every item.
4. **Guardrails, in code, after the model:** an item citing no real passage is dropped; an item with a number
   that is not in its passages is dropped; concerns can only add to the checks. The report shows how many
   statements passed and what the AI looked up.

Without Claude (only a Groq or Gemini key) step 2 runs once, without tools. Without any AI key the report still
works: the rule checks, the food guidance and the fact sheet links do not need the AI.

## The knowledge base (etl/build_knowledge.py)

The 24 official pages (18 NIH ODS fact sheets, 6 NIH NCCIH herb pages) are stored in `data/knowledge/pages/`.
The NIH ODS site blocks scripts, so those pages are saved from a browser; the script downloads only what is
missing. It keeps each section's text and tables (menus and reference lists dropped), cuts them into passages
of about 180 words, embeds them with `BAAI/bge-small-en-v1.5`, and saves `data/knowledge/chunks.json` and
`data/knowledge/vectors.npy`: 1,047 passages, about 120,000 words.

Why passages and not whole documents: sending 120,000 words to the AI with every scan would be slow and
expensive, and the AI is less accurate when the answer is buried in that much text. So each report gets only
the 6-14 passages about this product and this person.

Search (`services/knowledge.py`) is hybrid: vector search for meaning, BM25 for exact words like medicine
names, merged with reciprocal rank fusion, with at most 2 passages from one section so one long section can't
hide the others. Passages can be limited to one product's ingredients.

## Food, drink and supplement interactions (services/food_guidance.py)

`data/food_interactions.json` holds 28 interactions for 12 supplements, built from 33 exact sentences of the NIH
fact sheets (foods that help or lower absorption, drinks, how to take it, and supplement-with-supplement
interactions such as iron and calcium). `tests/test_11_food_interactions.py` checks that every sentence appears
word for word in its saved NIH page. Interactions with a dose (zinc 50 mg or more) apply only at that dose.

`data/foods.json` links 26 everyday foods in Pakistan (roti, daal, chai, dahi...) to the NIH food groups they
belong to, so "Calcium can lower iron absorption" also shows "doodh, dahi, chai". `etl/import_foods.py` adds
each food's official values from USDA FoodData Central.

## Measuring it (evals/)

`python -m evals.run_evals` runs `evals/cases.json` with the real models:
- retrieval: is a right passage in the top 1, 3 and 5 results (hit@k, MRR)?
- reports: does the agent catch a typed medicine or condition, without false alarms? what share of its claims
  pass the citation checks?
- questions: does Ask MediSafe answer what NIH covers, and say so when it doesn't?

The unit tests (`tests/`) check the code's logic with stand-ins for the models; the evals check the models.

## Folders

```
backend/
  main.py            starts the app and adds the routes
  settings.py        paths, keys from .env, and every tuning value (thresholds, timeouts, model names)
  datasets.py        loads every file in data/ once
  schemas.py         checks every request (profile, email, reasons, medicines)
  routes/            the API endpoints; they only receive, call a service and return
  services/          the logic, one job per file
  prompts/           the instructions given to the AI, as plain text
  data/              all facts the app uses, each with its source (see below)
  data/knowledge/    the RAG knowledge base (built by etl/build_knowledge.py)
  etl/               build_knowledge.py (NIH pages), import_foods.py (USDA), import_dsld.py (NIH label database)
  evals/             measures the AI parts with the real models
  tests/             pytest tests, one file per test group
frontend/
  App.js, index.js   app start and navigation
  api.js             backend address, sign-in token on every request, profile and history
  firebase.js        Firebase sign-in setup
  ui.js, forms.js    shared components
  screens/           one file per screen
  data/nutrients.json  the nutrient cards on the home screen
```

## Where the data comes from

| File | What it holds | Source |
|---|---|---|
| `nutrients.json` | daily need and upper limit for 16 nutrients, by age, sex, pregnancy | NIH Office of Dietary Supplements (one fact sheet link per nutrient) |
| `product_groups.json` | shared rules for vitamins and minerals, iron, prenatal, herbal, hormone products | NIH ODS; herbs from NIH NCCIH |
| `food_interactions.json` | food, drink and supplement interactions, each with its exact NIH sentences | NIH ODS fact sheets |
| `foods.json` | everyday foods in Pakistan and the NIH food groups they belong to | USDA FoodData Central |
| `medications.json` | supplement and medicine interactions | NIH ODS fact sheets, linked per entry |
| `reasons.json` | reasons each nutrient or herb is taken | NIH ODS and NCCIH |
| `dsld_products.json` | 718 real supplement labels | NIH Dietary Supplement Label Database |
| `knowledge_sources.json` | the herb and other pages the knowledge base is built from | NIH ODS and NIH NCCIH |
| `knowledge/pages/` | the 24 original pages, as published | NIH ODS and NIH NCCIH |
| `knowledge/chunks.json`, `vectors.npy` | the same text in 1,047 passages, and one vector per passage | NIH ODS and NIH NCCIH |
| `medicine_names.json` | words that show a pack is a medicine | WHO Essential Medicines List, WHO INN stems |
| `products.json`, `companies.json` | product names, brands and their owners | each company's website |
| `targets.json`, `label_words.json`, `email_rules.json`, `vision_labels.json` | words used to read labels and check input | app settings, not medical facts |

Amounts are only taken from the pack's own label, from the NIH label database, or from the brand's official
label online. Nothing is guessed: when no amounts can be found, the report says the dose was not checked and
is never "Safe".

## Run it

Backend (from `backend/`, with Python 3.12):

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Put `firebase-key.json` and `.env` (see `.env.example`) in `backend/`. Without the Firebase key the app still
runs, without accounts or history.

Frontend (from `frontend/`): set `API_BASE` in `api.js` to the laptop's IP, then

```
npm install
npx expo start
```

Tests (from `backend/`): `python -m pytest tests -v`
Evals (from `backend/`): `python -m evals.run_evals`

## Practice: find it in the code

1. Where does the user's age come from when a report is made, and where is it compared with a limit?
2. Where is the upper limit for iron for an 8-year-old written, and which function reads it?
3. Which file decides that a pregnant woman should not take Ashwagandha, and where does that rule come from?
4. A man scans Centrum Women. Which function gives the "made for women" message, and why is it orange, not red?
5. Where does the "4 hours apart" advice for thyroid medicine and calcium come from?
6. The photo shows only the front. Which two places does the app look for the full ingredient list, in what order?
7. Where is the CLIP threshold set, and what happens to a photo that scores below it?
8. What stops one user from opening another user's saved report?
9. The user typed "warfarin" as another medicine. Follow it from the profile screen to the AI's prompt.
10. Where is an AI claim with a made-up number removed, and how does the code know the number is made up?
11. Why does the search use both vectors and BM25? Find where the two rankings are merged.
12. What does the report do when there is no AI key at all? Which parts still work?
