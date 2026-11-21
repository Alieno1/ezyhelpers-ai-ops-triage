"""End-to-end API, evaluation, human review, security, and export tests."""
from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.config import Settings
from app.db import normalize_db_url
from app.main import create_app

PROJECT_DIR = Path(__file__).resolve().parents[2]


def _make_client(tmp_path: Path, api_key: str = "") -> TestClient:
    settings = Settings(
        openrouter_api_key=api_key,
        openrouter_model="google/gemini-2.5-flash",
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        max_upload_bytes=2048,
        ai_run_cooldown_seconds=0,
        data_dir=PROJECT_DIR / "shift_data",
        evaluation_dir=PROJECT_DIR / "backend" / "evaluation",
        artifacts_dir=tmp_path / "artifacts",
    )
    app = create_app(settings)
    return TestClient(app)


def test_health_overview_and_security_controls(tmp_path: Path) -> None:
    assert normalize_db_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_db_url("postgresql://u:p@h/db?sslmode=require") == "postgresql+psycopg://u:p@h/db?sslmode=require"
    assert normalize_db_url("postgresql+psycopg2://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
    assert normalize_db_url("sqlite:///triage.db") == "sqlite:///triage.db"

    client = _make_client(tmp_path, api_key="sk-or-secret-test-value")
    r_health = client.get("/health")
    assert r_health.status_code == 200
    h = r_health.json()
    assert h["status"] == "ok"
    assert h["database"]["connected"] is True
    assert h["openrouter"]["configured"] is True

    # Never leak API key in /api/model/status
    r_mod = client.get("/api/model/status")
    assert r_mod.status_code == 200
    assert "sk-or-secret-test-value" not in r_mod.text
    assert r_mod.json()["api_key_configured"] is True

    # Private submission is NEVER served by FastAPI
    assert client.get("/private_submission/EzyHelpers_Assignment_2_Technical_Report.pdf").status_code == 404

    r_ov = client.get("/api/overview?dataset=supplied")
    assert r_ov.status_code == 200
    ov = r_ov.json()
    assert ov["metrics"]["total_messages"] == 12
    assert ov["metrics"]["distinct_issues"] == 8
    assert ov["first_callback"]["booking_id"] == "B101"


def test_evaluation_scores_before_and_after_improvement(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    # Supplied dataset evaluation: v1=7/8 -> v2=8/8, 0 unsupported promises
    r_sup = client.post("/api/processing/evaluate?dataset=supplied&include_ai=false")
    assert r_sup.status_code == 200
    rep = r_sup.json()
    methods = {m["variant"]: m for m in rep["methods"]}
    assert methods["rules_v1"]["correct_next_actions"] == 7
    assert methods["rules_v1"]["total_cases"] == 8
    assert methods["rules_v1"]["unsupported_promises"] == 0
    assert methods["rules_v2"]["correct_next_actions"] == 8
    assert methods["rules_v2"]["unsupported_promises"] == 0
    assert methods["rules_v2"]["first_callback_correct"] is True
    assert methods["ai_v1_live"]["status"] == "pending_credentials"
    assert rep["improvement_summary"]["delta_correct"] == 1

    # Harder synthetic dataset: v1=5/6 -> v2=6/6, 0 unsupported promises
    r_hard = client.post("/api/processing/evaluate?dataset=harder&include_ai=false")
    assert r_hard.status_code == 200
    hrep = r_hard.json()
    hmethods = {m["variant"]: m for m in hrep["methods"]}
    assert hmethods["rules_v1"]["correct_next_actions"] == 5
    assert hmethods["rules_v1"]["total_cases"] == 6
    assert hmethods["rules_v2"]["correct_next_actions"] == 6
    assert hmethods["rules_v2"]["unsupported_promises"] == 0


def test_human_review_actions_and_priority_reranking(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    issues = client.get("/api/issues?dataset=supplied").json()["issues"]
    # Pick B104 schedule change (initially medium)
    b104 = next(i for i in issues if i["group"]["booking_id"] == "B104")
    iid = b104["issue_id"]

    # Escalate priority to critical -> should move near top & persist override
    r1 = client.patch(f"/api/issues/{iid}/review?dataset=supplied", json={
        "action": "change_priority", "urgency": "critical", "reason": "VIP elderly parent cooks at home", "reviewer": "ananya",
    })
    assert r1.status_code == 200
    assert r1.json()["issue"]["final"]["urgency"] == "critical"
    assert r1.json()["issue"]["final"]["source"] == "human"

    # Edit draft + approve -> override MUST survive subsequent review actions!
    r2 = client.patch(f"/api/issues/{iid}/review?dataset=supplied", json={
        "action": "edit_draft", "draft_response": "Hi, checking with your cook for 10 AM tomorrow now.", "reason": "Clearer phrasing",
    })
    assert r2.status_code == 200
    assert r2.json()["issue"]["final"]["urgency"] == "critical"
    assert "10 AM tomorrow" in r2.json()["issue"]["final"]["draft_response"]

    # Request info -> awaiting_info
    r3 = client.patch(f"/api/issues/{iid}/review?dataset=supplied", json={
        "action": "request_info", "info_requested": "Confirm dietary restriction", "reason": "Need note for cook",
    })
    assert r3.status_code == 200
    assert r3.json()["issue"]["final"]["status"] == "awaiting_info"

    # Resolve -> resolved
    r4 = client.patch(f"/api/issues/{iid}/review?dataset=supplied", json={
        "action": "resolve", "reason": "Confirmed via phone",
    })
    assert r4.status_code == 200
    assert r4.json()["issue"]["final"]["status"] == "resolved"
    assert r4.json()["issue"]["final"]["urgency"] == "none"

    revs = client.get(f"/api/reviews?dataset=supplied&issue_id={iid}").json()
    assert revs["count"] == 4


def test_ai_fallback_upload_validation_and_exports(tmp_path: Path) -> None:
    client = _make_client(tmp_path, api_key="")

    # Calling /api/processing/ai without key falls back cleanly and logs failed calls
    r_ai = client.post("/api/processing/ai?dataset=supplied")
    assert r_ai.status_code == 200
    data_ai = r_ai.json()
    assert data_ai["status"] == "failed"
    assert len(data_ai["llm_calls"]) == 8
    assert all(i["final"]["source"] == "rules_fallback" for i in data_ai["issues"])

    # Model status shows the preserved failed calls
    calls = client.get("/api/model/status").json()["recent_calls"]
    assert len(calls) >= 8 and calls[0]["error_type"] == "missing_api_key"

    # Upload limits & bad CSV
    too_big = b"booking_id,service\n" + b"B999,Cooking\n" * 300
    r_big = client.post("/api/data/upload/bookings", files={"file": ("big.csv", too_big, "text/csv")})
    assert r_big.status_code == 413

    r_bad = client.post("/api/data/upload/bookings", files={"file": ("bad.csv", b"foo,bar\n1,2\n", "text/csv")})
    assert r_bad.status_code == 400

    # Reset back to supplied and test exports
    assert client.post("/api/data/reset?dataset=supplied").status_code == 200

    r_q_csv = client.get("/api/exports/queue?format=csv&dataset=supplied")
    assert r_q_csv.status_code == 200 and "CARE_GAP_IMMEDIATE" in r_q_csv.text

    r_q_xlsx = client.get("/api/exports/queue?format=xlsx&dataset=supplied")
    assert r_q_xlsx.status_code == 200
    wb_q = load_workbook(io.BytesIO(r_q_xlsx.content))
    assert {"Summary", "Priority Queue", "Message Timeline", "Data Quality", "Human Reviews"} <= set(wb_q.sheetnames)

    r_e_csv = client.get("/api/exports/evaluation?format=csv&dataset=supplied")
    assert r_e_csv.status_code == 200 and "rules_v2" in r_e_csv.text

    r_e_xlsx = client.get("/api/exports/evaluation?format=xlsx&dataset=supplied")
    assert r_e_xlsx.status_code == 200
    wb_e = load_workbook(io.BytesIO(r_e_xlsx.content))
    assert {"Summary Comparison", "Supplied Cases", "Harder Synthetic Cases", "Failures & Improvement"} <= set(wb_e.sheetnames)

    r_md = client.get("/api/exports/issues-report?format=md&dataset=supplied")
    assert r_md.status_code == 200 and "# EzyHelpers Shift Triage Report" in r_md.text

    r_json = client.get("/api/exports/issues-report?format=json&dataset=supplied")
    assert r_json.status_code == 200 and r_json.json()["run"]["dataset"] == "supplied"

