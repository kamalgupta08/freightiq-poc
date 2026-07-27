# FreightIQ: Agentic Analytics + Document Intelligence for Freight Operations
### Product Requirements Document — Part 1 (Foundation)
GoComet Agentic AI PM Assignment | Prepared by Kamal Gupta

---

## 1. Problem Statement

Freight and logistics organizations generate two kinds of data that never talk to each other: structured operational records (bookings, costs, transit times, delays) sitting in a data lake or warehouse, and unstructured documents (freight invoices, bills of lading, customs paperwork) sitting in inboxes and shared drives. Today, getting value out of either requires a person in the loop who isn't the person who needs the answer.

Three failure patterns show up repeatedly:

**Analyst dependency.** An ops manager who wants to know "which carrier is costing us the most on the Nhava Sheva–Jebel Ali lane this month" cannot get that answer without a SQL-literate analyst or a pre-built dashboard that may not have that exact cut. Every new question becomes a ticket.

**Manual reconciliation of documents against data.** Freight invoices arrive as PDFs. Someone re-keys line items into a spreadsheet or ERP field by field, then manually checks whether the invoiced amount matches what was quoted at booking. This is slow, error-prone, and the two records — the quote in the system and the invoice in the inbox — are never structurally connected.

**Low trust in existing tools.** Dashboards show numbers without showing the underlying query or data, so when a number looks wrong, the user has no way to verify it themselves — they have to go back to the analyst, defeating the point of self-service.

Success for a user in the first 5 minutes of using this product looks like: they type a real business question in plain English and get an answer with the data and query behind it visible; they upload a real invoice and, in under a minute, watch it turn into a structured, reviewed record; they ask a follow-up question that pulls in the exact invoice they just uploaded, without re-explaining context.

## 2. Users + Jobs-to-be-Done

**Persona 1 — Priya, Logistics Operations Manager.** Owns day-to-day shipment execution across multiple carriers and lanes. Not SQL-literate. Currently pings the analytics team or opens three different dashboards to answer questions from her own leadership.

**Persona 2 — Rahul, Freight Audit & Payables Analyst.** Reconciles carrier invoices against quoted freight cost before approving payment. Currently opens each PDF invoice manually, re-types charges into Excel, and cross-checks against the booking system by hand — for hundreds of invoices a month.

**Jobs-to-be-done:**

1. When I need to check shipment status or cost, I want to ask a direct question and get an answer with the data behind it, so I don't have to wait on the analytics team or open five dashboards.
2. When a carrier invoice arrives as a PDF, I want its charges extracted into structured fields automatically, so I don't have to manually re-key them into our systems.
3. When an invoice has been extracted, I want to compare it against the originally quoted cost, so I can catch overcharges before approving payment.
4. When I'm shown an answer, I want to see exactly what query and data produced it, so I can trust it enough to act on without re-verifying manually.
5. When my first question doesn't give me the full picture, I want to refine it conversationally — filter, group, change the time window — without starting over.
6. When the system can't confidently answer a question or read a document, I want it to tell me plainly rather than guess, so I don't make a costly decision on bad data.

## 3. Product Scope

**MVP (built in this 24-hour window):**
- Natural-language Q&A over a synthetic freight shipments dataset, with a real agentic tool-use loop (not single-shot text-to-SQL), transparency into the query used, a result table, one chart type, and multi-turn follow-up refinement.
- Vision-based extraction of one document type — freight invoices — into a structured schema, with per-field confidence scoring, mandatory human review before storage, and storage into the same database the analytics layer queries.
- Joined analytics across the operational data and the stored, reviewed invoice data (the end-to-end linkage the assignment requires).

**Explicitly out of scope for this MVP:**
- Multi-user accounts, roles, or permissions.
- Live integration with a real TMS/ERP/data warehouse (a local SQLite store stands in for "the data lake"; the query layer is designed so swapping in a real warehouse is a connection-string change, not a redesign).
- Document types beyond freight invoices (bills of lading, packing lists, customs forms — flagged for a later iteration).
- Any write-back to source systems, payment triggers, or approval workflows.
- Non-English documents, real-time/streaming data, mobile clients.

**Key assumptions and constraints:** single-tenant, demo-scale data volumes (hundreds, not millions of rows); one vision-and-reasoning model provider; every extracted document is reviewed by a human before it enters the queryable store — there is no auto-approve path, by design.

## 4. Key Flows

**Flow A — Ask → Answer → Visualise → Follow-up.** User types a question. The agent decides whether it has enough information to query; if not, it asks a clarifying question instead of guessing. If it does, it issues a governed SQL query, receives the actual result, and only then produces a grounded text answer, alongside the query it ran (for transparency), the result table, and an auto-generated chart. The user can immediately follow up in the same thread — "now just show Maersk and MSC" — and the agent treats it as a refinement of the prior result rather than a disconnected new question.

**Flow B — Upload Document → Extract → Review → Store → Query Later.** User uploads a freight invoice (PDF or image). The system renders it and runs structured extraction with a vision-capable model, which is required to report a confidence score and explicitly name any field it isn't sure about. The user sees the rendered document next to the extracted fields, with low-confidence fields visibly flagged, and can correct anything before confirming. Only on explicit confirmation is the record written to the store — at which point it becomes queryable through Flow A.

## 5. Trust, Safety & Failure Handling

**Avoiding fabricated answers.** The agent is architecturally prevented from answering before it has a real query result: the final natural-language answer is only generated after a tool call has returned actual rows from the database. If a query returns zero rows, the product says so explicitly rather than inventing a plausible-sounding number.

**Explaining sources.** Every answer is shown alongside the exact query that produced it and the resulting data table — the user never has to take the answer on faith.

**Missing or ambiguous questions.** Questions that are too vague ("how's Q3 looking?") or reference data the system doesn't have (customer satisfaction, profit margin) route to a dedicated clarifying-question path instead of a guess. This is a first-class agent action, not an error state.

**Extraction uncertainty.** The extraction step requires a confidence score and an explicit list of low-confidence fields as part of its structured output — not a follow-up judgment call. The review UI surfaces these before storage is possible, so uncertain data cannot silently enter the system that later analytics will treat as ground truth.

**Guardrails against unsafe actions.** The query tool only accepts single, read-only SELECT statements against an explicit table allowlist, enforced independently of the model's own good behavior — including at the database connection level — so a prompt-level guardrail failure alone cannot cause a write or an out-of-scope read.

## 6. Metrics & Success Criteria

**North-star metric:** Self-serve resolution rate — the percentage of freight data questions and invoice reconciliations completed by the end user without analyst involvement or manual re-keying.

**Supporting metrics:**
1. Median time from question asked to answer shown.
2. Rate at which users open the underlying query/data behind an answer (a trust-and-verify signal, not just a click-through metric).
3. Follow-up usage rate per session (proxy for conversational trust — users only refine an answer they believe is close).
4. Invoice field-level extraction accuracy against human-corrected ground truth.
5. Percentage of extracted invoices requiring zero manual field corrections before storage.
6. Time from document upload to stored, queryable record.
7. Rate at which the agent falls back to a clarifying question (a healthy nonzero rate; near-zero suggests the model is guessing instead of asking).
8. Freight-cost variance (invoice vs. quote) caught before payment approval, in dollar terms.

**Go / No-Go criteria for a pilot:**
- **Go** if all three required minimum behaviors (analytics, extraction, end-to-end linkage) pass reliably across a test set; the SQL guardrail blocks 100% of disallowed query attempts under adversarial testing; confidence flagging agrees with human judgment on which fields need review at least 90% of the time; and at least one real pilot user completes the full flow unassisted.
- **No-Go** if any hallucinated numeric answer appears in testing, any guardrail bypass is found, or any low-confidence field is found to have entered storage without being flagged.

## 7. Next 2 Iterations

**Iteration 1 (weeks 1-2):** Replace the local SQLite store with a connection to a real warehouse or TMS export; extend document extraction to bills of lading, packing lists, and customs paperwork; persist conversation history across sessions rather than per-session state; add basic role-based views for ops vs. finance users.

**Iteration 2 (weeks 3-4):** Move from purely reactive Q&A toward proactive agent behavior — a scheduled daily exception digest ("3 shipments delayed this week, 2 invoices exceeded quote by more than 10%"); an approval-gated write-back path from a confirmed invoice reconciliation into the ERP/TMS; batch document upload; and a full audit log of every agent query and extraction decision for compliance review.
