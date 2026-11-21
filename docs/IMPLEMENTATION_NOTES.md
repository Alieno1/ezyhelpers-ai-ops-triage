# Implementation Notes

## Key Design & Architectural Decisions

1. **Deterministic Guardrails Wrap Every Model Call:** Rather than letting an LLM set final department ownership, action codes, refund approvals, or priority rank directly, the model outputs structured `Signals` + a candidate draft (`AITriageOutput`), and pure Python (`business_rules.py`, `evidence.py`, `priority.py`) enforces `R1`–`R11`. Even on live `openrouter/free`, deterministic guardrails upgraded `ISS-07` (`M10`) from `medium` to `high` urgency.
2. **Tiered Priority Over Pure Numeric Scoring:** Hard business tiers (`CRITICAL > HIGH > MEDIUM > LOW > NONE`) govern ranking first, with minute-level deadlines and arrival timestamps acting strictly as intra-tier tie-breakers.
3. **Immutable Evidence vs Mutable Final Decision:** Each `IssueResult` preserves `rules`, `ai_raw`, `ai_guarded`, and `final` separately, while `reviews` stores full `before_json` snapshots. Re-ranking on `change_priority` reconstructs all active coordinator urgency overrides from the audit log so subsequent draft edits never accidentally overwrite an earlier priority escalation.
4. **Real-World OpenRouter Failure & Fallback Validation:** Live runs against OpenRouter demonstrated why resilient engineering matters:
   - `google/gemini-2.5-flash` hit a key credit cap (`402`).
   - `google/gemma-4-31b-it:free` hit upstream rate limits (`429`).
   - `openrouter/free` succeeded on `particle-ai/particle-1:free` and `baidu/ernie-5.5-flash-preview:free` (`2/8` supplied, `2/6` harder) while truncating on free reasoning models at `max_tokens=1500` (`finish_reason="length"`), triggering `rules_fallback` without losing queue accuracy (`8/8` final).
   - Testing also caught and fixed two real bugs: `datetime` JSON serialization (`model_dump(mode="json")`) in `/api/exports/issues-report?format=json`, and failed AI evaluations previously falling back to `rules` scores instead of scoring `0/n`.

## Trade-Offs

- **SQLite Default + Repository Pattern:** SQLite (`triage.db`) enables zero-config local execution while `TriageRepository` + `normalize_db_url()` makes switching to managed PostgreSQL (Neon / Render) a single `DATABASE_URL` env change.
- **Regex Promise Detection:** `evidence.py` uses conservative sentence-level negation checks rather than another LLM judge — fast, deterministic, and zero-cost, paired with mandatory human draft approval (`R11`).

## Development Time & Scope

- **Actual Implementation Effort:** Built, tested, and verified end-to-end across modular backend (`16` Python modules + CLI), `20` pytest tests, `7`-page Next.js Light/Dark dashboard, `10` documentation files, and ReportLab/OpenPyXL private deliverables within ~4 hours of focused work.
- **Deployment Readiness:** Configured for GitHub + Neon Postgres + Render (`render.yaml`) + Vercel (`.vercelignore`, `frontend/.vercelignore`), with `private_submission/`, `backend/.env`, `backend/triage.db`, and all `*.pdf` files strictly excluded from Git.
