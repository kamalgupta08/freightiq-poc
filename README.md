# FreightIQ -- Agentic Analytics + Vision Document Intelligence

GoComet Agentic AI PM assignment, Part 1. A working POC combining:

- **Agentic Analytics Layer** -- ask a question in natural language about freight shipments,
  get a grounded answer, the SQL used, a result table, and a chart. Supports multi-turn
  follow-up refinement (filter / group / time window).
- **Vision Document Agent** -- upload a freight invoice (PDF or image), get structured fields
  extracted by a vision-capable model, review/edit them, and store them.
- **End-to-end linkage** -- once an invoice is stored, it's immediately queryable through the
  same analytics layer (e.g. "total invoiced amount by carrier," "invoices over quote").

Domain: a synthetic freight-forwarding operations data lake (this mirrors GoComet's own
space -- shipment visibility + freight invoice audit -- rather than a generic dataset).

## Quick start

```bash
cd gocomet_agentic_freight_poc
python3 -m venv .venv && source .venv/bin/activate     # optional but recommended
pip install -r requirements.txt

# Optional but recommended -- see "Demo mode vs live mode" below
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY

python3 data/seed_shipments.py          # generates db/freight.db (320 synthetic shipments)
python3 data/generate_sample_invoices.py # generates data/sample_invoices/*.pdf (4 sample docs)

streamlit run app.py
```

Then open the URL Streamlit prints (typically http://localhost:8501).

## Demo mode vs live mode

The app runs either way:

- **No `ANTHROPIC_API_KEY` set** -- "demo mode." A deterministic mock LLM client
  (`agents/mock_client.py`) handles the curated question set in `sample_questions.md` and the
  four bundled sample invoices, so you can click through the entire product with zero setup.
  Every other part of the system is real: the SQL guardrails, the read-only DB connection, the
  tool-use control flow, the storage step, and the end-to-end linkage.
- **`ANTHROPIC_API_KEY` set** -- "live mode." The exact same agent code
  (`analytics_agent.py`, `document_agent.py`) instead calls the real Anthropic API for both
  natural-language-to-SQL reasoning and vision extraction, and is no longer limited to the
  curated question set.

This is a deliberate testability choice, not a shortcut: it means the wiring between the two
agents and the database can be verified without needing a live key, and the sidebar always
tells you which mode you're in.

## Project structure

```
app.py                          Streamlit UI (analytics tab, document tab, about tab)
schema.sql                      SQLite schema: shipments + invoices
agents/
  llm_client.py                 Picks real Anthropic client or MockClient based on env
  mock_client.py                Deterministic offline stand-in (see above)
  analytics_agent.py             Tool-use loop: run_sql / ask_clarification
  sql_guard.py                  SELECT-only / allowlist / row-cap / read-only enforcement
  document_agent.py             Vision extraction (forced structured tool call) + storage
data/
  seed_shipments.py             Generates the synthetic shipment dataset
  generate_sample_invoices.py   Generates the 4 sample invoice PDFs
  sample_invoices/*.pdf         Sample documents for the Document Agent demo
db/freight.db                   SQLite database (generated)
PRD.docx / PRD.md               Deliverable 1
sample_questions.md             Deliverable 2 requirement
demo_script.md                  Deliverable 2 requirement
```

## Design notes / what to look at first

- **Guardrails are enforced in code, not just prompted.** `agents/sql_guard.py` rejects
  anything that isn't a single SELECT against the two allowed tables, force-appends a row
  limit, and executes against a `mode=ro` SQLite connection with `PRAGMA query_only = ON` --
  so even if every prompt-level instruction were ignored, nothing can write or read outside
  the allowlisted tables.
- **The model never states a number it didn't just query for.** The analytics agent's final
  answer is only produced after a tool result is in the conversation; the system prompt
  and the mock's synthesis logic both refuse to answer with 0 matching rows rather than
  guessing.
- **Ambiguous or out-of-schema questions get a clarifying question**, not a hallucinated
  answer (`ask_clarification` tool, exercised in `sample_questions.md` #8-9).
- **Extraction uncertainty is structural, not cosmetic.** The vision tool call requires the
  model to report a confidence score and name any field it isn't sure about; the UI surfaces
  those with a warning and a ⚠️ marker before the user can store the record.
- **A and B are genuinely one system.** The `invoices` table has a foreign key to
  `shipments.shipment_id`, and the analytics agent's schema includes both tables --
  it can join across a natural-language question and an extracted document in a single query.

## Known limitations (by design, for a 24-hour POC)

- Single-user, no auth -- fine for a demo, not for a pilot (see PRD "Out of scope").
- The document agent extracts one invoice type; field set would need extending for e.g.
  bills of lading or packing lists.
- Demo-mode NL understanding is keyword-matched, not general -- this is explicit and
  disclosed in the UI, not hidden.
