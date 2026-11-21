"""CLI runner for reproducible terminal execution (rules, AI, evaluation, exports)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import BACKEND_DIR, get_settings
from app.modules.evaluation import run_full_evaluation
from app.modules.exports import evaluation_to_csv_bytes, evaluation_to_xlsx_bytes, queue_to_csv_bytes, queue_to_xlsx_bytes
from app.modules.ingestion import ingest_files
from app.modules.llm_client import OpenRouterClient
from app.pipeline import parse_snapshot, run_ai, run_rules


def _paths(dataset: str):
    settings = get_settings()
    if dataset == "harder":
        d = settings.evaluation_dir / "harder_cases"
        return d / "booking_register.csv", d / "shift_inbox.csv", d / "expected_actions.json"
    b = settings.data_dir / "booking_register.csv"
    i = settings.data_dir / "shift_inbox.csv"
    if not b.exists() or not i.exists():
        b, i = BACKEND_DIR / "data" / "booking_register.csv", BACKEND_DIR / "data" / "shift_inbox.csv"
    return b, i, settings.evaluation_dir / "expected_actions.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EzyHelpers AI Operations Triage CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rules = sub.add_parser("rules", help="Run deterministic rules pipeline")
    p_rules.add_argument("--dataset", choices=["supplied", "harder"], default="supplied")
    p_rules.add_argument("--version", choices=["v1", "v2"], default="v2")

    p_ai = sub.add_parser("ai", help="Run OpenRouter AI pipeline (falls back to rules on failure)")
    p_ai.add_argument("--dataset", choices=["supplied", "harder"], default="supplied")
    p_ai.add_argument("--prompt-version", choices=["v1", "v2"], default="v1")

    p_eval = sub.add_parser("evaluate", help="Run before/after evaluation against frozen expected actions")
    p_eval.add_argument("--dataset", choices=["supplied", "harder"], default="supplied")
    p_eval.add_argument("--include-ai", action="store_true")

    p_exp = sub.add_parser("export-all", help="Write CSV/XLSX/JSON artifacts to backend/artifacts/")
    p_exp.add_argument("--out-dir", default=str(BACKEND_DIR / "artifacts"))

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.cmd == "rules":
        b, i, _ = _paths(args.dataset)
        ing = ingest_files(b, i, parse_snapshot(settings.snapshot_time_ist))
        run = run_rules(ing, settings.snapshot_time_ist, version=args.version, dataset=args.dataset)
        print(json.dumps({"run_id": run.run_id, "variant": run.variant, "issues": len(run.issues)}, indent=2))
        for iss in run.issues:
            f = iss.final
            print(f"#{f.priority_rank} {iss.issue_id} bk={iss.group.booking_id} msgs={iss.group.source_message_ids} "
                  f"urg={f.urgency.value} dept={f.responsible_department.value} act={f.action_code.value} ch={f.contact_channel.value}")
        return 0

    if args.cmd == "ai":
        b, i, _ = _paths(args.dataset)
        ing = ingest_files(b, i, parse_snapshot(settings.snapshot_time_ist))
        client = OpenRouterClient(
            api_key=settings.openrouter_api_key, model=settings.openrouter_model,
            base_url=settings.openrouter_base_url, timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries, temperature=settings.llm_temperature,
        )
        run = run_ai(ing, settings.snapshot_time_ist, client, prompt_version=args.prompt_version, dataset=args.dataset, rules_version="v2")
        print(json.dumps({"run_id": run.run_id, "status": run.status, "model": run.model, "notes": run.notes}, indent=2))
        return 0

    if args.cmd == "evaluate":
        b, i, exp = _paths(args.dataset)
        ing = ingest_files(b, i, parse_snapshot(settings.snapshot_time_ist))
        client = OpenRouterClient(
            api_key=settings.openrouter_api_key, model=settings.openrouter_model,
            base_url=settings.openrouter_base_url,
        )
        rep = run_full_evaluation(ing, settings.snapshot_time_ist, args.dataset, exp, client=client, include_ai=args.include_ai)
        print(json.dumps(rep.model_dump(), indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "export-all":
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        b_s, i_s, exp_s = _paths("supplied")
        ing_s = ingest_files(b_s, i_s, parse_snapshot(settings.snapshot_time_ist))
        run_s = run_rules(ing_s, settings.snapshot_time_ist, version="v2", dataset="supplied")
        b_h, i_h, exp_h = _paths("harder")
        ing_h = ingest_files(b_h, i_h, parse_snapshot(settings.snapshot_time_ist))
        rep_s = run_full_evaluation(ing_s, settings.snapshot_time_ist, "supplied", exp_s)
        rep_h = run_full_evaluation(ing_h, settings.snapshot_time_ist, "harder", exp_h)

        (out / "priority_queue_supplied.csv").write_bytes(queue_to_csv_bytes(run_s))
        (out / "priority_queue_supplied.xlsx").write_bytes(queue_to_xlsx_bytes(run_s, ing_s, []))
        (out / "evaluation_supplied.csv").write_bytes(evaluation_to_csv_bytes(rep_s))
        (out / "evaluation_results.xlsx").write_bytes(evaluation_to_xlsx_bytes(rep_s, rep_h))
        (out / "evaluation_supplied.json").write_text(rep_s.model_dump_json(indent=2), encoding="utf-8")
        (out / "evaluation_harder.json").write_text(rep_h.model_dump_json(indent=2), encoding="utf-8")
        print(f"Exported artifacts to {out}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

