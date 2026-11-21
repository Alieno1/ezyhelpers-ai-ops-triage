# Business Workflow & Pilot Framing

## The 09:00 AM Bengaluru Operations Problem

At 09:00 AM IST, 12 events sit in the duty desk inbox while only **one coordinator** is free to make an outbound call. Calling the wrong person first leaves an elderly father unattended after `09:10 IST`; promising an unconfirmed replacement or refund causes customer disputes; answering a "don't call" customer by phone breaks trust.

## Two Bottlenecks Between Message Arrival & Follow-up

1. **Fragmented Context & Manual Cross-Referencing:** Related messages arrive across separate threads (e.g., customer `M01` in `T01` and Sales handoff `M07` in `S11` both concern `B101`), Hinglish text (`M04`: *"Kal cook ko 8 ki jagah 10 baje bhej sakte ho?"*) slows scanning, and coordinators must check the booking register row by row before knowing if a refund (`B103` vs `B106`) or cover (`B105`) is confirmed.
2. **Urgency Triage & Guardrail Verification Under Time Pressure:** Without a deterministic ranker, FIFO handling treats a `08:26` refund question or `08:33` prospect enquiry ahead of or alongside an uncovered elder care gap (`B101`, deadline `09:10`) or an unlinked same-day question (`M10`). Under pressure, staff risk making unsupported promises (ETAs, refunds, quotes).

## Selected Automation Pilot

**Pilot Choice:** **AI-Assisted Inbox Triage, Grouping & Evidence-Backed Priority Queue (`Shift Triage Workbench`)** with **human-in-the-loop draft approval**.

**Why Choose This Pilot Over Automated WhatsApp Replies:**
- **High leverage, zero customer blast radius:** Consolidating threads, surfacing register discrepancies, and ranking callbacks recovers minutes immediately while keeping **every outgoing message as a draft** (`R11`).
- **Directly solves the single-coordinator bottleneck:** Guarantees the #1 callback (`B101`) surfaces immediately with all evidence (`M01`, `M07`, register status, `09:10` deadline) before `09:10`.

**Assumption That Could Change This Choice:**
- If inbound volume were `< 10` messages per morning and 95%+ arrived in clean English with single-thread booking IDs, a lightweight rules-only spreadsheet filter would suffice and LLM integration would add unnecessary latency. Conversely, if >40% of messages arrive in unstructured Hinglish/voice transcripts or span multiple unlinked messages, AI interpretation becomes the primary bottleneck solver.

## Division of Labour: Rules vs AI vs Coordinator

| Capability | Deterministic Python Rules | AI Model (OpenRouter) | Human Coordinator |
|---|---|---|---|
| Message grouping by `booking_id`/`thread_id` | **Primary** (exact, auditable) | Not needed | Merges edge cases where IDs differ |
| Booking register lookups & refund authority | **Primary** (sole authority) | Must obey register facts | Resolves conflicts (e.g. `B103` Sales claim) |
| Hinglish / negation / intent interpretation | Baseline regex (`v2` fixes known phrases) | **Primary value-add** for novel phrasing & nuance | Overrides misclassified intent |
| Priority tier & deadline enforcement (`R2`) | **Primary** (hard rule tiers) | Suggests urgency only | Can override urgency with logged reason |
| Draft response writing | Safe static templates | **Value-add** for natural, empathetic drafts | **Final approval** before sending |
| Unsupported-promise & channel blocking | **Primary** (`evidence.py` + `R3`) | Instructed in prompt, checked in code | Final check before WhatsApp / call |

## Department Ownership Rules (`R1–R11`)

- **Duty Ops:** Owns active service/care gaps, schedule changes, and unclear existing bookings (`B101`, `B102`, `B104`, `B105`, `M10`). First priority goes to an uncovered current care gap (`B101`). Must respect contact preferences (`M06`/`M12` WhatsApp-only).
- **Sourcing:** Checks availability with helpers (`B101`, `B104`, `B105`). No replacement or revised time can be promised until Sourcing records confirmation; Duty Ops owns the family update.
- **Billing:** Register is the authority for refund approval, amount, and payout date (`B103` under review; `B106` ₹2,000 approved, payout pending). Coordinators may relay confirmed register facts; Billing investigates disputed claims and missing dates.
- **Sales:** Owns new prospect enquiries (`M05`) and prepares quotations. Since no rate card is supplied in this assignment, no price may be quoted.

