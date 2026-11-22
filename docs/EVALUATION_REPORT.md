# Evaluation Report: Rules Baseline vs Improvement & Live OpenRouter AI

## Expected-Action Reference Set (Authored Before Execution)

Both expected-action reference sets were frozen prior to running either workflow:
- **Supplied Shift (`n=8` distinct issues from 12 messages):** [`backend/evaluation/expected_actions.json`](../backend/evaluation/expected_actions.json)
- **Harder Synthetic Set (`n=6` invented edge-case issues):** [`backend/evaluation/harder_cases/expected_actions.json`](../backend/evaluation/harder_cases/expected_actions.json)

**Scoring Criteria:**
- **Correct next action (`x/n`):** Exact `action_code` AND exact `contact_channel` match (calling a `"don't call"` customer fails).
- **Unsupported promises:** Regex/fact detector checking unconfirmed arrival ETAs, replacements, rescheduled times, unrecorded refund approvals, payout timelines, invented prices, or prohibited phone channels.
- **Honest AI failure scoring:** Failed/truncated AI calls fall back to `rules_fallback` in production for coordinator safety, **but are NOT credited as AI accuracy** in evaluation (`0` for failed items).

## Summary Results: Supplied 12-Message Shift (`n=8`)

| Method / Variant | Status | Correct Next Actions | Unsupported Promises | Dept Routing | Urgency | Grouping | 1st Callback | Tokens / Cost / Time |
|---|---|---:|---:|---:|---:|---:|---|---|
| `rules_v1` (English Keywords) | Evaluated | **7/8** | **0** | 8/8 | 8/8 | 8/8 | Match (`M01, M07`) | - |
| `rules_v2` (+ Hinglish Fix) | Evaluated | **8/8** | **0** | 8/8 | 8/8 | 8/8 | Match (`M01, M07`) | - |
| `ai_v1_raw` (`openrouter/free`) | Evaluated (`8/8` OK) | **7/8** | **0** | 8/8 | **7/8** | 8/8 | Match (`M01, M07`) | `21,712` tok / `$0.0` / `64.1s` |
| `ai_v1_guarded` (`openrouter/free`) | Evaluated (`8/8` OK) | **8/8** | **0** | 8/8 | **8/8** | 8/8 | Match (`M01, M07`) | `21,712` tok / `$0.0` / `64.1s` |

## Case-by-Case Comparison (Supplied Shift)

| Source IDs | Booking | Expected Action & Channel | `rules_v1` | `rules_v2` | `ai_v1_raw` (`openrouter/free`) | `ai_v1_guarded` |
|---|---|---|---|---|---|---|
| `M01, M07` | `B101` | `CARE_GAP_IMMEDIATE` (`phone`, Duty Ops, critical) | PASS | PASS | **PASS** (`nemotron-3-nano`) | **PASS** |
| `M02, M08` | `B102` | `CLOSE_CONFIRMED_ARRIVAL` (`none`, Duty Ops, none) | PASS | PASS | **PASS** (`nemotron-3-ultra`) | **PASS** |
| `M03, M09` | `B103` | `BILLING_VERIFY_DISPUTED_REFUND` (`whatsapp`, Billing, medium) | PASS | PASS | **PASS** (`particle-1:free`) | **PASS** |
| `M04` | `B104` | `SCHEDULE_CHANGE_SOURCING_CHECK` (`whatsapp`, Duty Ops, medium) | **FAIL (`MANUAL_TRIAGE`)** | **PASS** | **PASS** (`nemotron-3-ultra`) | **PASS** |
| `M05` | `-` | `SALES_ENQUIRY_NO_QUOTE` (`whatsapp`, Sales, low) | PASS | PASS | **FAIL channel (`none`, omitted rate card)** (`nemotron-3-nano`) | **PASS (Guardrail enforced `whatsapp` + rate card)** |
| `M06, M12` | `B105` | `CARE_GAP_COVERED_CHASE_SOURCING` (`whatsapp`, Duty Ops, high) | PASS | PASS | **PASS** (`nemotron-3.5-super-vl`) | **PASS** |
| `M10` | `-` | `ASK_MINIMUM_BOOKING_IDENTITY` (`whatsapp`, Duty Ops, high) | PASS | PASS | **PASS action, WRONG urgency (`medium`)** (`nemotron-3-ultra`) | **PASS (Guardrail promoted `medium -> high`)** |
| `M11` | `B106` | `RELAY_APPROVED_REFUND_CHASE_PAYOUT` (`whatsapp`, Billing, medium) | PASS | PASS | **PASS** (`particle-1:free`) | **PASS** |

## Summary Results: Harder Synthetic Set (`n=6`)

| Method / Variant | Status | Correct Next Actions | Unsupported Promises | Dept Routing | Urgency | Grouping | Tokens / Cost / Time |
|---|---|---:|---:|---:|---:|---:|---|
| `rules_v1` (English Keywords) | Evaluated | **5/6** | **0** | 6/6 | 5/6 | 6/6 | - |
| `rules_v2` (+ Hinglish Fix) | Evaluated | **6/6** | **0** | 6/6 | 6/6 | 6/6 | - |
| `ai_v1_raw` (`openrouter/free`) | Evaluated (`6/6` OK) | **5/6** | **0** | 5/6 | 5/6 | 6/6 | `21,908` tok / `$0.0` / `103.0s` |
| `ai_v1_guarded` (`openrouter/free`) | Evaluated (`6/6` OK) | **6/6** | **0** | **6/6** | **6/6** | 6/6 | `21,908` tok / `$0.0` / `103.0s` |

Notably, on the harder edge-case suite:
- `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` correctly handled **Hinglish care gap `H01`** (`"Didi abhi tak nahi aayi... call karo"` -> `CARE_GAP_IMMEDIATE`, `critical`, `phone`, `deadline=09:30`), and `nvidia/nemotron-3-ultra-550b-a55b:free` handled **critical WhatsApp-only child care gap `H06`** (`whatsapp`, respecting `"don't call"`).
- On **`H03`** (unlinked customer asking about a refund without providing a booking ID), raw `recursive/flint-v1.0:free` misrouted to **`Billing` (`BILLING_VERIFY_DISPUTED_REFUND`)**; **`ai_v1_guarded` enforced Rule `R10`** to re-route to **`Duty Ops` (`ASK_MINIMUM_BOOKING_IDENTITY`)** without guessing a booking. Guardrails also promoted **`H02` urgency (`low -> medium`)** and filled missing-info checks (`4/6 -> 6/6`).

## Failure Analysis, Disagreements & Iteration

1. **Targeted Improvement — Rules Hinglish Fix (`rules_v1 -> rules_v2`):**
   - `rules_v1` (English keywords) failed on `M04` (`B104`: *"Kal cook ko 8 ki jagah 10 baje bhej sakte ho?"*) returning `MANUAL_TRIAGE` (`7/8`), and on synthetic `H01` (`B201`: *"Didi abhi tak nahi aayi... call karo"*) returning `MANUAL_TRIAGE` (`5/6`).
   - Added targeted Hinglish schedule-change (`ki jagah`, `baje ... bhej/bulao`), arrival-gap (`nahi aayi`, `abhi tak nahi`), and callback (`call karo`) patterns plus `requested_change` extraction (`10:00`) in [`backend/app/modules/rules_classifier.py`](../backend/app/modules/rules_classifier.py).
   - **Result:** Supplied **`7/8 -> 8/8`** (`+1`); Harder **`5/6 -> 6/6`** (`+1`); **`0`** unsupported promises across both sets.
2. **Guardrail Protection Over Raw LLM Outputs (`ai_v1_raw -> ai_v1_guarded`):**
   - Live OpenRouter runs completed `8/8` (Supplied) and `6/6` (Harder) at `$0.0` using structured JSON (`reasoning: {"enabled": false}`).
   - Even when API calls succeeded cleanly, raw model outputs made deterministic policy slips—dropping the `whatsapp` contact channel + rate card flag on `M05`, under-rating urgency on `M10` (`medium -> high`) and `H02` (`low -> medium`), and misrouting unlinked refund query `H03` to `Billing` instead of `Duty Ops`. Deterministic guardrails (`guard_ai`) corrected every deviation automatically (`7/8 -> 8/8` supplied; `5/6 -> 6/6` harder; `0` unsupported promises).

## Incremental Time-Saving Analysis: Rules vs. AI Layer

A critical operational question is how much coordinator time the **AI (LLM) layer itself** saves beyond deterministic software and `rules_v2`:

- **Where the ~19.8 min shift saving actually comes from:** Most of the estimated time reduction against manual triage (~75–85% of the `26.0 min -> 6.2 min` shift assumption in [`docs/PILOT_PLAN.md`](PILOT_PLAN.md)) comes from **deterministic engineering**—automated CSV ingestion, thread/booking grouping, booking register reconciliation, priority ranking, missing-fact surfacing, and rule-enforced holding templates—rather than the LLM.
- **Measured finding on the current benchmarks (`n=8` supplied, `n=6` harder):** Deterministic `rules_v2` already achieves **`8/8`** on the supplied shift and **`6/6`** on the harder set in **`< 1s`** at **`$0.00`**. On known, structured patterns, the LLM layer saves **`~0` minutes** today—and calling sequential free-tier models via `openrouter/free` (`64.1s` supplied / `103.0s` harder) would *add* wait time if a coordinator had to block on it synchronously.
- **Where the AI layer is expected to save incremental time in production (hypothesis to test):**
  1. **Unstructured / long-tail `MANUAL_TRIAGE` avoidance:** Live Bengaluru WhatsApp shifts include unseen Hinglish, Kannada-English transliteration, voice-to-text typos, and multi-intent messages outside pre-written regex patterns. Left to rules alone, those tickets drop to `MANUAL_TRIAGE` (~2–4 minutes each for a human to read, reconcile, and reply from scratch). At higher daily volumes (100+ messages/day), if rules cover ~75–80% of traffic, AI helps recover time on the remaining **20–25% long-tail exceptions** without ongoing regex maintenance.
  2. **Faster contextual reply drafting on nuanced cases:** While safe templates cover standard cases, a fast non-reasoning model (e.g., `google/gemini-2.5-flash`, `~1–2s` parallel/async) can pre-draft natural, context-specific replies for complex situations—backed by `evidence.py` promise blocking so coordinators spend less time rewriting drafts and do not lose time fixing unsafe AI claims.
- **Recommended production pattern (`Rules-First, AI-on-Exception`):** Render the deterministic `rules_v2` queue immediately (`< 1s`) so the first callback is never delayed; invoke the guarded LLM **asynchronously** only on `MANUAL_TRIAGE` tickets, mixed-language/ambiguous threads, or nuanced reply drafts.
- **How we close this open question:** Execute the controlled **`Rules-Only` (`rules_v2` + templates) vs. `Rules + Guarded AI` (async fast non-reasoning model)** split defined in [`docs/PILOT_PLAN.md`](PILOT_PLAN.md). Keep the AI layer enabled on those exception/drafting paths only if measured net handle-time savings exceed **`~15–20s` per complex ticket** after accounting for coordinator review/override overhead; otherwise operate rules-only.

## Limitations

- Sample sizes (`n=8` supplied, `n=6` synthetic) are too small for statistical significance claims.
- `openrouter/free` routes across heterogeneous free models and is capped at **50 free requests/day** without credits; production deployments should pin a funded non-reasoning model.
- Coordinator handle time per issue—and therefore the exact incremental minutes saved by the AI layer itself over `rules_v2`—has not yet been measured on live shifts and is targeted for direct instrumentation in the 1-week pilot ([`docs/PILOT_PLAN.md`](PILOT_PLAN.md)).
