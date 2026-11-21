"""FastAPI backend for the EzyHelpers AI Operations Triage System."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from app.config import BACKEND_DIR, Settings, get_settings
from app.db import init_db
from app.modules.evaluation import EvaluationReport, run_full_evaluation, run_full_evaluation_with_run
from app.modules.exports import (
    evaluation_to_csv_bytes,
    evaluation_to_xlsx_bytes,
    issues_report_markdown,
    queue_to_csv_bytes,
    queue_to_xlsx_bytes,
)
from app.modules.ingestion import IngestionError
from app.modules.llm_client import OpenRouterClient
from app.modules.priority import first_callback
from app.pipeline import parse_snapshot, run_ai, run_rules
from app.repository import TriageRepository
from app.schemas import URGENCY_ORDER, IssueContext, IssueResult, ReviewRequest, RunResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("triage.api")


def _dataset_paths(settings: Settings, dataset: str) -> tuple[Path, Path, Path]:
    if dataset == "harder":
        d = settings.evaluation_dir / "harder_cases"
        return d / "booking_register.csv", d / "shift_inbox.csv", d / "expected_actions.json"
    b = settings.data_dir / "booking_register.csv"
    i = settings.data_dir / "shift_inbox.csv"
    if not b.exists() or not i.exists():
        b = BACKEND_DIR / "data" / "booking_register.csv"
        i = BACKEND_DIR / "data" / "shift_inbox.csv"
    return b, i, settings.evaluation_dir / "expected_actions.json"


def _make_client(settings: Settings) -> OpenRouterClient:
    return OpenRouterClient(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
        base_url=settings.openrouter_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        temperature=settings.llm_temperature,
    )


def _ensure_dataset_and_run(repo: TriageRepository, settings: Settings, dataset: str) -> tuple[Any, RunResult]:
    ds = repo.get_dataset(dataset)
    if ds is None:
        b_path, i_path, _ = _dataset_paths(settings, dataset)
        if not b_path.exists() or not i_path.exists():
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset}' source files not found")
        ing = repo.bootstrap_dataset(dataset, b_path.read_bytes(), i_path.read_bytes(), settings.snapshot_time_ist)
    else:
        ing = ds[0]
    run = repo.get_latest_run(dataset)
    if run is None:
        run = run_rules(ing, settings.snapshot_time_ist, version="v2", dataset=dataset)
        repo.save_run(run)
    return ing, run


def create_app(custom_settings: Settings | None = None) -> FastAPI:
    settings = custom_settings or get_settings()
    engine, session_factory = init_db(settings.database_url)
    repo = TriageRepository(session_factory)

    def bootstrap_all() -> None:
        for ds_name in ("supplied", "harder"):
            b_path, i_path, exp_path = _dataset_paths(settings, ds_name)
            if b_path.exists() and i_path.exists():
                ing = repo.bootstrap_dataset(ds_name, b_path.read_bytes(), i_path.read_bytes(), settings.snapshot_time_ist)
                if repo.get_latest_run(ds_name) is None:
                    run = run_rules(ing, settings.snapshot_time_ist, version="v2", dataset=ds_name)
                    repo.save_run(run)
                if exp_path.exists() and repo.get_latest_evaluation_json(ds_name) is None:
                    rep = run_full_evaluation(ing, settings.snapshot_time_ist, ds_name, exp_path, client=_make_client(settings), include_ai=False)
                    repo.save_evaluation(rep.eval_id, ds_name, rep.model_dump_json(), rep.evaluated_at)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        bootstrap_all()
        yield

    app = FastAPI(
        title="EzyHelpers AI Operations Triage API",
        version="1.0.0",
        description="Modular, evidence-backed operations triage backend for EzyHelpers Bengaluru duty desk.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.repo = repo
    app.state.engine = engine

    # Ensure DB is seeded even when TestClient is constructed without entering lifespan.
    bootstrap_all()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        t0 = time.monotonic()
        response = await call_next(request)
        ms = int((time.monotonic() - t0) * 1000)
        log.info("%s %s -> %s (%dms)", request.method, request.url.path, response.status_code, ms)
        return response

    @app.exception_handler(IngestionError)
    async def handle_ingestion_error(_req: Request, exc: IngestionError):
        return JSONResponse(status_code=400, content={"detail": str(exc), "error_type": "ingestion_error"})

    @app.get("/health")
    def health() -> dict[str, Any]:
        db_ok = False
        db_backend = "postgresql" if not settings.database_url.startswith("sqlite") else "sqlite"
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception as exc:
            log.error("Database health check failed: %s", exc)
        latest = repo.get_latest_run("supplied")
        return {
            "status": "ok" if db_ok else "degraded",
            "database": {"backend": db_backend, "connected": db_ok},
            "openrouter": {
                "configured": settings.llm_configured,
                "model": settings.openrouter_model,
                "base_url": settings.openrouter_base_url,
                "allow_live_ai": settings.allow_live_ai,
            },
            "snapshot_time_ist": settings.snapshot_time_ist,
            "active_supplied_run_id": latest.run_id if latest else None,
        }

    @app.get("/api/overview")
    def overview(dataset: str = Query("supplied", pattern="^(supplied|harder)$")) -> dict[str, Any]:
        ing, run = _ensure_dataset_and_run(repo, settings, dataset)
        reviews = repo.list_reviews(run_id=run.run_id)
        issues = run.issues
        pairs = [(i.final, IssueContext(group=i.group, messages=i.messages, booking=i.booking)) for i in issues]
        fc = first_callback(pairs)
        fc_payload = None
        if fc:
            fc_rec, fc_ctx = fc
            second = next((i for i in issues if i.issue_id != fc_ctx.group.issue_id and i.final.status.value != "resolved"), None)
            why_first = fc_rec.priority_reason
            if second:
                why_first += (
                    f" Ranked ahead of #{second.final.priority_rank} {second.issue_id} "
                    f"({second.group.booking_id or 'Unlinked'}, {second.final.urgency.value}): {second.final.priority_reason}"
                )
            fc_payload = {
                "issue_id": fc_ctx.group.issue_id,
                "booking_id": fc_ctx.group.booking_id,
                "priority_rank": fc_rec.priority_rank,
                "urgency": fc_rec.urgency.value,
                "department": fc_rec.responsible_department.value,
                "channel": fc_rec.contact_channel.value,
                "action_code": fc_rec.action_code.value,
                "next_action": fc_rec.next_action,
                "source_message_ids": fc_ctx.group.source_message_ids,
                "deadline": fc_rec.deadline,
                "why_first": why_first,
                "draft_response": fc_rec.draft_response,
            }

        urg_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "none": 0}
        dept_counts: dict[str, int] = {"Duty Ops": 0, "Sourcing": 0, "Billing": 0, "Sales": 0}
        status_counts: dict[str, int] = {"open": 0, "awaiting_info": 0, "resolved": 0}
        for i in issues:
            u = i.final.urgency.value
            urg_counts[u] = urg_counts.get(u, 0) + 1
            d = i.final.responsible_department.value
            dept_counts[d] = dept_counts.get(d, 0) + 1
            st = i.final.status.value
            status_counts[st] = status_counts.get(st, 0) + 1

        return {
            "dataset": dataset,
            "snapshot_time_ist": settings.snapshot_time_ist,
            "run_id": run.run_id,
            "mode": run.mode,
            "variant": run.variant,
            "run_status": run.status,
            "model": run.model,
            "openrouter_configured": settings.llm_configured,
            "notes": run.notes,
            "metrics": {
                "total_messages": len(ing.messages),
                "total_bookings": len(ing.bookings),
                "distinct_issues": len(issues),
                "urgent_cases": sum(1 for i in issues if i.final.urgency.value in ("critical", "high") and i.final.status.value != "resolved"),
                "critical_cases": urg_counts["critical"],
                "high_cases": urg_counts["high"],
                "open_issues": sum(1 for i in issues if i.final.status.value != "resolved"),
                "resolved_issues": status_counts["resolved"],
                "human_review_cases": sum(1 for i in issues if i.final.human_review_required),
                "data_quality_issues": len(ing.dq_issues),
                "dq_warnings_errors": sum(1 for d in ing.dq_issues if d.severity in ("warning", "error")),
                "human_reviews_logged": len(reviews),
            },
            "first_callback": fc_payload,
            "urgency_breakdown": [{"urgency": k, "count": v} for k, v in urg_counts.items()],
            "department_breakdown": [{"department": k, "count": v} for k, v in dept_counts.items()],
            "status_breakdown": [{"status": k, "count": v} for k, v in status_counts.items()],
            "recent_runs": repo.list_runs(dataset=dataset, limit=5),
        }

    async def _read_upload(file: UploadFile) -> bytes:
        name = (file.filename or "").lower()
        if name and not name.endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only .csv files are accepted.")
        raw = await file.read()
        if len(raw) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_bytes} byte upload limit.")
        if not raw.strip():
            raise HTTPException(status_code=400, detail="Uploaded CSV file is empty.")
        return raw

    @app.post("/api/data/upload/bookings")
    async def upload_bookings(
        file: UploadFile = File(...),
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
    ) -> dict[str, Any]:
        _ensure_dataset_and_run(repo, settings, dataset)
        raw = await _read_upload(file)
        ing = repo.update_bookings_csv(dataset, raw, settings.snapshot_time_ist)
        run = run_rules(ing, settings.snapshot_time_ist, version="v2", dataset=dataset)
        repo.save_run(run)
        return {
            "dataset": dataset,
            "filename": file.filename,
            "bookings_count": len(ing.bookings),
            "messages_count": len(ing.messages),
            "dq_issues_count": len(ing.dq_issues),
            "run_id": run.run_id,
        }

    @app.post("/api/data/upload/inbox")
    async def upload_inbox(
        file: UploadFile = File(...),
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
    ) -> dict[str, Any]:
        _ensure_dataset_and_run(repo, settings, dataset)
        raw = await _read_upload(file)
        ing = repo.update_inbox_csv(dataset, raw, settings.snapshot_time_ist)
        run = run_rules(ing, settings.snapshot_time_ist, version="v2", dataset=dataset)
        repo.save_run(run)
        return {
            "dataset": dataset,
            "filename": file.filename,
            "bookings_count": len(ing.bookings),
            "messages_count": len(ing.messages),
            "dq_issues_count": len(ing.dq_issues),
            "run_id": run.run_id,
        }

    @app.post("/api/data/reset")
    def reset_dataset(dataset: str = Query("supplied", pattern="^(supplied|harder)$")) -> dict[str, Any]:
        b_path, i_path, exp_path = _dataset_paths(settings, dataset)
        ing = repo.bootstrap_dataset(dataset, b_path.read_bytes(), i_path.read_bytes(), settings.snapshot_time_ist, force=True)
        run = run_rules(ing, settings.snapshot_time_ist, version="v2", dataset=dataset)
        repo.save_run(run)
        if exp_path.exists():
            rep = run_full_evaluation(ing, settings.snapshot_time_ist, dataset, exp_path, client=_make_client(settings), include_ai=False)
            repo.save_evaluation(rep.eval_id, dataset, rep.model_dump_json(), rep.evaluated_at)
        return {"dataset": dataset, "status": "reset", "run_id": run.run_id, "distinct_issues": len(run.issues)}

    @app.get("/api/data/quality-report")
    def quality_report(dataset: str = Query("supplied", pattern="^(supplied|harder)$")) -> dict[str, Any]:
        ing, _ = _ensure_dataset_and_run(repo, settings, dataset)
        _, _, _, updated_at = repo.get_dataset(dataset) or (None, b"", b"", "")
        issues = ing.dq_issues
        return {
            "dataset": dataset,
            "updated_at": updated_at,
            "files": ing.files,
            "summary": {
                "total": len(issues),
                "error": sum(1 for d in issues if d.severity == "error"),
                "warning": sum(1 for d in issues if d.severity == "warning"),
                "info": sum(1 for d in issues if d.severity == "info"),
                "human_review_required": sum(1 for d in issues if d.human_review_required),
            },
            "issues": [d.model_dump() for d in issues],
        }

    @app.post("/api/processing/rules", response_model=RunResult)
    def process_rules(
        version: Literal["v1", "v2"] = Query("v2"),
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
    ) -> RunResult:
        ing, _ = _ensure_dataset_and_run(repo, settings, dataset)
        run = run_rules(ing, settings.snapshot_time_ist, version=version, dataset=dataset)
        repo.save_run(run)
        return run

    @app.post("/api/processing/ai", response_model=RunResult)
    def process_ai(
        prompt_version: Literal["v1", "v2"] = Query("v1"),
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
    ) -> RunResult:
        if not settings.allow_live_ai:
            raise HTTPException(status_code=403, detail="Live AI calls are disabled (ALLOW_LIVE_AI=false).")
        ing, _ = _ensure_dataset_and_run(repo, settings, dataset)
        if settings.llm_configured and settings.ai_run_cooldown_seconds > 0:
            last = repo.last_ai_run_time(dataset)
            if last:
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                if elapsed < settings.ai_run_cooldown_seconds:
                    wait = int(settings.ai_run_cooldown_seconds - elapsed)
                    raise HTTPException(status_code=429, detail=f"AI run cooldown active; wait {wait}s before re-running OpenRouter.")
        client = _make_client(settings)
        run = run_ai(ing, settings.snapshot_time_ist, client, prompt_version=prompt_version, dataset=dataset, rules_version="v2")
        repo.save_run(run)
        return run

    @app.post("/api/processing/evaluate", response_model=EvaluationReport)
    def process_evaluate(
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
        include_ai: bool = Query(False),
        ai_prompt_version: Literal["v1", "v2"] = Query("v1"),
    ) -> EvaluationReport:
        ing, run = _ensure_dataset_and_run(repo, settings, dataset)
        _, _, exp_path = _dataset_paths(settings, dataset)
        if not exp_path.exists():
            raise HTTPException(status_code=404, detail=f"Expected actions file missing for '{dataset}'")
        reviews = repo.list_reviews(run_id=run.run_id)
        rep, ai_run = run_full_evaluation_with_run(
            ing, settings.snapshot_time_ist, dataset, exp_path,
            client=_make_client(settings), include_ai=include_ai and settings.allow_live_ai,
            human_corrections_count=len(reviews), ai_prompt_version=ai_prompt_version,
        )
        if ai_run is not None:
            repo.save_run(ai_run)
        repo.save_evaluation(rep.eval_id, dataset, rep.model_dump_json(), rep.evaluated_at)
        return rep

    @app.post("/api/processing/rerun", response_model=RunResult)
    def rerun(
        mode: Literal["rules", "ai"] = Query("rules"),
        variant: Literal["v1", "v2"] = Query("v2"),
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
    ) -> RunResult:
        if mode == "ai":
            return process_ai(prompt_version=variant, dataset=dataset)
        return process_rules(version=variant, dataset=dataset)

    @app.get("/api/evaluation/latest", response_model=EvaluationReport)
    def latest_evaluation(dataset: str = Query("supplied", pattern="^(supplied|harder)$")) -> EvaluationReport:
        raw = repo.get_latest_evaluation_json(dataset)
        if raw:
            return EvaluationReport.model_validate_json(raw)
        return process_evaluate(dataset=dataset, include_ai=False, ai_prompt_version="v1")

    @app.get("/api/issues")
    def list_issues(
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
        department: str | None = Query(None),
        urgency: str | None = Query(None),
        status: str | None = Query(None),
        human_review_required: bool | None = Query(None),
        search: str | None = Query(None),
        sort_by: Literal["priority_rank", "urgency", "issue_id", "department"] = Query("priority_rank"),
        sort_dir: Literal["asc", "desc"] = Query("asc"),
    ) -> dict[str, Any]:
        _, run = _ensure_dataset_and_run(repo, settings, dataset)
        filtered = list(run.issues)
        if department:
            filtered = [i for i in filtered if i.final.responsible_department.value.lower() == department.lower()]
        if urgency:
            filtered = [i for i in filtered if i.final.urgency.value.lower() == urgency.lower()]
        if status:
            filtered = [i for i in filtered if i.final.status.value.lower() == status.lower()]
        if human_review_required is not None:
            filtered = [i for i in filtered if i.final.human_review_required is human_review_required]
        if search:
            q = search.strip().lower()
            filtered = [
                i for i in filtered
                if q in i.issue_id.lower()
                or (i.group.booking_id and q in i.group.booking_id.lower())
                or any(q in mid.lower() for mid in i.group.source_message_ids)
                or q in i.final.next_action.lower()
                or any(q in m.text_normalised for m in i.messages)
            ]

        def _sort_key(iss: IssueResult):
            if sort_by == "urgency":
                return (URGENCY_ORDER[iss.final.urgency], iss.final.priority_rank or 99)
            if sort_by == "issue_id":
                return (iss.issue_id,)
            if sort_by == "department":
                return (iss.final.responsible_department.value, iss.final.priority_rank or 99)
            return (iss.final.priority_rank or 99,)

        filtered.sort(key=_sort_key, reverse=(sort_dir == "desc"))
        return {
            "run_id": run.run_id,
            "dataset": run.dataset,
            "mode": run.mode,
            "variant": run.variant,
            "status": run.status,
            "model": run.model,
            "notes": run.notes,
            "total": len(run.issues),
            "filtered": len(filtered),
            "issues": [i.model_dump() for i in filtered],
        }

    @app.get("/api/issues/{issue_id}")
    def get_issue(
        issue_id: str,
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
        run_id: str | None = Query(None),
    ) -> dict[str, Any]:
        ing, active_run = _ensure_dataset_and_run(repo, settings, dataset)
        run = repo.get_run(run_id) if run_id else active_run
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        iss = next((i for i in run.issues if i.issue_id == issue_id), None)
        if not iss:
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
        reviews = repo.list_reviews(run_id=run.run_id, issue_id=issue_id)
        rel_ids = set(iss.group.source_message_ids) | ({iss.group.booking_id} if iss.group.booking_id else set())
        dq_related = [d.model_dump() for d in ing.dq_issues if d.record_id in rel_ids]
        return {
            "run_id": run.run_id,
            "dataset": run.dataset,
            "mode": run.mode,
            "variant": run.variant,
            "issue": iss.model_dump(),
            "reviews": [r.model_dump() for r in reviews],
            "dq_related": dq_related,
        }

    @app.patch("/api/issues/{issue_id}/review")
    def review_issue(
        issue_id: str,
        req: ReviewRequest,
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
        run_id: str | None = Query(None),
    ) -> dict[str, Any]:
        _, active_run = _ensure_dataset_and_run(repo, settings, dataset)
        target_run_id = run_id or active_run.run_id
        try:
            updated_run, record = repo.apply_review(target_run_id, issue_id, req, settings.snapshot_time_ist)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        iss = next(i for i in updated_run.issues if i.issue_id == issue_id)
        return {
            "run_id": updated_run.run_id,
            "issue": iss.model_dump(),
            "review": record.model_dump(),
        }

    @app.get("/api/reviews")
    def list_reviews(
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
        run_id: str | None = Query(None),
        issue_id: str | None = Query(None),
    ) -> dict[str, Any]:
        if run_id is None:
            _, active_run = _ensure_dataset_and_run(repo, settings, dataset)
            run_id = active_run.run_id
        revs = repo.list_reviews(run_id=run_id, issue_id=issue_id)
        return {"run_id": run_id, "count": len(revs), "reviews": [r.model_dump() for r in revs]}

    @app.get("/api/exports/queue")
    def export_queue(
        format: Literal["csv", "xlsx"] = Query("csv"),
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
    ) -> Response:
        ing, run = _ensure_dataset_and_run(repo, settings, dataset)
        if format == "xlsx":
            revs = repo.list_reviews(run_id=run.run_id)
            data = queue_to_xlsx_bytes(run, ing, revs)
            return Response(
                content=data,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="ezyhelpers_priority_queue_{dataset}.xlsx"'},
            )
        data = queue_to_csv_bytes(run)
        return Response(
            content=data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="ezyhelpers_priority_queue_{dataset}.csv"'},
        )

    @app.get("/api/exports/evaluation")
    def export_evaluation(
        format: Literal["csv", "xlsx"] = Query("csv"),
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
    ) -> Response:
        rep = latest_evaluation(dataset=dataset)
        if format == "xlsx":
            sup = latest_evaluation(dataset="supplied")
            hard = latest_evaluation(dataset="harder")
            data = evaluation_to_xlsx_bytes(sup, hard)
            return Response(
                content=data,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": 'attachment; filename="ezyhelpers_evaluation_results.xlsx"'},
            )
        data = evaluation_to_csv_bytes(rep)
        return Response(
            content=data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="ezyhelpers_evaluation_{dataset}.csv"'},
        )

    @app.get("/api/exports/issues-report")
    def export_issues_report(
        format: Literal["md", "json"] = Query("md"),
        dataset: str = Query("supplied", pattern="^(supplied|harder)$"),
    ) -> Response:
        ing, run = _ensure_dataset_and_run(repo, settings, dataset)
        revs = repo.list_reviews(run_id=run.run_id)
        if format == "json":
            return JSONResponse(content={
                "run": run.model_dump(mode="json"),
                "dq_issues": [d.model_dump(mode="json") for d in ing.dq_issues],
                "reviews": [r.model_dump(mode="json") for r in revs],
            })
        md = issues_report_markdown(run, ing, revs)
        return Response(
            content=md.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="ezyhelpers_issue_report_{dataset}.md"'},
        )

    @app.get("/api/model/status")
    def model_status() -> dict[str, Any]:
        calls = repo.list_llm_calls(limit=30)
        return {
            "provider": "openrouter",
            "base_url": settings.openrouter_base_url,
            "model": settings.openrouter_model,
            "api_key_configured": settings.llm_configured,
            "allow_live_ai": settings.allow_live_ai,
            "timeout_seconds": settings.llm_timeout_seconds,
            "max_retries": settings.llm_max_retries,
            "temperature": settings.llm_temperature,
            "pricing_assumptions_usd_per_1m": {
                "input": settings.price_input_per_m,
                "output": settings.price_output_per_m,
                "note": "Assumptions for estimation only when provider does not return cost.",
            },
            "recent_calls": [
                {
                    "call_id": c.call_id,
                    "issue_id": c.issue_id,
                    "ok": c.ok,
                    "provider": c.provider,
                    "model_requested": c.model_requested,
                    "model_used": c.model_used,
                    "started_at": c.started_at,
                    "duration_ms": c.duration_ms,
                    "attempts": c.attempts,
                    "prompt_tokens": c.prompt_tokens,
                    "completion_tokens": c.completion_tokens,
                    "total_tokens": c.total_tokens,
                    "cost_usd": c.cost_usd,
                    "error_type": c.error_type,
                    "error_message": c.error_message,
                    "simulated": c.simulated,
                }
                for c in calls
            ],
        }

    return app


app = create_app()

