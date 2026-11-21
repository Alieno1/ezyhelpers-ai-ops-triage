"""Tests for deterministic business rules R1-R11, priority engine, and promise guardrails."""
from __future__ import annotations

from pathlib import Path

from app.modules.evidence import find_unsupported_promises
from app.modules.grouping import group_messages
from app.modules.ingestion import ingest_files
from app.modules.priority import first_callback
from app.pipeline import parse_snapshot, run_rules
from app.schemas import ActionCode, Channel, Department, IssueStatus, Urgency

PROJECT_DIR = Path(__file__).resolve().parents[2]
SUPPLIED_BOOKINGS = PROJECT_DIR / "shift_data" / "booking_register.csv"
SUPPLIED_INBOX = PROJECT_DIR / "shift_data" / "shift_inbox.csv"
HARDER_DIR = PROJECT_DIR / "backend" / "evaluation" / "harder_cases"


def test_supplied_priority_first_callback_and_all_business_rules() -> None:
    snap = "2026-11-23 09:00"
    ing = ingest_files(SUPPLIED_BOOKINGS, SUPPLIED_INBOX, parse_snapshot(snap))
    run = run_rules(ing, snap, version="v2")
    assert len(run.issues) == 8

    # Rank #1 MUST be B101 (M01+M07): uncovered care gap, deadline 09:10, phone call
    top = run.issues[0]
    assert top.group.booking_id == "B101"
    assert top.group.source_message_ids == ["M01", "M07"]
    assert top.final.urgency == Urgency.CRITICAL
    assert top.final.action_code == ActionCode.CARE_GAP_IMMEDIATE
    assert top.final.contact_channel == Channel.PHONE
    assert top.final.responsible_department == Department.DUTY_OPS

    # Rank #2 is B105 (M06+M12): care gap covered until 11:30, MUST NOT call (WhatsApp only)
    second = run.issues[1]
    assert second.group.booking_id == "B105"
    assert second.final.urgency == Urgency.HIGH
    assert second.final.action_code == ActionCode.CARE_GAP_COVERED_CHASE_SOURCING
    assert second.final.contact_channel == Channel.WHATSAPP

    by_bk = {i.group.booking_id: i for i in run.issues}
    # B103 disputed refund: register says under review, never assume approved
    b103 = by_bk["B103"].final
    assert b103.responsible_department == Department.BILLING
    assert b103.action_code == ActionCode.BILLING_VERIFY_DISPUTED_REFUND
    assert "approved" not in (b103.draft_response or "").lower() or "do not" in (b103.draft_response or "").lower() or "under review" in (b103.draft_response or "").lower()

    # B106 approved refund without payout date: relay Rs. 2,000 approval, chase payout
    b106 = by_bk["B106"].final
    assert b106.responsible_department == Department.BILLING
    assert b106.action_code == ActionCode.RELAY_APPROVED_REFUND_CHASE_PAYOUT
    assert "₹2,000" in (b106.draft_response or "")

    # B104 Hinglish schedule change caught by v2
    b104 = by_bk["B104"].final
    assert b104.responsible_department == Department.DUTY_OPS
    assert b104.action_code == ActionCode.SCHEDULE_CHANGE_SOURCING_CHECK
    assert b104.signals and b104.signals.requested_change == "10:00"

    # B102 arrival confirmation closed, no draft
    b102 = by_bk["B102"].final
    assert b102.status == IssueStatus.RESOLVED
    assert b102.urgency == Urgency.NONE
    assert b102.contact_channel == Channel.NONE
    assert b102.draft_response is None

    # M05 enquiry -> Sales, no price
    m05 = next(i for i in run.issues if i.group.source_message_ids == ["M05"]).final
    assert m05.responsible_department == Department.SALES
    assert m05.action_code == ActionCode.SALES_ENQUIRY_NO_QUOTE

    # M10 uncertain booking -> Duty Ops, awaiting_info, asks minimum identity
    m10 = next(i for i in run.issues if i.group.source_message_ids == ["M10"]).final
    assert m10.responsible_department == Department.DUTY_OPS
    assert m10.action_code == ActionCode.ASK_MINIMUM_BOOKING_IDENTITY
    assert m10.status == IssueStatus.AWAITING_INFO

    # First callback helper returns B101
    from app.schemas import IssueContext
    fc = first_callback([(i.final, IssueContext(group=i.group, messages=i.messages, booking=i.booking)) for i in run.issues])
    assert fc is not None and fc[1].group.booking_id == "B101"


def test_harder_cases_negation_and_contact_preference() -> None:
    snap = "2026-11-23 09:00"
    ing = ingest_files(HARDER_DIR / "booking_register.csv", HARDER_DIR / "shift_inbox.csv", parse_snapshot(snap))
    run = run_rules(ing, snap, version="v2", dataset="harder")
    by_msg = {i.group.source_message_ids[0]: i.final for i in run.issues}

    # H01 Hinglish care gap
    assert by_msg["H01"].action_code == ActionCode.CARE_GAP_IMMEDIATE
    assert by_msg["H01"].contact_channel == Channel.PHONE
    assert by_msg["H01"].urgency == Urgency.CRITICAL

    # H04 negated closure must remain OPEN service gap
    assert by_msg["H04"].action_code == ActionCode.SERVICE_GAP_CHECK_ARRIVAL
    assert by_msg["H04"].status == IssueStatus.OPEN

    # H06 critical care gap where customer can't take calls -> WhatsApp only!
    assert by_msg["H06"].action_code == ActionCode.CARE_GAP_IMMEDIATE
    assert by_msg["H06"].urgency == Urgency.CRITICAL
    assert by_msg["H06"].contact_channel == Channel.WHATSAPP


def test_unsupported_promise_detector_catches_all_violations() -> None:
    ing = ingest_files(SUPPLIED_BOOKINGS, SUPPLIED_INBOX, parse_snapshot("2026-11-23 09:00"))
    ctxs = {c.group.booking_id or c.group.source_message_ids[0]: c for c in group_messages(ing.messages, ing.bookings)}

    # Unconfirmed arrival / replacement ETA on B101
    f1 = find_unsupported_promises("She will arrive by 9:30 and a replacement is confirmed.", ctxs["B101"])
    assert any(f.kind == "arrival_or_replacement" for f in f1)

    # Unconfirmed schedule change on B104
    f2 = find_unsupported_promises("Your cook visit is now rescheduled and confirmed at 10:00.", ctxs["B104"])
    assert any(f.kind == "revised_time" for f in f2)

    # Disputed refund falsely confirmed on B103
    f3 = find_unsupported_promises("Your ₹8,000 refund is approved and will reach within 3 working days.", ctxs["B103"])
    kinds3 = {f.kind for f in f3}
    assert {"refund_approval", "payout_date"} <= kinds3

    # Invented quote price on M05
    f4 = find_unsupported_promises("A weekday cook costs ₹4,500 per month.", ctxs["M05"])
    assert any(f.kind == "amount" for f in f4)

    # Phone channel overriding don't call on B105
    f5 = find_unsupported_promises("Checking cover.", ctxs["B105"], channel=Channel.PHONE, contact_preference="whatsapp")
    assert any(f.kind == "contact_preference" for f in f5)

