# Sample questions for testing

Domain: a synthetic freight-forwarding operations "data lake" (320 shipments across
ocean/air/road, 11 carriers, 13 lanes) plus an `invoices` table populated only through the
Vision Document Agent's review-and-store flow. See `schema.sql` for the full data model.

Note on demo mode vs live mode: in demo mode (no `ANTHROPIC_API_KEY`), the questions below
are the ones the mock LLM client (`agents/mock_client.py`) is built to handle well end to
end. In live mode (key set), the agent is not limited to this list -- any natural-language
question about the schema should work, including rephrasings and questions not listed here.

## Flow A -- Agentic Analytics (pure shipment data)

1. Which carrier has the highest average freight cost?
2. How many shipments are currently delayed, and what are the top delay reasons?
3. What's the total quoted freight cost by transport mode this year?
4. **Follow-up to #3:** Now break that down by carrier as well
5. Show me delayed shipments from Nhava Sheva to Jebel Ali
6. What is the average transit time by carrier for ocean shipments?
7. **Follow-up to #6:** Now just show Maersk and MSC

## Guardrail checks -- should trigger a clarifying question, not a guess

8. How's Q3 looking? *(too vague -- no metric specified)*
9. What's our customer satisfaction score for these shipments? *(field doesn't exist in the schema)*

## Flow B -- Vision Document Agent

10. Upload (or select from the bundled samples in `data/sample_invoices/`) any of:
    `MSK-INV-88213.pdf`, `MSK-INV-88490.pdf`, `ONE-INV-51027.pdf`, `LHC-INV-70915.pdf`
    -- review the extracted fields, note the flagged low-confidence field on the ONE Line
    and Lufthansa Cargo invoices, then confirm & store.

## Flow C -- End-to-end linkage (run only after storing at least one invoice above)

11. What's the total invoiced amount by carrier so far?
12. List the invoices where the invoiced amount is higher than the quoted cost, and by how much
13. Are there any invoices still pending review?

Questions 11-13 return zero rows until at least one document has been extracted and stored --
that's the intended behaviour, not a bug: it's the proof that Flow A and Flow B are actually
connected through the same store rather than being two disconnected demos.

## Bonus -- Part 2 linkage (run after processing at least one SU email in the Verification tab)

14. Show me all the SU document verifications that came back with discrepancies
15. Show me all the SU document verifications

These pull from the `verifications` table Part 2 adds, through the exact same analytics agent
and guardrails as questions 1-13 -- no separate system.
