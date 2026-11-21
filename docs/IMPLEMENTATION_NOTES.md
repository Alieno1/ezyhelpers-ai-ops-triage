# Implementation Notes

## Key Design & Architectural Decisions

1. **Deterministic Guardrails Wrap Every Model Call:** Rather than letting an LLM set final department ownership, action codes, refund approvals, or priority rank directly, the model outputs structured `Signals` + a candidate draft (`AITriageOutput`), and pure Python (`business_rules.py`, `evidence.py`, `priority.py`) enforces `R1`–`R11`. On live `openrouter/free` runs (`max_tokens=3500`), guardrails rescued 3 urgency errors (`4/8 -> 7/8`) on the supplied shift and caught/blocked a live unsupported `revised_time` promise (`R4`) on harder case `H02` (`1 -> 0` promises).
2. **Tiered Priority Over Pure Numeric Scoring:** Hard business tiers (`CRITICAL > HIGH > MEDIUM > LOW > NONE`) govern ranking first, with minute-level deadlines and arrival timestamps acting strictly as intra-tier tie-breakers.
3. **Immutable Evidence vs Mutable Final Decision:** Each `IssueResult` preserves `rules`, `ai_raw`, `ai_guarded`, and `final` separately, while `reviews` stores full `before_json` snapshots. Re-ranking on `change_priority` reconstructs all active coordinator urgency overrides from the audit log so subsequent draft edits never accidentally overwrite an earlier priority escalation.
4. **Real-World OpenRouter Failure & Fallback Validation:** Live runs against OpenRouter demonstrated why resilient engineering matters:
   - `google/gemini-2.5-flash` hit a key credit cap (`402`).
   - `google/gemma-4-31b-it:free` hit upstream rate limits (`429`).
   - `openrouter/free` initially completed `2/8` supplied (`2/6` harder) at `max_tokens=1500` due to free reasoning-model truncation; raising `max_tokens=3500` lifted live completion to **`7/8`** supplied (`30,520` tokens, `$0.00`) and **`4/6`** harder (`24,376` tokens, `$0.00`), while `rules_fallback` cleanly covered remaining `incomplete_response` calls (`8/8` and `6/6` final queues).
   - Testing also caught and fixed two real bugs: `datetime` JSON serialization (`model_dump(mode="json")`) in `/api/exports/issues-report?format=json`, and failed AI evaluations previously falling back to `rules` scores instead of scoring `0/n`.

## Trade-Offs

- **SQLite Default + Repository Pattern:** SQLite (`triage.db`) enables zero-config local execution while `TriageRepository` + `normalize_db_url()` makes switching to managed PostgreSQL (Neon / Render) a single `DATABASE_URL` env change.
- **Regex Promise Detection:** `evidence.py` uses conservative sentence-level negation checks rather than another LLM judge — fast, deterministic, and zero-cost, paired with mandatory human draft approval (`R11`).

## Development Time & Scope

- **Actual Implementation Effort:** Built, tested, and verified end-to-end across modular backend (`16` Python modules + CLI), `20` pytest tests, `7`-page Next.js Light/Dark dashboard, `10` documentation files, and ReportLab/OpenPyXL private deliverables within ~4 hours of focused work.
- **Deployment Readiness:** Configured for GitHub + Neon Postgres + Render (`render.yaml`) + Vercel (`.vercelignore`, `frontend/.vercelignore`), with `private_submission/`, `backend/.env`, `backend/triage.db`, and all `*.pdf` files strictly excluded from Git.
