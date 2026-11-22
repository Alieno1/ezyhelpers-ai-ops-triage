"""Tests for OpenRouter client, Pydantic validation, PII redaction, guardrails, and failure fallbacks.

All mocked transports explicitly mark records as simulated=True.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.modules.ai_triage import build_user_payload
from app.modules.grouping import group_messages
from app.modules.ingestion import ingest, ingest_files
from app.modules.llm_client import OpenRouterClient
from app.modules.normalisation import redact_pii
from app.pipeline import parse_snapshot, run_ai
from app.schemas import ActionCode, Channel, Department, IssueStatus

PROJECT_DIR = Path(__file__).resolve().parents[2]
SUPPLIED_BOOKINGS = PROJECT_DIR / "shift_data" / "booking_register.csv"
SUPPLIED_INBOX = PROJECT_DIR / "shift_data" / "shift_inbox.csv"


def _valid_ai_json(**overrides) -> dict:
    base = {
        "issue_category": "care_gap",
        "customer_intent": "Caregiver did not arrive; father left alone at 9:10.",
        "resolved_by_customer": False,
        "cover_available": "no",
        "cover_until": None,
        "deadline": "09:10",
        "contact_preference": "phone",
        "contact_channel": "phone",
        "refund_claimed_approved": False,
        "mentions_today": True,
        "requested_change": None,
        "suggested_urgency": "critical",
        "suggested_department": "Duty Ops",
        "recommended_action_code": "CARE_GAP_IMMEDIATE",
        "recommended_next_action": "Call customer now and check Sourcing.",
        "missing_information": ["Caregiver ETA"],
        "draft_response": "Hello, we are checking with the caregiver and our Sourcing team is looking for cover.",
        "hold_contact_reason": None,
        "explanation": "Urgent care gap.",
        "supporting_source_ids": ["M01", "B101"],
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def test_pii_redaction_before_external_llm() -> None:
    red = redact_pii("Call +91 98765 43210 or mail user.test@example.com ASAP")
    assert "98765" not in red
    assert "user.test@example.com" not in red
    assert "[PHONE]" in red and "[EMAIL]" in red


def test_guardrails_override_bad_ai_department_promise_and_channel() -> None:
    # Single-issue dataset for B103 disputed refund
    b_csv = (
        "booking_id,service,locality,scheduled_start_ist,updated_at_ist,operations_record,billing_record\n"
        "B103,Housekeeping,JP Nagar,,2026-11-23 08:20,Booking closed.,\"₹8,000 payment received. Refund under review. No approval or payout date recorded.\"\n"
    ).encode("utf-8")
    i_csv = (
        "event_id,received_at_ist,thread_id,booking_id,channel,sender,message\n"
        "M03,2026-11-23 08:26,T03,B103,WhatsApp,Customer,\"I paid ₹8,000. Sales told me my refund was approved. Please WhatsApp me, don't call.\"\n"
    ).encode("utf-8")
    ing = ingest(b_csv, i_csv, parse_snapshot("2026-11-23 09:00"))

    bad_ai = _valid_ai_json(
        issue_category="refund_query",
        cover_available="not_applicable",
        deadline=None,
        contact_preference="phone",
        contact_channel="phone",  # violates explicit don't call
        refund_claimed_approved=True,
        suggested_department="Sales",  # violates Billing ownership (R5/R6)
        recommended_action_code="RELAY_CONFIRMED_REFUND_FACTS",  # register says under review!
        draft_response="Your ₹8,000 refund is approved and will reach within 3 working days.",  # unsupported!
        supporting_source_ids=["M03", "B103", "FAKE_ID"],
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "gen-1", "model": "google/gemini-2.5-flash", "provider": "Google",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(bad_ai)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "cost": 0.0002},
        })

    client = OpenRouterClient("test-key", "google/gemini-2.5-flash", transport=httpx.MockTransport(handler))
    run = run_ai(ing, "2026-11-23 09:00", client)
    assert run.status == "completed"
    assert run.llm_calls[0].simulated is True
    assert run.llm_calls[0].total_tokens == 150

    iss = run.issues[0]
    assert iss.ai_status == "ok"
    assert iss.final.responsible_department == Department.BILLING
    assert iss.final.action_code == ActionCode.BILLING_VERIFY_DISPUTED_REFUND
    assert iss.final.contact_channel == Channel.WHATSAPP
    assert "within 3 working days" not in (iss.final.draft_response or "")
    rule_ids = {e.rule_id for e in iss.final.guardrail_events}
    assert {"R3", "R1/R5/R7", "ACTION_MAP", "EVIDENCE"} <= rule_ids


def test_invalid_json_triggers_repair_and_schema_failure_falls_back() -> None:
    b_csv = (
        "booking_id,service,locality,scheduled_start_ist,updated_at_ist,operations_record,billing_record\n"
        "B101,Elder companionship,HSR Layout,2026-11-23 08:00,2026-11-22 18:10,Regular caregiver assigned.,\n"
    ).encode("utf-8")
    i_csv = (
        "event_id,received_at_ist,thread_id,booking_id,channel,sender,message\n"
        "M01,2026-11-23 08:17,T01,B101,WhatsApp,Customer,Dad caregiver missing.\n"
    ).encode("utf-8")
    ing = ingest(b_csv, i_csv, parse_snapshot("2026-11-23 09:00"))

    # Case A: invalid JSON then valid JSON on repair call
    calls = {"n": 0}
    def repair_handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        content = "{broken json" if calls["n"] == 1 else json.dumps(_valid_ai_json(supporting_source_ids=["M01", "B101"]))
        return httpx.Response(200, json={
            "model": "google/gemini-2.5-flash",
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        })

    client_ok = OpenRouterClient("k", "google/gemini-2.5-flash", transport=httpx.MockTransport(repair_handler))
    run_ok = run_ai(ing, "2026-11-23 09:00", client_ok)
    assert run_ok.issues[0].ai_status == "ok"
    assert calls["n"] == 2
    assert run_ok.llm_calls[0].total_tokens == 140

    # Case B: both attempts fail Pydantic -> fallback to rules_fallback
    def always_bad(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "model": "google/gemini-2.5-flash",
            "choices": [{"finish_reason": "stop", "message": {"content": '{"issue_category": "invalid_cat"}'}}],
        })

    client_fail = OpenRouterClient("k", "google/gemini-2.5-flash", transport=httpx.MockTransport(always_bad))
    run_fail = run_ai(ing, "2026-11-23 09:00", client_fail)
    assert run_fail.status == "failed"
    assert run_fail.issues[0].ai_status == "failed"
    assert run_fail.issues[0].final.source == "rules_fallback"
    assert run_fail.llm_calls[0].error_type == "schema_validation_failed"


def test_openrouter_timeout_rate_limit_unavailable_and_missing_key_fallbacks() -> None:
    b_csv = SUPPLIED_BOOKINGS.read_bytes()
    # Keep only 1 message for fast deterministic failure tests
    i_csv = (
        "event_id,received_at_ist,thread_id,booking_id,channel,sender,message\n"
        "M01,2026-11-23 08:17,T01,B101,WhatsApp,Customer,Dad caregiver missing.\n"
    ).encode("utf-8")
    ing = ingest(b_csv, i_csv, parse_snapshot("2026-11-23 09:00"))

    # 1. Missing API key
    c_no_key = OpenRouterClient("", "google/gemini-2.5-flash")
    r_no_key = run_ai(ing, "2026-11-23 09:00", c_no_key)
    assert r_no_key.status == "failed"
    assert r_no_key.issues[0].final.source == "rules_fallback"
    assert r_no_key.llm_calls[0].error_type == "missing_api_key"

    # 2. Timeout retry exhaustion
    def timeout_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=req)

    c_to = OpenRouterClient("k", "google/gemini-2.5-flash", max_retries=1, backoff_base=0.0, transport=httpx.MockTransport(timeout_handler))
    r_to = run_ai(ing, "2026-11-23 09:00", c_to)
    assert r_to.issues[0].final.source == "rules_fallback"
    assert r_to.llm_calls[0].attempts == 2
    assert r_to.llm_calls[0].error_type == "timeout"

    # 3. 429 rate limit
    def rl_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0"}, text="rate limited")

    c_rl = OpenRouterClient("k", "google/gemini-2.5-flash", max_retries=1, backoff_base=0.0, transport=httpx.MockTransport(rl_handler))
    r_rl = run_ai(ing, "2026-11-23 09:00", c_rl)
    assert r_rl.issues[0].final.source == "rules_fallback"
    assert r_rl.llm_calls[0].error_type == "rate_limited"
    assert r_rl.llm_calls[0].attempts == 2

    # 4. 404 model unavailable -> no retry, immediate fallback
    def not_found(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="model not found")

    c_404 = OpenRouterClient("k", "missing/model", max_retries=2, backoff_base=0.0, transport=httpx.MockTransport(not_found))
    r_404 = run_ai(ing, "2026-11-23 09:00", c_404)
    assert r_404.issues[0].final.source == "rules_fallback"
    assert r_404.llm_calls[0].attempts == 1
    assert r_404.llm_calls[0].error_type == "model_unavailable"

    # 5. 400 json_schema unsupported -> automatic downgrade to json_object succeeds
    seen_formats = []
    def schema_downgrade(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen_formats.append(body["response_format"]["type"])
        if len(seen_formats) == 1:
            return httpx.Response(400, text="response_format json_schema is not supported")
        return httpx.Response(200, json={
            "model": "google/gemini-2.5-flash",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(_valid_ai_json(supporting_source_ids=["M01", "B101"]))}}],
        })

    c_down = OpenRouterClient("k", "google/gemini-2.5-flash", transport=httpx.MockTransport(schema_downgrade))
    r_down = run_ai(ing, "2026-11-23 09:00", c_down)
    assert seen_formats == ["json_schema", "json_object"]
    assert r_down.issues[0].ai_status == "ok"


def test_user_payload_has_no_raw_credentials() -> None:
    ing = ingest_files(SUPPLIED_BOOKINGS, SUPPLIED_INBOX, parse_snapshot("2026-11-23 09:00"))
    ctxs = group_messages(ing.messages, ing.bookings)
    pl = build_user_payload(ctxs[0], "2026-11-23 09:00")
    assert pl["issue_id"] == "ISS-01"
    assert pl["booking_register_row"]["booking_id"] == "B101"


def test_failed_ai_scores_zero_in_evaluation() -> None:
    from app.modules.evaluation import evaluate_run, load_expected

    ing = ingest_files(SUPPLIED_BOOKINGS, SUPPLIED_INBOX, parse_snapshot("2026-11-23 09:00"))
    expected = load_expected(PROJECT_DIR / "backend" / "evaluation" / "expected_actions.json")

    def always_402(req: httpx.Request) -> httpx.Response:
        return httpx.Response(402, text="insufficient credits")

    client = OpenRouterClient("k", "google/gemma-4-31b-it:free", max_retries=0, transport=httpx.MockTransport(always_402))
    failed_run = run_ai(ing, "2026-11-23 09:00", client)
    assert failed_run.status == "failed"

    metrics, _, disagreements = evaluate_run(failed_run, expected, "ai_v1_guarded", "AI Guarded", use_field="ai_guarded")
    assert metrics.correct_next_actions == 0
    assert metrics.first_callback_correct is False
    assert any(d.kind == "ai_failure" for d in disagreements)


def test_reasoning_effort_downgrade_and_truncation_retry() -> None:
    b_csv = (
        "booking_id,service,locality,scheduled_start_ist,updated_at_ist,operations_record,billing_record\n"
        "B101,Elder companionship,HSR Layout,2026-11-23 08:00,2026-11-22 18:10,Regular caregiver assigned.,\n"
    ).encode("utf-8")
    i_csv = (
        "event_id,received_at_ist,thread_id,booking_id,channel,sender,message\n"
        "M01,2026-11-23 08:17,T01,B101,WhatsApp,Customer,Dad caregiver missing.\n"
    ).encode("utf-8")
    ing = ingest(b_csv, i_csv, parse_snapshot("2026-11-23 09:00"))

    # 1a. Pinned model strips reasoning immediately on HTTP 400 rejecting reasoning.
    seen_pinned: list[object] = []

    def strip_pinned_handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen_pinned.append(body.get("reasoning"))
        if len(seen_pinned) == 1:
            return httpx.Response(400, text="Reasoning is mandatory for this endpoint and cannot be disabled.")
        return httpx.Response(200, json={
            "model": "baidu/ernie-5.5-flash-preview:free",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(_valid_ai_json(supporting_source_ids=["M01", "B101"]))}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        })

    c_pinned = OpenRouterClient("k", "baidu/ernie-5.5-flash-preview:free", transport=httpx.MockTransport(strip_pinned_handler))
    r_pinned = run_ai(ing, "2026-11-23 09:00", c_pinned)
    assert seen_pinned == [{"enabled": False}, None]
    assert r_pinned.issues[0].ai_status == "ok"

    # 1b. openrouter/free retries once keeping reasoning={"enabled": False} before stripping on a second 400.
    seen_router: list[object] = []

    def router_retry_handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen_router.append(body.get("reasoning"))
        if len(seen_router) <= 2:
            return httpx.Response(400, text="Reasoning is mandatory for this endpoint and cannot be disabled.")
        return httpx.Response(200, json={
            "model": "nvidia/nemotron-3.5-super-vl:free",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(_valid_ai_json(supporting_source_ids=["M01", "B101"]))}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        })

    c_router = OpenRouterClient("k", "openrouter/free", transport=httpx.MockTransport(router_retry_handler))
    r_router = run_ai(ing, "2026-11-23 09:00", c_router)
    assert seen_router == [{"enabled": False}, {"enabled": False}, None]
    assert r_router.issues[0].ai_status == "ok"

    # 2. One finish_reason="length" retries once and accumulates tokens across attempts.
    trunc_calls = {"n": 0}

    def trunc_then_ok(req: httpx.Request) -> httpx.Response:
        trunc_calls["n"] += 1
        if trunc_calls["n"] == 1:
            return httpx.Response(200, json={
                "model": "recursive/flint-v1.0:free",
                "choices": [{"finish_reason": "length", "message": {"content": "{partial"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 500, "total_tokens": 600, "cost": 0.001},
            })
        return httpx.Response(200, json={
            "model": "nvidia/nemotron-3.5-lightning:free",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(_valid_ai_json(supporting_source_ids=["M01", "B101"]))}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200, "cost": 0.0},
        })

    c_retry = OpenRouterClient("k", "openrouter/free", max_retries=2, backoff_base=0.0, transport=httpx.MockTransport(trunc_then_ok))
    r_retry = run_ai(ing, "2026-11-23 09:00", c_retry)
    assert trunc_calls["n"] == 2
    assert r_retry.issues[0].ai_status == "ok"
    assert r_retry.llm_calls[0].attempts == 2
    assert r_retry.llm_calls[0].total_tokens == 800

    # 3. Two consecutive finish_reason="length" stop after 2 attempts and fall back cleanly.
    always_calls = {"n": 0}

    def always_trunc(req: httpx.Request) -> httpx.Response:
        always_calls["n"] += 1
        return httpx.Response(200, json={
            "model": "recursive/flint-v1.0:free",
            "choices": [{"finish_reason": "length", "message": {"content": "{partial"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 500, "total_tokens": 600},
        })

    c_fail = OpenRouterClient("k", "openrouter/free", max_retries=2, backoff_base=0.0, transport=httpx.MockTransport(always_trunc))
    r_fail = run_ai(ing, "2026-11-23 09:00", c_fail)
    assert always_calls["n"] == 2
    assert r_fail.issues[0].ai_status == "failed"
    assert r_fail.issues[0].final.source == "rules_fallback"
    assert r_fail.llm_calls[0].attempts == 2
    assert r_fail.llm_calls[0].error_type == "incomplete_response"
    assert r_fail.llm_calls[0].total_tokens == 1200


def test_r9_promotes_resolved_service_gap_and_blocks_negated_closure() -> None:
    b_csv = (
        "booking_id,service,locality,scheduled_start_ist,updated_at_ist,operations_record,billing_record\n"
        "B102,Housekeeping,Bellandur,2026-11-23 08:15,2026-11-23 08:12,Helper assigned. Arrival pending.,\n"
    ).encode("utf-8")

    # 1. Non-negated arrival confirmation with resolved_by_customer=True and issue_category="service_gap"
    i_ok = (
        "event_id,received_at_ist,thread_id,booking_id,channel,sender,message\n"
        "M02,2026-11-23 08:23,T02,B102,WhatsApp,Customer,Our 8:15 housekeeping shift hasn't started. Can you check?\n"
        "M08,2026-11-23 08:46,T02,B102,WhatsApp,Customer,\"Aa gayi hain. She is here now, all sorted. Please close this.\"\n"
    ).encode("utf-8")
    ing_ok = ingest(b_csv, i_ok, parse_snapshot("2026-11-23 09:00"))
    ai_close = _valid_ai_json(
        issue_category="service_gap",
        resolved_by_customer=True,
        cover_available="not_applicable",
        deadline=None,
        contact_preference="no_preference",
        contact_channel="none",
        suggested_urgency="low",
        recommended_action_code="SERVICE_GAP_CHECK_ARRIVAL",
        supporting_source_ids=["M02", "M08", "B102"],
    )

    def ok_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "model": "nvidia/nemotron-3.5-lightning:free",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(ai_close)}}],
        })

    run_ok = run_ai(ing_ok, "2026-11-23 09:00", OpenRouterClient("k", "openrouter/free", transport=httpx.MockTransport(ok_handler)))
    iss_ok = run_ok.issues[0]
    assert iss_ok.final.action_code == ActionCode.CLOSE_CONFIRMED_ARRIVAL
    assert iss_ok.final.status == IssueStatus.RESOLVED
    assert iss_ok.final.contact_channel == Channel.NONE
    assert any(e.rule_id == "R9" for e in iss_ok.final.guardrail_events)

    # 2. Negated closure ("Please don't close, she still hasn't come.") remains blocked and open
    i_neg = (
        "event_id,received_at_ist,thread_id,booking_id,channel,sender,message\n"
        "M02,2026-11-23 08:23,T02,B102,WhatsApp,Customer,Our 8:15 housekeeping shift hasn't started. Can you check?\n"
        "M08,2026-11-23 08:46,T02,B102,WhatsApp,Customer,\"Please don't close, she still hasn't come.\"\n"
    ).encode("utf-8")
    ing_neg = ingest(b_csv, i_neg, parse_snapshot("2026-11-23 09:00"))
    ai_bad_close = _valid_ai_json(
        issue_category="arrival_confirmed",
        resolved_by_customer=True,
        cover_available="not_applicable",
        deadline=None,
        contact_preference="no_preference",
        contact_channel="none",
        suggested_urgency="none",
        recommended_action_code="CLOSE_CONFIRMED_ARRIVAL",
        supporting_source_ids=["M02", "M08", "B102"],
    )

    def neg_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "model": "nvidia/nemotron-3.5-lightning:free",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(ai_bad_close)}}],
        })

    run_neg = run_ai(ing_neg, "2026-11-23 09:00", OpenRouterClient("k", "openrouter/free", transport=httpx.MockTransport(neg_handler)))
    iss_neg = run_neg.issues[0]
    assert iss_neg.final.action_code == ActionCode.SERVICE_GAP_CHECK_ARRIVAL
    assert iss_neg.final.status == IssueStatus.OPEN
    assert any(e.rule_id == "R9" for e in iss_neg.final.guardrail_events)

