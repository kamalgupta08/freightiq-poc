# Part 2 demo script (~2 minutes)

**Setup (before recording):** `streamlit run app.py`, open the "SU → CG Verification" tab.

---

**0:00-0:35 -- PRD thinking**
"Part 2 applies exactly what I built in Part 1 to GoComet's real SU-CG-Customer document loop.
Today CG manually reads every field on every trade document against customer rules and types
out amendments by hand, two to four cycles per shipment, four to twenty-four hours of delay
each. Nothing about the three-party structure needs to change -- what needs to stop is a human
reading every field. My north-star metric is median time from SU document received to CG-
approved reply sent, and the one failure mode I designed against is the agent silently
approving a field it isn't actually sure about -- so confidence is checked per field, and
anything below threshold gets forced to 'uncertain' no matter what the text says."

**0:35-1:10 -- UI walkthrough (clean scenario)**
- Point to the inbox: "This is the mock inbox -- SU just emailed a trade doc for shipment
  GC-2026-00004." Click **Process with agent**.
- Once processed, scroll through the four states: "Verification Result shows all seven fields
  checked -- consignee, HS code, ports, Incoterm, weight, goods description -- all green,
  each with its own confidence score. No Discrepancy Detail needed since nothing's flagged.
  Draft Reply shows a clean approval the agent generated -- but it's sitting here waiting for
  me to click Send, it hasn't gone anywhere yet."
- Click **CG: Approve & Send**.

**1:10-1:45 -- Agent running live (issues scenario)**
- Process the second email, GC-2026-00009: "This one has four real problems baked in -- wrong
  consignee legal name, wrong Incoterm, wrong port of discharge, and a weight that's off by
  more than the 3% tolerance versus what was actually booked."
- Click into a couple of the flagged rows in Discrepancy Detail: "Found vs. expected, plus why
  -- for port of discharge it's literally pulling the destination port from the original
  booking in Part 1's shipments table, not a hardcoded rule."
- Point at the goods-description row: "This one's marked uncertain, not mismatch -- the
  extraction wasn't confident on that field, so it refused to silently pass it even though the
  text technically overlaps."
- Show the Draft Reply: "The agent wrote the full amendment listing all four issues by field
  name. I can edit this before sending." Click **CG: Approve & Send**.

**1:45-2:00 -- Close the loop**
- Switch to the Analytics tab, ask *"Show me all the SU document verifications that came back
  with discrepancies"* -- show the answer pulling from the same `verifications` table the
  agent just wrote to. "Same analytics agent from Part 1, same guardrails, new table -- this
  is what 'connect what you built' means in practice."
