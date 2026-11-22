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
| `ai_v1_raw` (`openrouter/free`, `max_tokens=3500`) | Evaluated (7/8 OK, 1/8 truncated fallback) | **7/8** | **0** | 7/8 | **4/8** | 8/8 | Match (`M01, M07`) | `30,520` tok / `$0.0` / `155.8s` |
| `ai_v1_guarded` (`openrouter/free`, `max_tokens=3500`) | Evaluated (7/8 OK, 1/8 truncated fallback) | **7/8** | **0** | 7/8 | **7/8** | 8/8 | Match (`M01, M07`) | `30,520` tok / `$0.0` / `155.8s` |

## Case-by-Case Comparison (Supplied Shift)

| Source IDs | Booking | Expected Action & Channel | `rules_v1` | `rules_v2` | `ai_v1_raw` (`openrouter/free`) | `ai_v1_guarded` |
|---|---|---|---|---|---|---|
| `M01, M07` | `B101` | `CARE_GAP_IMMEDIATE` (`phone`, Duty Ops, critical) | PASS | PASS | **PASS** (`nemotron-3.5-lightning`) — omitted missing caregiver status | **PASS** |
| `M02, M08` | `B102` | `CLOSE_CONFIRMED_ARRIVAL` (`none`, Duty Ops, none) | PASS | PASS | **PASS** (`nemotron-3.5-lightning`) | **PASS** |
| `M03, M09` | `B103` | `BILLING_VERIFY_DISPUTED_REFUND` (`whatsapp`, Billing, medium) | PASS | PASS | **PASS** (`particle-1:free`) | **PASS** |
| `M04` | `B104` | `SCHEDULE_CHANGE_SOURCING_CHECK` (`whatsapp`, Duty Ops, medium) | **FAIL (`MANUAL_TRIAGE`)** | **PASS** | **PASS action, WRONG urgency (`low`)** (`nemotron-3-nano`) | **PASS (Guardrail promoted `low -> medium`)** |
| `M05` | `-` | `SALES_ENQUIRY_NO_QUOTE` (`whatsapp`, Sales, low) | PASS | PASS | **PASS** (`nemotron-3-nano`) — omitted missing rate card | **PASS** |
| `M06, M12` | `B105` | `CARE_GAP_COVERED_CHASE_SOURCING` (`whatsapp`, Duty Ops, high) | PASS | PASS | Fail (`incomplete_response` on `flint-v1.0:free` -> `rules_fallback`) | Fail (`rules_fallback`) |
| `M10` | `-` | `ASK_MINIMUM_BOOKING_IDENTITY` (`whatsapp`, Duty Ops, high) | PASS | PASS | **PASS action, WRONG urgency (`low`)** (`nemotron-3.5-lightning`) | **PASS (Guardrail promoted `low -> high`)** |
| `M11` | `B106` | `RELAY_APPROVED_REFUND_CHASE_PAYOUT` (`whatsapp`, Billing, medium) | PASS | PASS | **PASS action, WRONG urgency (`none`)** (`nemotron-3-nano`) | **PASS (Guardrail promoted `none -> medium`)** |

## Summary Results: Harder Synthetic Set (`n=6`)

| Method / Variant | Status | Correct Next Actions | Unsupported Promises | Dept Routing | Urgency | Grouping | Tokens / Cost / Time |
|---|---|---:|---:|---:|---:|---:|---|
| `rules_v1` (English Keywords) | Evaluated | **5/6** | **0** | 6/6 | 5/6 | 6/6 | - |
| `rules_v2` (+ Hinglish Fix) | Evaluated | **6/6** | **0** | 6/6 | 6/6 | 6/6 | - |
| `ai_v1_raw` (`openrouter/free`, `max_tokens=3500`) | Evaluated (4/6 OK, 2/6 truncated) | **4/6** | **1** (`H02` R4 violation) | 4/6 | 3/6 | 6/6 | `24,376` tok / `$0.0` / `191.9s` |
| `ai_v1_guarded` (`openrouter/free`, `max_tokens=3500`) | Evaluated (4/6 OK, 2/6 truncated) | **4/6** | **0** (promise blocked) | 4/6 | **4/6** | 6/6 | `24,376` tok / `$0.0` / `191.9s` |

Notably, on the completed harder cases:
- `nvidia/nemotron-3.5-lightning:free` correctly handled **Hinglish care gap `H01`** (`"Didi abhi tak nahi aayi... call karo"` -> `CARE_GAP_IMMEDIATE`, `critical`, `phone`, `deadline=09:30`), and `nvidia/nemotron-3-ultra-550b-a55b:free` handled **critical WhatsApp-only child care gap `H06`** (`whatsapp`, respecting `"don't call"`).
- On **`H02` (`B204`)**, raw model output included a time statement caught by our unsupported-promise detector (`revised_time` R4 violation) and wrong urgency (`low`); **`ai_v1_guarded` suppressed the unsupported promise (`1 -> 0`) and promoted urgency (`low -> medium`)**.

## Failure Analysis, Disagreements & Iterations

1. **Iteration 1 — Rules Hinglish Improvement (`rules_v1 -> rules_v2`):**
   - `rules_v1` failed on `M04` (`B104`: *"Kal cook ko 8 ki jagah 10 baje bhej sakte ho?"*) returning `MANUAL_TRIAGE` (`7/8`), and on synthetic `H01` (`B201`: *"Didi abhi tak nahi aayi... call karo"*) returning `MANUAL_TRIAGE` (`5/6`).
   - Added Hinglish schedule-change (`ki jagah`, `baje ... bhej/bulao`), gap (`nahi aayi`, `abhi tak nahi`), and callback (`call karo`) patterns + `requested_change` parsing (`10:00`) in [`backend/app/modules/rules_classifier.py`](../backend/app/modules/rules_classifier.py).
   - **Result:** Supplied **`7/8 -> 8/8`** (`+1`); Harder **`5/6 -> 6/6`** (`+1`); **`0`** unsupported promises.
2. **Iteration 2 — LLM Token Budget & Guardrail Rescue (`max_tokens: 1500 -> 3500`):**
   - With `max_tokens=1500`, `openrouter/free` reasoning models truncated on `6/8` supplied calls (`2/8` completed, `23,546` tok) and `4/6` harder calls (`2/6` completed, `17,407` tok).
   - Raising `max_tokens` to `3500` in [`backend/app/modules/llm_client.py`](../backend/app/modules/llm_client.py) lifted live completion on Render to **`7/8`** supplied (`30,520` tok, `155.8s`, `$0.0`) and **`4/6`** harder (`24,376` tok, `191.9s`, `$0.0`), leaving only `recursive/flint-v1.0:free` truncations safely handled by `rules_fallback` (keeping final operational queues `8/8` and `6/6`).
   - Live OpenRouter calls proved why guardrails are essential: `ai_v1_guarded` fixed **3 raw urgency errors (`4/8 -> 7/8`)** on supplied (`M04`, `M10`, `M11`), fixed **1 unsupported revised-time promise (`1 -> 0`)** + 1 urgency error on harder (`H02`), and filled missing-info checks (`5/8 -> 7/8` supplied, `0/6 -> 4/6` harder).

## Incremental Time-Saving Analysis: Rules vs. AI Layer

A critical operational question is how much coordinator time the **AI (LLM) layer itself** saves beyond deterministic software and `rules_v2`:

- **Where the ~19.8 min shift saving actually comes from:** Most of the estimated time reduction against manual triage (~75–85% of the `26.0 min -> 6.2 min` shift assumption in [`docs/PILOT_PLAN.md`](PILOT_PLAN.md)) comes from **deterministic engineering**—automated CSV ingestion, thread/booking grouping, booking register reconciliation, priority ranking, missing-fact surfacing, and rule-enforced holding templates—rather than the LLM.
- **Measured finding on the current benchmarks (`n=8` supplied, `n=6` harder):** Deterministic `rules_v2` already achieves **`8/8`** on the supplied shift and **`6/6`** on the harder set in **`< 1s`** at **`$0.00`**. On known, structured patterns, the LLM layer saves **`~0` minutes** today—and calling sequential free-tier reasoning models via `openrouter/free` (`155.8s` supplied / `191.9s` harder) would *add* wait time if a coordinator had to block on it synchronously.
- **Where the AI layer is expected to save incremental time in production (hypothesis to test):**
  1. **Unstructured / long-tail `MANUAL_TRIAGE` avoidance:** Live Bengaluru WhatsApp shifts include unseen Hinglish, Kannada-English transliteration, voice-to-text typos, and multi-intent messages outside pre-written regex patterns. Left to rules alone, those tickets drop to `MANUAL_TRIAGE` (~2–4 minutes each for a human to read, reconcile, and reply from scratch). At higher daily volumes (100+ messages/day), if rules cover ~75–80% of traffic, AI helps recover time on the remaining **20–25% long-tail exceptions** without ongoing regex maintenance.
  2. **Faster contextual reply drafting on nuanced cases:** While safe templates cover standard cases, a fast non-reasoning model (e.g., `google/gemini-2.5-flash`, `~1–2s` parallel/async) can pre-draft natural, context-specific replies for complex situations—backed by `evidence.py` promise blocking so coordinators spend less time rewriting drafts and do not lose time fixing unsafe AI claims.
- **Recommended production pattern (`Rules-First, AI-on-Exception`):** Render the deterministic `rules_v2` queue immediately (`< 1s`) so the first callback is never delayed; invoke the guarded LLM **asynchronously** only on `MANUAL_TRIAGE` tickets, mixed-language/ambiguous threads, or nuanced reply drafts.
- **How we close this open question:** Execute the controlled **`Rules-Only` (`rules_v2` + templates) vs. `Rules + Guarded AI` (async fast non-reasoning model)** split defined in [`docs/PILOT_PLAN.md`](PILOT_PLAN.md). Keep the AI layer enabled on those exception/drafting paths only if measured net handle-time savings exceed **`~15–20s` per complex ticket** after accounting for coordinator review/override overhead; otherwise operate rules-only.

## Limitations

- Sample sizes (`n=8` supplied, `n=6` synthetic) are too small for statistical significance claims.
- `openrouter/free` routes dynamically across heterogeneous free models (including heavy reasoning models such as `recursive/flint-v1.0:free`); production deployments should pin a funded non-reasoning model.
- Coordinator handle time per issue—and therefore the exact incremental minutes saved by the AI layer itself over `rules_v2`—has not yet been measured on live shifts and is targeted for direct instrumentation in the 1-week pilot ([`docs/PILOT_PLAN.md`](PILOT_PLAN.md)).
