# Demo script (~1.5 minutes)

**Setup (before recording):** `streamlit run app.py`, fresh `db/freight.db` (0 invoices).

---

**0:00-0:10 -- Framing**
"This is FreightIQ: a POC for two agentic capabilities GoComet's own customers need --
asking questions of shipment data without an analyst, and turning freight invoices into
structured, queryable data automatically. Both are wired into one system, not two demos."

**0:10-0:35 -- Flow A: Agentic Analytics**
- Ask: *"Which carrier has the highest average freight cost?"*
- Show the answer, then expand "Transparency: query used" -- point out the actual SQL,
  the result table, and the auto-generated bar chart.
- Ask a follow-up in the same thread: *"Now just show Maersk and MSC"* -- show that the
  agent refines the prior result using conversation context, not a fresh unrelated query.
- Briefly trigger a guardrail: ask *"How's Q3 looking?"* -- show the agent asks a clarifying
  question instead of inventing an answer.

**0:35-1:05 -- Flow B: Vision Document Agent**
- Switch to the Document tab, select the bundled sample invoice `MSK-INV-88213.pdf`.
- Show the rendered invoice image next to the extracted fields.
- Point out the confidence bar; open a low-confidence sample (e.g. `ONE-INV-51027.pdf`)
  to show a flagged field (customs_duty) that the UI highlights before storage.
- Click "Confirm & store."

**1:05-1:25 -- Flow C: End-to-end linkage**
- Back in the Analytics tab, ask: *"What's the total invoiced amount by carrier so far?"*
  -- show the number reflects the invoice just stored.
- Ask: *"List the invoices where the invoiced amount is higher than the quoted cost, and by
  how much"* -- this is the moment that proves A and B are one connected system: the answer
  joins data that came from a natural-language question (A) with data that came from a
  scanned PDF (B).

**1:25-1:30 -- Close**
"Same agent architecture in demo mode or live mode -- only the LLM reasoning changes,
everything else (guardrails, storage, UI) is real and already tested."
