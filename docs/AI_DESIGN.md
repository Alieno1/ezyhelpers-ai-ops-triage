# AI Design & OpenRouter Integration

## Gateway & Model Selection

- **Gateway:** OpenRouter Chat Completions API (`https://openrouter.ai/api/v1/chat/completions`), implemented in [`backend/app/modules/llm_client.py`](../backend/app/modules/llm_client.py).
- **Configured Model Identifier:** `openrouter/free` (configurable via `OPENROUTER_MODEL`; tested also against `google/gemini-2.5-flash` and `google/gemma-4-31b-it:free`).
- **Selection Rationale:** `openrouter/free` provides zero-cost (`$0.00`) routing across free OpenRouter models supporting structured `json_schema` / `json_object` responses, allowing real end-to-end verification without billing exhaustion. For production shifts, a dedicated low-latency non-reasoning model such as `google/gemini-2.5-flash` is recommended to avoid upstream free-tier rate limits and reasoning-token truncation.
- **Credential Isolation:** `OPENROUTER_API_KEY` is read exclusively in `backend/app/config.py` and never serialized in `/api/model/status` or frontend bundles.

## Live OpenRouter Execution Findings (Actual Measured Runs)

Three live OpenRouter configurations were tested during verification (zero results fabricated):

1. **`google/gemini-2.5-flash`:** Returned HTTP `402 insufficient_credits` (*"requested up to 1500 tokens, but can only afford 314"*); all 8 calls logged and fell back cleanly to `rules_fallback`.
2. **`google/gemma-4-31b-it:free`:** Returned HTTP `429 rate_limited` (*"temporarily rate-limited upstream"*); all 8 calls retried within policy, logged, and fell back to `rules_fallback`.
3. **`openrouter/free` (Active Configured Model — `reasoning: {"enabled": false}`, `max_tokens=3500`):**
   - Because structured triage JSON requires `~280–350` output tokens rather than verbose chain-of-thought reasoning, [`backend/app/modules/llm_client.py`](../backend/app/modules/llm_client.py) passes `"reasoning": {"enabled": false}` by default (with automatic router retry on HTTP `400` and a single truncation retry on `finish_reason == "length"`):
   - **Supplied Shift (`n=8`):** **`8/8`** API calls succeeded end-to-end across free models (`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`, `nvidia/nemotron-3-ultra-550b-a55b:free`, `particle-ai/particle-1:free`, `nvidia/nemotron-3.5-super-vl:free`). Raw AI scored `7/8` (missing `whatsapp` channel + rate card on `M05` and setting `medium` urgency on `M10`); deterministic guardrails (`ai_v1_guarded`) corrected all deviations to **`8/8`** across actions, department, urgency, and missing info with **`0` unsupported promises** and `#1` callback match (`M01, M07`).
     - **Total Tokens:** `21,712` | **Total Duration:** `64,108 ms` | **Actual Cost:** `$0.00`
   - **Harder Synthetic Set (`n=6`):** **`6/6`** API calls succeeded (`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`, `recursive/flint-v1.0:free`, `nvidia/nemotron-3.5-lightning:free`, `nvidia/nemotron-3-ultra-550b-a55b:free`). Raw AI scored `5/6` (misrouting unlinked `H03` to `Billing` instead of asking for booking identity via `Duty Ops`, and setting `H02` urgency to `low`); deterministic guardrails (`ai_v1_guarded`) enforced `R10` and urgency rules to reach **`6/6`** across all dimensions with **`0` unsupported promises**.
     - **Total Tokens:** `21,908` | **Total Duration:** `102,978 ms` | **Actual Cost:** `$0.00`

## System Prompt (`SYSTEM_PROMPT_V1` / `SYSTEM_PROMPT_V2`)

Located in [`backend/app/modules/ai_triage.py`](../backend/app/modules/ai_triage.py):
- Supplies rules `R1`–`R11` explicitly.
- Designates `booking_register_row` as the sole authority for arrivals, substitutes, refunds, amounts, and payout dates.
- Instructs the model to interpret English, Hindi, and Hinglish (including negations), avoid guessing bookings from locality alone, keep drafts to 2–4 plain English sentences, and return strict JSON matching `AITriageOutput`.
- `SYSTEM_PROMPT_V2` adds explicit Hinglish schedule/gap guidance and negated-closure warnings.

## Actual Redacted Request Input & Raw Model Output (`ISS-01` / `B101`)

### Redacted User Payload Sent (`build_user_payload`)

```json
{
  "snapshot_now_ist": "2026-11-23 09:00",
  "issue_id": "ISS-01",
  "messages_in_this_issue": [
    {
      "id": "M01",
      "received_at_ist": "2026-11-23 08:17",
      "thread": "T01",
      "booking_ref_given": "B101",
      "channel": "WhatsApp",
      "sender_role": "Customer",
      "text": "Dad’s caregiver was due at 8. Nobody has come. I leave for work at 9:10 and Dad will be alone. Please call me."
    },
    {
      "id": "M07",
      "received_at_ist": "2026-11-23 08:41",
      "thread": "S11",
      "booking_ref_given": "B101",
      "channel": "Sales handoff",
      "sender_role": "Sales",
      "text": "Forwarding a callback request from B101. Missed 8 am elder support. Family member leaves at 9:10."
    }
  ],
  "booking_register_row": {
    "booking_id": "B101",
    "service": "Elder companionship",
    "locality": "HSR Layout",
    "scheduled_start_ist": "2026-11-23 08:00",
    "register_updated_at_ist": "2026-11-22 18:10",
    "operations_record": "Regular caregiver assigned. Arrival unconfirmed.",
    "billing_record": null
  },
  "booking_match_note": "Exact booking_id match to register row 2.",
  "grouping_note": "M01: first message of a new issue; M07: internal handoff in thread S11 references the same booking B101"
}
```

### Actual Raw Output Returned by OpenRouter (`nvidia/nemotron-3.5-lightning:free`, `3,499` tokens, `9,894 ms`, `$0.0`)

```json
{
  "issue_category": "care_gap",
  "customer_intent": "Request immediate caregiver cover and a call",
  "resolved_by_customer": false,
  "cover_available": "no",
  "cover_until": "09:10",
  "deadline": "09:10",
  "contact_preference": "phone",
  "contact_channel": "phone",
  "refund_claimed_approved": false,
  "mentions_today": true,
  "requested_change": null,
  "suggested_urgency": "critical",
  "suggested_department": "Duty Ops",
  "recommended_action_code": "CARE_GAP_IMMEDIATE",
  "recommended_next_action": "Contact Sourcing to find an immediate replacement caregiver and inform the customer via phone",
  "missing_information": ["Whether any family member is currently covering the elder"],
  "draft_response": "We understand Dad's caregiver hasn't arrived yet and you need to leave at 9:10. We are sourcing an immediate replacement and will call you shortly – please keep your phone handy.",
  "hold_contact_reason": null,
  "explanation": "The booking B101 is for elder companionship scheduled to start at 08:00. The register shows arrival unconfirmed, and the customer reports nobody has come. With the customer leaving at 09:10 and Dad at risk of being alone, this is a critical care gap. The customer explicitly asked to be called, so contact preference is phone. Immediate sourcing is required per CARE_GAP_IMMEDIATE.",
  "supporting_source_ids": ["M01", "M07", "B101"],
  "confidence": 0.92
}
```

## Schema Validation, Guardrails & Hallucination Prevention

1. **Structured Output + Repair:** Requests `response_format: { type: "json_schema", strict: true }` (automatically downgrades once to `json_object` on HTTP 400). Validates against `AITriageOutput` via Pydantic v2; invalid JSON or schema violations trigger **one** repair prompt before falling back to `rules_fallback`.
2. **Hard Rule Re-Derivation (`guard_ai`):** Even after valid JSON returns, deterministic Python (`enforce_signal_constraints`, `decide_action`, `decide_channel`, `DEPARTMENT_BY_CATEGORY`) overrides any conflicting AI action, department, urgency, closure, booking link, or `"don't call"` channel violation (`R1`–`R11`). For example, on `ISS-07` (`M10`), `baidu/ernie-5.5-flash-preview:free` suggested `"medium"` urgency while deterministic priority logic promoted it to `"high"` because the customer asked about `"today"`.
3. **Unsupported-Promise Detector (`evidence.py`):** Scans AI `draft_response` for unconfirmed arrival ETAs, replacement confirmations, rescheduled start times, unrecorded refund approvals, payout timelines, or invented rupee amounts.
4. **Source ID Verification:** Drops any `supporting_source_ids` not present in the issue's message or booking IDs.

## Error Handling & Rerun Instructions

- **Timeouts / Network / 429 Rate Limits:** Exponential backoff (`max_retries=2`), honours `Retry-After` up to 10s.
- **401/402/403/404 / Truncated `length` / Missing Key:** Fail-safe `LLMCallRecord` persisted in DB (`ok=False`) + transparent fallback to `rules_fallback`.
- **Rerun with any model:**
  ```bash
  cd backend
  OPENROUTER_MODEL="google/gemini-2.5-flash" .venv/bin/python -m app.cli evaluate --dataset supplied --include-ai
  ```

## Pricing Assumptions (For Estimation Only)

`openrouter/free` returned `actual_cost_usd = $0.0`. For production paid-tier estimation (`docs/PILOT_PLAN.md`), `.env.example` provides configurable placeholder rates (`$0.30 / 1M` input tokens, `$2.50 / 1M` output tokens for `google/gemini-2.5-flash` reference pricing, clearly labelled as assumptions).
