# FreightIQ -- Agentic Analytics + Vision Document Intelligence

GoComet Agentic AI PM assignment, **Part 1 + Part 2**, in one repo. Part 2 is not a separate
app -- it's the same agents, database and guardrails from Part 1, applied to a real workflow
(see "Part 2" section below).

## Part 1 -- Build the Foundation

A working POC combining:

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

python3 data/seed_shipments.py                # generates db/freight.db (320 synthetic shipments)
python3 data/generate_sample_invoices.py      # generates data/sample_invoices/*.pdf (4 sample docs, Part 1)
python3 data/generate_sample_trade_docs.py    # generates data/sample_su_docs/*.pdf (2 sample docs, Part 2)

streamlit run app.py
```

Then open the URL Streamlit prints (typically http://localhost:8501). All three tabs (Analytics,
Vision Document Agent, SU -> CG Verification) are in the same app -- Part 2 is the third tab.

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
app.py                          Streamlit UI: Analytics tab, Document Agent tab,
                                 SU -> CG Verification tab (Part 2), About tab
schema.sql                      SQLite schema: shipments + invoices + verifications
agents/
  llm_client.py                 Picks real Anthropic client or MockClient based on env
  mock_client.py                Deterministic offline stand-in (see above)
  analytics_agent.py            Tool-use loop: run_sql / ask_clarification
  sql_guard.py                  SELECT-only / allowlist / row-cap / read-only enforcement
  document_agent.py             Part 1: freight invoice vision extraction + storage
  verification_agent.py         Part 2: trade-doc extraction, rule comparison, reply drafting
data/
  seed_shipments.py             Generates the synthetic shipment dataset
  generate_sample_invoices.py   Generates the 4 sample freight invoice PDFs (Part 1)
  generate_sample_trade_docs.py Generates the 2 sample SU trade-document PDFs (Part 2)
  sample_invoices/*.pdf         Part 1 sample documents
  sample_su_docs/*.pdf          Part 2 sample documents
db/freight.db                   SQLite database (generated)
PRD.docx / PRD.md               Part 1 PRD (Deliverable 1)
PRD_Part2.pdf                   Part 2 PRD (max 1 page)
sample_questions.md             Part 1 submission requirement
demo_script.md                  Part 1 demo script
demo_script_part2.md            Part 2 demo script
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

## Part 2 -- Agentic Document Verification (SU -> CG -> Customer)

Part 2 applies Part 1's exact machinery to a real workflow described in the assignment: a
Shipping Unit (SU) emails trade documents, a Cargo/Control Group (CG) validator manually checks
every field against customer requirements today, and Part 2's job is to remove that manual
reading, not the three-party structure.

**What's new vs. Part 1** (everything else -- the DB, the guardrails, the mock/live client
switch -- is reused as-is):

- `agents/verification_agent.py` -- a mock inbox (`MOCK_INBOX`, 2 SU emails with real PDF
  attachments), a per-customer rule profile (`CUSTOMER_RULES`), field comparison logic that
  checks some fields against the rule profile and others (port of discharge, weight) directly
  against the original Part 1 booking in `shipments` -- the booking *is* the requirement for
  those fields -- and reply-email drafting via the same LLM client used in Part 1.
- `verifications` table in `schema.sql`, registered in `sql_guard.py`'s table allowlist and in
  `analytics_agent.py`'s schema description, so verification results are queryable from the
  Analytics tab immediately (try: *"Show me all the SU document verifications that came back
  with discrepancies"*).
- A third Streamlit tab, "SU -> CG Verification," showing all four required states:
  **Incoming** (mock inbox with a "Process with agent" trigger), **Verification Result**
  (field-by-field match/mismatch/uncertain table with per-field confidence), **Discrepancy
  Detail** (click any flagged field to expand found vs. expected), and **Draft Reply** (editable
  text area; a human must click "CG: Approve & Send" -- the agent never sends on its own).

**The two bundled scenarios** (both reference real shipments already in `shipments`, so the
comparison against booking data is real, not staged):

- `SU_TRADEDOC_GC-2026-00004.pdf` -- clean pass, every field matches -> approval draft.
- `SU_TRADEDOC_GC-2026-00009.pdf` -- 4 deliberate mismatches (wrong consignee legal name, wrong
  Incoterm, wrong port of discharge, weight outside tolerance) plus 1 low-confidence field
  (goods description) that is surfaced as "uncertain" rather than silently passed -> amendment
  draft listing each issue by field name, found value, and expected value.

No extra setup is needed beyond the Part 1 quick start above -- `generate_sample_trade_docs.py`
creates both PDFs, and the verification tab reads them directly from `data/sample_su_docs/`.
