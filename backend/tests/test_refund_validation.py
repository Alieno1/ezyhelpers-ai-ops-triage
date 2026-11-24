"""Repeatable tests for refund fact extraction, reusable validation, guardrails, and full dashboard workflow."""
from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.modules.evidence import find_unsupported_promises, validate_refund_draft
from app.modules.grouping import group_messages
from app.modules.ingestion import ingest
from app.modules.matching import derive_booking_facts
from app.pipeline import ai_raw_recommendation, guard_ai, parse_snapshot, recommend, run_rules
from app.modules.rules_classifier import rules_signals
from app.schemas import ActionCode, AITriageOutput, Category, Department, Urgency

PROJECT_DIR = Path(__file__).resolve().parents[2]
SNAPSHOT = "2026-11-23 09:00"


def _make_single_issue_ctx(booking_id: str, billing_record: str, customer_msg: str, ops: str = "Booking closed."):
    bookings_csv = (
        "booking_id,service,locality,scheduled_start_ist,updated_at_ist,operations_record,billing_record\n"
        f'{booking_id},Housekeeping,JP Nagar,,2026-11-23 08:20,"{ops}","{billing_record}"\n'
    ).encode("utf-8")
    inbox_csv = (
        "event_id,received_at_ist,thread_id,booking_id,channel,sender,message\n"
        f'M01,2026-11-23 08:26,T01,{booking_id},WhatsApp,Customer,"{customer_msg}"\n'
    ).encode("utf-8")
    ing = ingest(bookings_csv, inbox_csv, parse_snapshot(SNAPSHOT))
    ctxs = group_messages(ing.messages, ing.bookings)
    assert len(ctxs) == 1
    return ing, ctxs[0]


def test_1_b103_original_payment_8000_refund_approved_3000_payout_pending() -> None:
    """TEST 1: Original payment ₹8,000, refund approved ₹3,000, payout pending."""
    billing = "Original payment: ₹8,000. Refund approved: ₹3,000. Payout date: Pending."
    ing, ctx = _make_single_issue_ctx("B103", billing, "I paid ₹8,000. Is my refund approved and when will I get it?")

    facts = ctx.booking.facts
    assert facts.payment_amount == "₹8,000"
    assert facts.refund_amount == "₹3,000"
    assert facts.refund_status == "approved"
    assert facts.payout_date_recorded is False
    assert facts.billing_ambiguous is False

    # 1a. Accept correct ₹3,000 refund statement with pending payout
    ok_draft = "Your ₹3,000 refund has been approved. The payout date is still pending confirmation."
    assert find_unsupported_promises(ok_draft, ctx) == []

    # 1b. Reject ₹8,000 refund claim (original payment mistaken for refund)
    wrong_draft = "Your ₹8,000 refund has been approved."
    findings = find_unsupported_promises(wrong_draft, ctx)
    assert any(f.kind == "refund_amount_mismatch" for f in findings), f"Expected refund_amount_mismatch, got {findings}"
    assert any("₹8,000" in f.reason and "₹3,000" in f.reason for f in findings)

    # 1c. Reject any promised payout date
    payout_draft = "Your ₹3,000 refund has been approved and will be credited by Friday."
    p_findings = find_unsupported_promises(payout_draft, ctx)
    assert any(f.kind == "payout_date" for f in p_findings), f"Expected payout_date finding, got {p_findings}"

    # 1d. Full guardrail flow: incorrect AI draft is caught and replaced with safe ₹3,000 draft
    rules_rec = recommend(ctx, rules_signals(ctx, "v2"), "rules")
    ai_out = AITriageOutput(
        issue_category=Category.REFUND_QUERY,
        customer_intent="Asking about refund approval and payout.",
        resolved_by_customer=False,
        cover_available="not_applicable",
        cover_until=None,
        deadline=None,
        contact_preference="whatsapp",
        contact_channel="whatsapp",
        refund_claimed_approved=False,
        mentions_today=False,
        requested_change=None,
        suggested_urgency=Urgency.MEDIUM,
        suggested_department=Department.BILLING,
        recommended_action_code=ActionCode.RELAY_APPROVED_REFUND_CHASE_PAYOUT,
        recommended_next_action="Relay approved refund and chase Billing for payout date.",
        missing_information=["Payout date"],
        draft_response="Your ₹8,000 refund has been approved.",
        hold_contact_reason=None,
        explanation="Refund approved.",
        supporting_source_ids=["M01", "B103"],
        confidence=0.9,
    )
    raw_rec = ai_raw_recommendation(ai_out, "whatsapp", ctx)
    guarded = guard_ai(ai_out, raw_rec, ctx, rules_rec)
    assert any(e.rule_id == "PROMISE" and "refund_amount_mismatch" in e.reason for e in guarded.guardrail_events)
    assert guarded.draft_response is not None
    assert "Your ₹3,000 refund has been approved. The payout date is still pending confirmation" in guarded.draft_response
    assert "₹8,000" not in guarded.draft_response
    assert guarded.human_review_required is True


def test_2_wrong_refund_amount_5000_flagged() -> None:
    """TEST 2: Original payment ₹8,000, refund approved ₹3,000, draft claims ₹5,000 approved."""
    billing = "Original payment: ₹8,000. Refund approved: ₹3,000. Payout date: Pending."
    _, ctx = _make_single_issue_ctx("B103", billing, "Any update on my refund?")

    findings = find_unsupported_promises("Your ₹5,000 refund has been approved.", ctx)
    assert any(f.kind == "refund_amount_mismatch" for f in findings), f"Expected refund_amount_mismatch, got {findings}"
    assert any("₹5,000" in f.reason and "₹3,000" in f.reason for f in findings)


def test_3_payout_promised_tomorrow_flagged() -> None:
    """TEST 3: Original payment ₹8,000, refund approved ₹3,000, draft promises payment tomorrow."""
    billing = "Original payment: ₹8,000. Refund approved: ₹3,000. Payout date: Pending."
    _, ctx = _make_single_issue_ctx("B103", billing, "When will I receive my refund?")

    for bad_draft in (
        "Your ₹3,000 refund has been approved. Payment will be made tomorrow.",
        "Your ₹3,000 refund has been approved and payout is scheduled for tomorrow.",
    ):
        findings = find_unsupported_promises(bad_draft, ctx)
        assert any(f.kind == "payout_date" for f in findings), f"Expected payout_date for '{bad_draft}', got {findings}"


def test_4_refund_under_review_and_other_non_approved_statuses() -> None:
    """TEST 4: Refund under review (plus rejected and pending) — never claim approval."""
    # Under review
    _, ctx_review = _make_single_issue_ctx(
        "B103",
        "₹8,000 payment received. Refund under review. No approval or payout date recorded.",
        "Sales told me my refund was approved. When will I get it?",
    )
    assert ctx_review.booking.facts.refund_status == "under_review"
    f_rev = find_unsupported_promises("Your ₹8,000 refund has been approved.", ctx_review)
    assert any(f.kind == "refund_approval" for f in f_rev)

    run = run_rules(
        _make_single_issue_ctx(
            "B103",
            "₹8,000 payment received. Refund under review. No approval or payout date recorded.",
            "Sales told me my refund was approved. When will I get it?",
        )[0],
        SNAPSHOT,
        version="v2",
    )
    rec = run.issues[0].final
    assert rec.action_code == ActionCode.BILLING_VERIFY_DISPUTED_REFUND
    assert "approved" not in (rec.draft_response or "").lower()

    # Rejected status
    facts_rej = derive_booking_facts("Booking closed.", "Paid ₹6,000. Refund rejected by Billing.")
    assert facts_rej.refund_status == "rejected"
    assert facts_rej.payment_amount == "₹6,000"
    f_rej = validate_refund_draft("Your refund has been approved.", facts_rej, "Paid ₹6,000. Refund rejected by Billing.")
    assert any(f.kind == "refund_approval" and "rejected" in f.reason.lower() for f in f_rej)

    # Pending status
    facts_pend = derive_booking_facts("Booking closed.", "Payment received: ₹4,000. Refund pending.")
    assert facts_pend.refund_status == "pending"
    f_pend = validate_refund_draft("Your refund is approved.", facts_pend, "Payment received: ₹4,000. Refund pending.")
    assert any(f.kind == "refund_approval" and "pending" in f.reason.lower() for f in f_pend)


def test_5_new_booking_different_amounts_and_wording_reusable() -> None:
    """TEST 5: New booking with different amounts and differently worded billing information."""
    billing = "Paid Rs. 12,500 towards booking; partial refund of Rs. 4,500 sanctioned and approved. Payout: pending."
    ing, ctx = _make_single_issue_ctx("B909", billing, "Can you confirm my refund amount and payout date?")

    facts = ctx.booking.facts
    assert facts.payment_amount == "₹12,500"
    assert facts.refund_amount == "₹4,500"
    assert facts.refund_status == "approved"
    assert facts.payout_date_recorded is False

    # Accepts ₹4,500, rejects ₹12,500, rejects ₹7,000, rejects payout promise
    assert find_unsupported_promises("Your ₹4,500 refund has been approved. The payout date is still pending confirmation.", ctx) == []
    assert any(f.kind == "refund_amount_mismatch" for f in find_unsupported_promises("Your ₹12,500 refund has been approved.", ctx))
    assert any(f.kind == "refund_amount_mismatch" for f in find_unsupported_promises("Your ₹7,000 refund has been approved.", ctx))
    assert any(f.kind == "payout_date" for f in find_unsupported_promises("Your ₹4,500 refund will be paid tomorrow.", ctx))

    # End-to-end pipeline produces correct draft automatically
    run = run_rules(ing, SNAPSHOT, version="v2")
    rec = run.issues[0].final
    assert rec.action_code == ActionCode.RELAY_APPROVED_REFUND_CHASE_PAYOUT
    assert rec.responsible_department == Department.BILLING
    assert "Your ₹4,500 refund has been approved. The payout date is still pending confirmation" in (rec.draft_response or "")


def test_6_incomplete_or_ambiguous_billing_flagged_for_human_review() -> None:
    """TEST 6: Incomplete or ambiguous billing information flags human review and never invents facts."""
    cases = (
        "Paid ₹8,000. Refund approved. Payout date pending.",  # approved without refund amount!
        "₹8,000 payment received. Refund status unclear; check with Billing.",  # explicit ambiguity
        "Refund ₹3,000 noted.",  # refund amount without approval status
    )
    for idx, billing in enumerate(cases, start=1):
        ing, ctx = _make_single_issue_ctx(f"B80{idx}", billing, "What is the status of my refund?")
        facts = ctx.booking.facts
        assert facts.billing_ambiguous is True, f"Expected billing_ambiguous=True for '{billing}', got {facts}"

        run = run_rules(ing, SNAPSHOT, version="v2")
        rec = run.issues[0].final
        assert rec.action_code == ActionCode.BILLING_VERIFY_DISPUTED_REFUND
        assert rec.human_review_required is True
        assert any("ambiguous" in r.lower() or "incomplete" in r.lower() for r in rec.human_review_reasons)
        assert "approved" not in (rec.draft_response or "").lower()

        # Draft claiming approval must be flagged
        findings = find_unsupported_promises("Your ₹3,000 refund has been approved.", ctx)
        assert any(f.kind == "billing_ambiguous" for f in findings), f"Expected billing_ambiguous for '{billing}', got {findings}"


def test_full_workflow_dashboard_upload_b103_and_unrelated_bookings(tmp_path: Path) -> None:
    """End-to-end verification: upload updated B103 billing record -> FastAPI -> Dashboard payload."""
    settings = Settings(
        openrouter_api_key="",
        database_url=f"sqlite:///{(tmp_path / 'dashboard_test.db').as_posix()}",
        max_upload_bytes=16384,
        ai_run_cooldown_seconds=0,
        data_dir=PROJECT_DIR / "shift_data",
        evaluation_dir=PROJECT_DIR / "backend" / "evaluation",
        artifacts_dir=tmp_path / "artifacts",
    )
    client = TestClient(create_app(settings))

    # Load original booking register and update ONLY B103's billing_record
    orig_csv = (PROJECT_DIR / "backend" / "data" / "booking_register.csv").read_text(encoding="utf-8")
    updated_csv = orig_csv.replace(
        '"₹8,000 payment received. Refund under review. No approval or payout date recorded."',
        '"Original payment: ₹8,000. Refund approved: ₹3,000. Payout date: Pending."',
    )
    assert updated_csv != orig_csv

    # Upload via the actual live dashboard update endpoint
    up = client.post(
        "/api/data/upload/bookings?dataset=supplied",
        files={"file": ("booking_register.csv", io.BytesIO(updated_csv.encode("utf-8")), "text/csv")},
    )
    assert up.status_code == 200, up.text

    # Query the dashboard issues endpoint
    res = client.get("/api/issues?dataset=supplied")
    assert res.status_code == 200
    issues = res.json()["issues"]
    by_bk = {i["group"]["booking_id"]: i for i in issues if i["group"]["booking_id"]}

    # Verify B103 corrected dashboard state
    b103 = by_bk["B103"]
    assert b103["booking"]["facts"]["payment_amount"] == "₹8,000"
    assert b103["booking"]["facts"]["refund_amount"] == "₹3,000"
    assert b103["booking"]["facts"]["refund_status"] == "approved"
    assert b103["booking"]["facts"]["payout_date_recorded"] is False
    assert b103["final"]["action_code"] == "RELAY_APPROVED_REFUND_CHASE_PAYOUT"
    assert b103["final"]["responsible_department"] == "Billing"
    assert "Your ₹3,000 refund has been approved. The payout date is still pending confirmation" in b103["final"]["draft_response"]
    assert "₹8,000" not in b103["final"]["draft_response"]

    # Verify unrelated bookings are completely unaffected
    assert by_bk["B101"]["final"]["priority_rank"] == 1
    assert by_bk["B101"]["final"]["action_code"] == "CARE_GAP_IMMEDIATE"
    assert by_bk["B101"]["final"]["contact_channel"] == "phone"
    assert by_bk["B105"]["final"]["action_code"] == "CARE_GAP_COVERED_CHASE_SOURCING"
    assert by_bk["B105"]["final"]["contact_channel"] == "whatsapp"
    assert by_bk["B102"]["final"]["action_code"] == "CLOSE_CONFIRMED_ARRIVAL"
    assert by_bk["B106"]["final"]["action_code"] == "RELAY_APPROVED_REFUND_CHASE_PAYOUT"
    assert "₹2,000" in by_bk["B106"]["final"]["draft_response"]

