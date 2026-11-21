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
| `ai_v1_raw` (`openrouter/free`) | Evaluated (2/8 OK, 6/8 truncated fallback) | **2/8** | **0** | 2/8 | 1/8 | 8/8 | Match (`M01, M07`) | `23,546` tok / `$0.0` / `169.8s` |
| `ai_v1_guarded` (`openrouter/free`) | Evaluated (2/8 OK, 6/8 truncated fallback) | **2/8** | **0** | 2/8 | **2/8** | 8/8 | Match (`M01, M07`) | `23,546` tok / `$0.0` / `169.8s` |

## Case-by-Case Comparison (Supplied Shift)

| Source IDs | Booking | Expected Action & Channel | `rules_v1` | `rules_v2` | `ai_v1_raw` (`openrouter/free`) | `ai_v1_guarded` |
|---|---|---|---|---|---|---|
| `M01, M07` | `B101` | `CARE_GAP_IMMEDIATE` (`phone`, Duty Ops, critical) | PASS | PASS | **PASS** (`particle-1:free`) | **PASS** |
| `M02, M08` | `B102` | `CLOSE_CONFIRMED_ARRIVAL` (`none`, Duty Ops, none) | PASS | PASS | Fail (`incomplete_response` -> `rules_fallback`) | Fail (`rules_fallback`) |
| `M03, M09` | `B103` | `BILLING_VERIFY_DISPUTED_REFUND` (`whatsapp`, Billing, medium) | PASS | PASS | Fail (`incomplete_response` -> `rules_fallback`) | Fail (`rules_fallback`) |
| `M04` | `B104` | `SCHEDULE_CHANGE_SOURCING_CHECK` (`whatsapp`, Duty Ops, medium) | **FAIL (`MANUAL_TRIAGE`)** | **PASS** | Fail (`incomplete_response` -> `rules_fallback`) | Fail (`rules_fallback`) |
| `M05` | `-` | `SALES_ENQUIRY_NO_QUOTE` (`whatsapp`, Sales, low) | PASS | PASS | Fail (`incomplete_response` -> `rules_fallback`) | Fail (`rules_fallback`) |
| `M06, M12` | `B105` | `CARE_GAP_COVERED_CHASE_SOURCING` (`whatsapp`, Duty Ops, high) | PASS | PASS | Fail (`incomplete_response` -> `rules_fallback`) | Fail (`rules_fallback`) |
| `M10` | `-` | `ASK_MINIMUM_BOOKING_IDENTITY` (`whatsapp`, Duty Ops, high) | PASS | PASS | **PASS action, WRONG urgency (`medium`)** (`ernie-5.5-flash`) | **PASS (Guardrail promoted `medium -> high`)** |
| `M11` | `B106` | `RELAY_APPROVED_REFUND_CHASE_PAYOUT` (`whatsapp`, Billing, medium) | PASS | PASS | Fail (`incomplete_response` -> `rules_fallback`) | Fail (`rules_fallback`) |

## Summary Results: Harder Synthetic Set (`n=6`)

| Method / Variant | Status | Correct Next Actions | Unsupported Promises | Dept Routing | Urgency | Grouping | Tokens / Cost / Time |
|---|---|---:|---:|---:|---:|---:|---|
| `rules_v1` (English Keywords) | Evaluated | **5/6** | **0** | 6/6 | 5/6 | 6/6 | - |
| `rules_v2` (+ Hinglish Fix) | Evaluated | **6/6** | **0** | 6/6 | 6/6 | 6/6 | - |
| `ai_v1_raw` (`openrouter/free`) | Evaluated (2/6 OK) | **2/6** | **0** | 2/6 | 2/6 | 6/6 | `17,407` tok / `$0.0` / `85.1s` |
| `ai_v1_guarded` (`openrouter/free`) | Evaluated (2/6 OK) | **2/6** | **0** | 2/6 | 2/6 | 6/6 | `17,407` tok / `$0.0` / `85.1s` |

Notably, on the two completed harder cases, `particle-ai/particle-1:free` correctly handled **Hinglish care gap `H01`** (`"Didi abhi tak nahi aayi... call karo"` -> `CARE_GAP_IMMEDIATE`, `critical`, `phone`, `deadline=09:30`) and **negated closure `H04`** (`"Please don't close this..."` -> `SERVICE_GAP_CHECK_ARRIVAL`, `high`, `whatsapp`).

## Failure Analysis, Disagreements & Single Improvement

1. **Rules Baseline Failure (`rules_v1`):** On `M04` (`B104`: *"Kal cook ko 8 ki jagah 10 baje bhej sakte ho? Please check with her first."*), English keywords missed Hinglish `"ki jagah 10 baje bhej sakte ho"`, scoring `7/8` (`MANUAL_TRIAGE`). On `H01` (`B201`), `rules_v1` missed `"nahi aayi"` and `"call karo"`, scoring `5/6`.
2. **Single Improvement (`rules_v2`):** Added Hinglish schedule-change (`ki jagah`, `baje ... bhej/bulao`), care/service-gap (`nahi aayi`, `abhi tak nahi`), and callback (`call karo`) patterns plus `ki jagah` time extraction (`10:00`) in [`backend/app/modules/rules_classifier.py`](../backend/app/modules/rules_classifier.py).
   - **Before -> After Rerun:** Supplied **`7/8 -> 8/8`** (`+1`); Harder synthetic **`5/6 -> 6/6`** (`+1`); **`0`** unsupported promises across all cases.
3. **AI vs Rules Disagreement (`ISS-07` / `M10`):** `baidu/ernie-5.5-flash-preview:free` correctly identified `ASK_MINIMUM_BOOKING_IDENTITY`, but assigned `suggested_urgency="medium"`. Deterministic priority rules (`R10` + `mentions_today=True`) overrode it to `urgency="high"` in `ai_v1_guarded`.
4. **Provider Failure Observation (`openrouter/free`):** `openrouter/free` routed 6/8 supplied calls and 4/6 harder calls to reasoning models (`ling-3.2-flash`, `nemotron-3-nano`, `flint-v1.0`, `lfm-3-1.7b`, `nemotron-3.5-lightning`) that exhausted `max_tokens=1500` in hidden chain-of-thought before completing JSON (`finish_reason="length"`). Our truncation guard rejected every partial response and routed cleanly to `rules_fallback`, keeping the operational queue `8/8` (`6/6` harder) accurate with `0` unsupported promises.
   - *(Note: Earlier live probes also tested `google/gemini-2.5-flash` -> HTTP `402` key credit cap, and `google/gemma-4-31b-it:free` -> HTTP `429` upstream rate limit, verifying both fallback paths live.)*

## Limitations

- Sample sizes (`n=8` supplied, `n=6` synthetic) are too small for statistical significance claims.
- `openrouter/free` routes dynamically across heterogeneous free models (including reasoning models that consume `max_tokens` heavily); production deployments should pin a funded non-reasoning model or increase `max_tokens` / disable reasoning effort.
