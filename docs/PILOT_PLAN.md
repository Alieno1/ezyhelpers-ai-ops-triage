# One-Week Operations Triage Pilot Plan

## Pilot Governance

| Item | Specification |
|---|---|
| **Duration** | 5–7 morning shifts (Monday–Sunday, 09:00–11:00 IST peak triage window) |
| **Pilot Owner** | Duty Ops Lead (Bengaluru morning shift) |
| **Human Review Responsibility** | Assigned Duty Ops Coordinator reviews every issue flagged `human_review_required=True` and approves/edits every draft before manual send |
| **Baseline (Pre-Pilot)** | Unassisted coordinator reading raw WhatsApp threads, Sales notes, and `booking_register.csv` manually in arrival order |
| **Primary Success Measures** | 1. First callback (`#1`) identified in `< 2 minutes` from 09:00.<br>2. `0` unsupported promises (unconfirmed ETA, replacement, refund approval, or quote) sent to customers.<br>3. `>= 90%` coordinator acceptance rate on queue rank and department routing without rework. |

## Explicit Pause Conditions (Stop & Revert to Manual)

Pause the AI-assisted pilot immediately and revert to manual/rules-only triage if **any** of the following occur:
1. Any customer receives an unsupported promise or is called despite an explicit `"don't call"` preference.
2. Any uncovered elder/child care gap is ranked below non-urgent enquiries or billing items.
3. OpenRouter error/timeout fallback rate exceeds `25%` across two consecutive shifts, or coordinator correction rate exceeds `30%`.

## Estimated Time Savings Per Shift (Transparent Assumptions)

*(All time figures are operational assumptions for a 12-message / 8-issue morning batch — not measured production telemetry.)*

| Step | Manual Baseline (Assumed) | Assisted Workflow (Assumed) | Basis / Assumption |
|---|---|---|---|
| Reading & grouping 12 msgs across threads + register lookup | ~1.5 min/msg = **18.0 min** | **0.2 min** (automated) | Automated CSV ingest + grouping + deterministic rules (`< 1s`); ~12s UI load/open |
| Drafting & double-checking policy/promises | ~1.0 min/issue × 8 = **8.0 min** | **0.0 min** (drafted) | Draft templates or AI drafts pre-checked by `evidence.py` |
| Coordinator human verification, edits & overrides | Included above | ~0.75 min/issue × 8 = **6.0 min** | Quick scan of timeline, register panel, and 1-click approve/edit |
| **Total Coordinator Time** | **26.0 min / shift** | **6.2 min / shift** | **Net Saved: ~19.8 minutes per 12-message shift (~76% prep reduction)** |

> **Attribution Breakdown (Workflow / `rules_v2` vs. LLM Layer):**
> - **Manual → Deterministic `rules_v2` workbench (~75–85% of total saving):** Automated grouping, booking register matching, priority ranking, missing-fact surfacing, and policy-safe templates deliver the bulk of the `~19.8 min` shift reduction in `< 1s` at `$0.00`.
> - **Deterministic `rules_v2` → Guarded AI layer (currently unmeasured):** On known benchmark patterns (`n=8` supplied, `n=6` harder), `rules_v2` already scores `8/8` and `6/6`, so AI adds `~0 min` there. Incremental LLM savings in live operations are expected strictly on long-tail `MANUAL_TRIAGE` vernacular/multi-intent tickets and faster editing of nuanced reply drafts.

## Measuring Incremental AI Time Savings (`Rules-Only` vs. `Rules + Guarded AI`)

To replace assumptions with measured shift telemetry and isolate how much time the AI layer itself saves beyond `rules_v2`, run a **7-day alternating/split-shift A/B comparison** during the pilot:

- **Arm A (`Rules-Only`):** `rules_v2` classification, deterministic priority queue, and rule-enforced holding templates.
- **Arm B (`Rules-First + Async Guarded AI`):** Immediate `rules_v2` queue render (`< 1s`), with a fast non-reasoning model (e.g., `google/gemini-2.5-flash`) invoked asynchronously for `MANUAL_TRIAGE`, mixed-language/ambiguous threads, and contextual draft replies behind `evidence.py` / `guard_ai`.

Log four timestamps/counters per issue directly in the review workbench:

| Metric | Definition | What It Isolates |
|---|---|---|
| `time_to_first_callback_sec` | `09:00` shift open → `#1` urgent call initiated | Verifies AI async execution adds zero delay to urgent callback dispatch |
| `handle_time_per_issue_sec` | Issue card opened → coordinator `Approve` / `Edit` / `Override` | Direct wall-clock comparison between Arm A and Arm B |
| `manual_triage_rate` | `%` of incoming issues dropped to `MANUAL_TRIAGE` by `rules_v2` vs. resolved cleanly by AI | Quantifies real-world vernacular/edge-case volume outside regex coverage |
| `draft_edit_distance` & `override_rate` | Characters edited in draft + `%` priority/dept/action overrides | Separates drafting time saved from coordinator review/correction overhead |

**Pilot Go / No-Go Decision Rule for AI:** Keep AI enabled in the production **Rules-First, AI-on-Exception** path only if Arm B yields a measurable net saving of **`>= 15–20 seconds` per complex/`MANUAL_TRIAGE` issue** (after review overhead) with **`0` unsupported promises**. Otherwise, stay on deterministic `rules_v2` only and avoid unnecessary LLM latency or operational complexity.

## Estimated Model Cost Per 100 Cases (Transparent Pricing Assumptions)

*(Assumptions using `google/gemini-2.5-flash` placeholder pricing from `.env.example`: `$0.30 / 1M` input tokens, `$2.50 / 1M` output tokens. Actual OpenRouter billing replaces these once executed with a live key.)*

- **Measured Average Input Size:** Our redacted user payload + `SYSTEM_PROMPT_V1` (`~750` prompt words + `~200` JSON words per issue) averages **~1,250 input tokens/issue** (`125,000` input tokens per 100 cases).
- **Expected Structured JSON Output:** `AITriageOutput` averages **~300 output tokens/issue** (`30,000` output tokens per 100 cases).
- **Calculation:**
  - Input cost: `(125,000 / 1,000,000) × $0.30 = $0.0375`
  - Output cost: `(30,000 / 1,000,000) × $2.50 = $0.0750`
  - **Estimated Total Cost per 100 Cases:** **`~$0.1125 USD` (~₹9.50–₹10 INR)** (excluding occasional repair retries, adding `< 10%`).

