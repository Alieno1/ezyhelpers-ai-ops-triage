# Testing Report

## Automated Test Suite Execution

Executed via `backend/.venv/bin/pytest -v` after all backend code edits:
- **Result:** **20 passed, 0 failed, 0 skipped** in **2.25s** (`Python 3.14.4`, `pytest 9.2.0`).

## Coverage by Module & Edge Case

| Test File | Tests | Key Scenarios Verified |
|---|---:|---|
| `tests/test_ingestion_and_dq.py` | 4 | Supplied CSVs UTF-8 BOM handling; `B103`/`B106` closed missing-start vs active warning; `M10` missing booking ID warning; missing columns; empty files; unparseable timestamps; duplicate `booking_id` & `event_id`; out-of-order chronology; orphan references; raw value preservation; Latin-1 fallback encoding. |
| `tests/test_grouping_and_matching.py` | 3 | Supplied 12 messages -> 8 distinct issues; Sales handoff `M07` merged into `B101` (`T01` + `S11`); `M10` HSR locality candidates (`B101`, `B104`) NOT auto-linked; chronological re-sorting; same-thread conflicting `booking_id` split. |
| `tests/test_rules_and_priority.py` | 3 | `B101` ranked `#1` (`CARE_GAP_IMMEDIATE`, `phone`, `09:10`); `B105` ranked `#2` (`WhatsApp` only); `B103` disputed refund vs `B106` ₹2,000 approved; `B104` Hinglish `v2` schedule change; `B102` arrival closure; `M05` no-quote Sales enquiry; `M10` awaiting info; harder synthetic `H04` negated closure & `H06` critical WhatsApp-only; all 5 promise-detector categories. |
| `tests/test_llm_and_fallback.py` | 6 | `[PHONE]`/`[EMAIL]` PII redaction; guardrails overriding bad AI department (`Sales->Billing`), `"don't call"` channel, unconfirmed refund approval & payout date, and fake source IDs; malformed JSON repair retry; schema-failure fallback; missing key fallback; timeout retry exhaustion; `429` `Retry-After`; `404` immediate fallback; `400` `json_schema -> json_object` downgrade (`httpx.MockTransport`, `simulated=True`); failed-AI `0/n` evaluation scoring check. |
| `tests/test_api_and_evaluation.py` | 4 | `/health`, `/api/overview`, `/api/model/status` (verifying `OPENROUTER_API_KEY` never leaks), `404` on `/private_submission/...`; `rules_v1` (`7/8`) -> `rules_v2` (`8/8`) supplied & (`5/6` -> `6/6`) harder evaluation; multi-step human review persistence & priority re-ranking; `/api/processing/ai` fallback without key; upload `413` size limit & `400` bad CSV; CSV/XLSX/MD/JSON export verification. |

## Live End-to-End Integration Verification

- **Frontend Build (`npm run build`):** Compiled all 7 Next.js routes (`/`, `/queue`, `/issues/[issueId]`, `/review`, `/evaluation`, `/data-quality`, `/exports`) with zero TypeScript or ESLint errors.
- **Live HTTP Verification:** All FastAPI API endpoints (including `/api/exports/issues-report?format=json`, `/api/model/status`, CSV/XLSX/MD downloads) and all 7 frontend pages returned HTTP `200`; `/private_submission/...` returned HTTP `404` on both servers.
- **Live OpenRouter Runs:** Verified live HTTP error handling on `402` (`google/gemini-2.5-flash`), `429` (`google/gemma-4-31b-it:free`), `length`-truncation fallback (`openrouter/free`), and real completions on `particle-ai/particle-1:free` and `baidu/ernie-5.5-flash-preview:free` (`30` real calls persisted in SQLite `llm_calls`).

## Known Testing Gaps

- Automated browser E2E scripts (Playwright/Cypress) were not created; frontend UI routes were verified via `next build` and live HTTP checks against the running backend.
