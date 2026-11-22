"""Repository layer decoupling triage business logic from SQLite/PostgreSQL storage."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import sessionmaker

from app.db import DatasetRow, EvaluationRow, LLMCallRow, ReviewRow, RunRow
from app.modules.ingestion import ingest
from app.modules.priority import rank
from app.pipeline import parse_snapshot
from app.schemas import (
    Channel, IngestResult, IssueContext, IssueStatus, LLMCallRecord, ReviewRecord, ReviewRequest, RunResult, Urgency,
)

_CACHE_TTL_S = 60.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TriageRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory
        self._datasets: dict[str, tuple[float, IngestResult, bytes, bytes, str]] = {}
        self._runs_by_id: dict[str, tuple[float, RunResult]] = {}
        self._latest_run: dict[str, tuple[float, RunResult]] = {}
        self._runs_list: dict[tuple[str | None, int], tuple[float, list[dict[str, Any]]]] = {}
        self._reviews: dict[tuple[str | None, str | None], tuple[float, list[ReviewRecord]]] = {}
        self._latest_eval: dict[str, tuple[float, str]] = {}
        self._llm_calls: dict[int, tuple[float, list[LLMCallRecord]]] = {}

    # ---------------------------------------------------------------- datasets
    def save_dataset(self, name: str, bookings_csv: bytes, inbox_csv: bytes, ing: IngestResult) -> None:
        now = _now_iso()
        payload = ing.model_dump_json()
        with self.session_factory() as db:
            row = db.get(DatasetRow, name)
            if row:
                row.bookings_csv = bookings_csv
                row.inbox_csv = inbox_csv
                row.ingest_json = payload
                row.updated_at = now
            else:
                db.add(DatasetRow(name=name, bookings_csv=bookings_csv, inbox_csv=inbox_csv, ingest_json=payload, updated_at=now))
            db.commit()
        self._datasets[name] = (time.monotonic(), ing.model_copy(deep=True), bookings_csv, inbox_csv, now)

    def get_dataset(self, name: str) -> tuple[IngestResult, bytes, bytes, str] | None:
        cached = self._datasets.get(name)
        now_t = time.monotonic()
        if cached and (now_t - cached[0]) < _CACHE_TTL_S:
            return cached[1].model_copy(deep=True), cached[2], cached[3], cached[4]
        with self.session_factory() as db:
            row = db.get(DatasetRow, name)
            if not row:
                return None
            ing = IngestResult.model_validate_json(row.ingest_json)
            self._datasets[name] = (now_t, ing.model_copy(deep=True), row.bookings_csv, row.inbox_csv, row.updated_at)
            return ing, row.bookings_csv, row.inbox_csv, row.updated_at

    def bootstrap_dataset(self, name: str, bookings_csv: bytes, inbox_csv: bytes, snapshot: str, force: bool = False) -> IngestResult:
        existing = None if force else self.get_dataset(name)
        if existing:
            return existing[0]
        ing = ingest(bookings_csv, inbox_csv, parse_snapshot(snapshot))
        self.save_dataset(name, bookings_csv, inbox_csv, ing)
        return ing

    def update_bookings_csv(self, name: str, bookings_csv: bytes, snapshot: str) -> IngestResult:
        existing = self.get_dataset(name)
        if not existing:
            raise ValueError(f"Dataset '{name}' is not initialised")
        _, _, inbox_csv, _ = existing
        ing = ingest(bookings_csv, inbox_csv, parse_snapshot(snapshot))
        self.save_dataset(name, bookings_csv, inbox_csv, ing)
        return ing

    def update_inbox_csv(self, name: str, inbox_csv: bytes, snapshot: str) -> IngestResult:
        existing = self.get_dataset(name)
        if not existing:
            raise ValueError(f"Dataset '{name}' is not initialised")
        _, bookings_csv, _, _ = existing
        ing = ingest(bookings_csv, inbox_csv, parse_snapshot(snapshot))
        self.save_dataset(name, bookings_csv, inbox_csv, ing)
        return ing

    # ---------------------------------------------------------------- runs
    def save_run(self, run: RunResult) -> None:
        payload = run.model_dump_json()
        with self.session_factory() as db:
            row = db.get(RunRow, run.run_id)
            if row:
                row.dataset = run.dataset
                row.mode = run.mode
                row.variant = run.variant
                row.model = run.model
                row.status = run.status
                row.started_at = run.started_at
                row.finished_at = run.finished_at
                row.result_json = payload
            else:
                db.add(RunRow(run_id=run.run_id, dataset=run.dataset, mode=run.mode, variant=run.variant, model=run.model,
                              status=run.status, started_at=run.started_at, finished_at=run.finished_at, result_json=payload))
            for call in run.llm_calls:
                existing_call = db.get(LLMCallRow, call.call_id)
                call_json = call.model_dump_json()
                if not existing_call:
                    db.add(LLMCallRow(
                        call_id=call.call_id, run_id=run.run_id, issue_id=call.issue_id, ok=call.ok, provider=call.provider,
                        model_requested=call.model_requested, model_used=call.model_used, duration_ms=call.duration_ms,
                        attempts=call.attempts, prompt_tokens=call.prompt_tokens, completion_tokens=call.completion_tokens,
                        total_tokens=call.total_tokens, cost_usd=call.cost_usd, error_type=call.error_type,
                        error_message=call.error_message, simulated=call.simulated, payload_json=call_json,
                        created_at=call.started_at,
                    ))
            db.commit()
        now_t = time.monotonic()
        run_copy = run.model_copy(deep=True)
        self._runs_by_id[run.run_id] = (now_t, run_copy)
        self._latest_run[run.dataset] = (now_t, run_copy.model_copy(deep=True))
        self._runs_list.clear()
        if run.llm_calls:
            self._llm_calls.clear()

    def get_run(self, run_id: str) -> RunResult | None:
        cached = self._runs_by_id.get(run_id)
        now_t = time.monotonic()
        if cached and (now_t - cached[0]) < _CACHE_TTL_S:
            return cached[1].model_copy(deep=True)
        with self.session_factory() as db:
            row = db.get(RunRow, run_id)
            if not row:
                return None
            res = RunResult.model_validate_json(row.result_json)
            self._runs_by_id[run_id] = (now_t, res.model_copy(deep=True))
            return res

    def get_latest_run(self, dataset: str = "supplied") -> RunResult | None:
        cached = self._latest_run.get(dataset)
        now_t = time.monotonic()
        if cached and (now_t - cached[0]) < _CACHE_TTL_S:
            return cached[1].model_copy(deep=True)
        with self.session_factory() as db:
            stmt = select(RunRow).where(RunRow.dataset == dataset).order_by(desc(RunRow.finished_at)).limit(1)
            row = db.scalars(stmt).first()
            if not row:
                return None
            res = RunResult.model_validate_json(row.result_json)
            self._latest_run[dataset] = (now_t, res.model_copy(deep=True))
            self._runs_by_id[res.run_id] = (now_t, res.model_copy(deep=True))
            return res

    def list_runs(self, dataset: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        key = (dataset, limit)
        cached = self._runs_list.get(key)
        now_t = time.monotonic()
        if cached and (now_t - cached[0]) < _CACHE_TTL_S:
            return [dict(r) for r in cached[1]]
        with self.session_factory() as db:
            cols = (
                RunRow.run_id, RunRow.dataset, RunRow.mode, RunRow.variant,
                RunRow.model, RunRow.status, RunRow.started_at, RunRow.finished_at,
            )
            stmt = select(*cols).order_by(desc(RunRow.finished_at)).limit(limit)
            if dataset:
                stmt = select(*cols).where(RunRow.dataset == dataset).order_by(desc(RunRow.finished_at)).limit(limit)
            rows = db.execute(stmt).all()
            out = [{
                "run_id": r.run_id, "dataset": r.dataset, "mode": r.mode, "variant": r.variant,
                "model": r.model, "status": r.status, "started_at": r.started_at, "finished_at": r.finished_at,
            } for r in rows]
            self._runs_list[key] = (now_t, [dict(r) for r in out])
            return out

    def last_ai_run_time(self, dataset: str | None = None) -> datetime | None:
        with self.session_factory() as db:
            stmt = select(RunRow).where(RunRow.mode == "ai").order_by(desc(RunRow.finished_at)).limit(1)
            if dataset:
                stmt = select(RunRow).where(RunRow.mode == "ai", RunRow.dataset == dataset).order_by(desc(RunRow.finished_at)).limit(1)
            row = db.scalars(stmt).first()
            if not row:
                return None
            try:
                return datetime.fromisoformat(row.finished_at)
            except ValueError:
                return None

    # ---------------------------------------------------------------- human review
    def apply_review(self, run_id: str, issue_id: str, req: ReviewRequest, snapshot: str) -> tuple[RunResult, ReviewRecord]:
        run = self.get_run(run_id)
        if not run:
            raise KeyError(f"Run {run_id} not found")
        target = next((i for i in run.issues if i.issue_id == issue_id), None)
        if not target:
            raise KeyError(f"Issue {issue_id} not found in run {run_id}")
        f = target.final
        before = {
            "urgency": f.urgency.value,
            "priority_rank": f.priority_rank,
            "department": f.responsible_department.value,
            "action_code": f.action_code.value,
            "next_action": f.next_action,
            "status": f.status.value,
            "contact_channel": f.contact_channel.value,
            "draft_response": f.draft_response,
            "human_review_required": f.human_review_required,
            "missing_information": list(f.missing_information),
        }
        note_tag = f"[{req.reviewer}]"
        if req.action == "approve":
            f.human_review_required = False
            f.human_review_reasons = [r for r in f.human_review_reasons if not r.startswith("Approved by ")]
            f.human_review_reasons.append(f"Approved by {req.reviewer}" + (f": {req.reason}" if req.reason else ""))
        elif req.action == "change_priority":
            if req.urgency is None:
                raise ValueError("urgency is required for change_priority")
            f.urgency = req.urgency
            f.human_review_required = False
        elif req.action == "change_department":
            if req.department is None:
                raise ValueError("department is required for change_department")
            f.responsible_department = req.department
        elif req.action == "correct_action":
            if req.action_code is None and not req.next_action:
                raise ValueError("action_code or next_action is required for correct_action")
            if req.action_code is not None:
                f.action_code = req.action_code
            if req.next_action:
                f.next_action = req.next_action
            f.human_review_required = False
        elif req.action == "edit_draft":
            if req.draft_response is None:
                raise ValueError("draft_response is required for edit_draft")
            f.draft_response = req.draft_response
            f.hold_contact_reason = None
        elif req.action == "request_info":
            if not req.info_requested:
                raise ValueError("info_requested is required for request_info")
            entry = f"{note_tag} Info requested: {req.info_requested}"
            if entry not in f.missing_information:
                f.missing_information.append(entry)
            f.status = IssueStatus.AWAITING_INFO
            f.human_review_required = True
        elif req.action == "resolve":
            f.status = IssueStatus.RESOLVED
            f.contact_channel = Channel.NONE
            f.hold_contact_reason = req.reason or f"Resolved by {req.reviewer}."
            f.human_review_required = False
        elif req.action == "reopen":
            f.status = IssueStatus.OPEN
            f.hold_contact_reason = None
            f.human_review_required = True
        f.source = "human"
        if req.reason and req.action != "approve":
            f.explanation = f"{f.explanation} | Human review ({req.action} by {req.reviewer}): {req.reason}".strip(" |")

        created_at = _now_iso()
        with self.session_factory() as db:
            # Collect existing priority overrides for this run, plus this one if change_priority.
            existing_rows = db.scalars(
                select(ReviewRow).where(ReviewRow.run_id == run_id, ReviewRow.action == "change_priority").order_by(ReviewRow.review_id)
            ).all()
            urgency_overrides: dict[str, Urgency] = {}
            for er in existing_rows:
                try:
                    pl = json.loads(er.payload_json)
                    if pl.get("urgency"):
                        urgency_overrides[er.issue_id] = Urgency(pl["urgency"])
                except (ValueError, KeyError):
                    pass
            if req.action == "change_priority" and req.urgency is not None:
                urgency_overrides[issue_id] = req.urgency
            elif req.action in ("resolve", "reopen") and issue_id in urgency_overrides:
                # Re-evaluating status clears stale manual urgency overrides on that issue unless re-applied.
                urgency_overrides.pop(issue_id, None)

            pairs = [
                (iss.final, IssueContext(group=iss.group, messages=iss.messages, booking=iss.booking))
                for iss in run.issues
            ]
            rank(pairs, parse_snapshot(snapshot), urgency_overrides=urgency_overrides)
            run.issues.sort(key=lambda i: i.final.priority_rank or 99)

            run_row = db.get(RunRow, run_id)
            if run_row:
                run_row.result_json = run.model_dump_json()

            rev_row = ReviewRow(
                run_id=run_id, issue_id=issue_id, action=req.action, reviewer=req.reviewer, reason=req.reason,
                payload_json=req.model_dump_json(), before_json=json.dumps(before), created_at=created_at,
            )
            db.add(rev_row)
            db.commit()
            db.refresh(rev_row)
            record = ReviewRecord(
                review_id=rev_row.review_id, issue_id=issue_id, run_id=run_id, created_at=created_at,
                before=before, **req.model_dump(),
            )
            now_t = time.monotonic()
            self._runs_by_id[run_id] = (now_t, run.model_copy(deep=True))
            latest_cached = self._latest_run.get(run.dataset)
            if latest_cached and latest_cached[1].run_id == run_id:
                self._latest_run[run.dataset] = (now_t, run.model_copy(deep=True))
            self._reviews.clear()
            return run, record

    def list_reviews(self, run_id: str | None = None, issue_id: str | None = None) -> list[ReviewRecord]:
        key = (run_id, issue_id)
        cached = self._reviews.get(key)
        now_t = time.monotonic()
        if cached and (now_t - cached[0]) < _CACHE_TTL_S:
            return [r.model_copy(deep=True) for r in cached[1]]
        with self.session_factory() as db:
            stmt = select(ReviewRow).order_by(desc(ReviewRow.review_id))
            if run_id and issue_id:
                stmt = select(ReviewRow).where(ReviewRow.run_id == run_id, ReviewRow.issue_id == issue_id).order_by(desc(ReviewRow.review_id))
            elif run_id:
                stmt = select(ReviewRow).where(ReviewRow.run_id == run_id).order_by(desc(ReviewRow.review_id))
            elif issue_id:
                stmt = select(ReviewRow).where(ReviewRow.issue_id == issue_id).order_by(desc(ReviewRow.review_id))
            rows = db.scalars(stmt).all()
            out: list[ReviewRecord] = []
            for r in rows:
                payload = json.loads(r.payload_json)
                before = json.loads(r.before_json)
                out.append(ReviewRecord(
                    review_id=r.review_id, issue_id=r.issue_id, run_id=r.run_id, created_at=r.created_at,
                    before=before, **payload,
                ))
            self._reviews[key] = (now_t, [r.model_copy(deep=True) for r in out])
            return out

    # ---------------------------------------------------------------- evaluations & llm calls
    def save_evaluation(self, eval_id: str, dataset: str, report_json: str, created_at: str) -> None:
        with self.session_factory() as db:
            row = db.get(EvaluationRow, eval_id)
            if row:
                row.report_json = report_json
                row.created_at = created_at
            else:
                db.add(EvaluationRow(eval_id=eval_id, dataset=dataset, created_at=created_at, report_json=report_json))
            db.commit()
        self._latest_eval[dataset] = (time.monotonic(), report_json)

    def get_latest_evaluation_json(self, dataset: str = "supplied") -> str | None:
        cached = self._latest_eval.get(dataset)
        now_t = time.monotonic()
        if cached and (now_t - cached[0]) < _CACHE_TTL_S:
            return cached[1]
        with self.session_factory() as db:
            stmt = select(EvaluationRow).where(EvaluationRow.dataset == dataset).order_by(desc(EvaluationRow.created_at)).limit(1)
            row = db.scalars(stmt).first()
            if not row:
                return None
            self._latest_eval[dataset] = (now_t, row.report_json)
            return row.report_json

    def list_llm_calls(self, limit: int = 50) -> list[LLMCallRecord]:
        cached = self._llm_calls.get(limit)
        now_t = time.monotonic()
        if cached and (now_t - cached[0]) < _CACHE_TTL_S:
            return [c.model_copy(deep=True) for c in cached[1]]
        with self.session_factory() as db:
            rows = db.scalars(select(LLMCallRow).order_by(desc(LLMCallRow.created_at)).limit(limit)).all()
            out = [LLMCallRecord.model_validate_json(r.payload_json) for r in rows]
            self._llm_calls[limit] = (now_t, [c.model_copy(deep=True) for c in out])
            return out

