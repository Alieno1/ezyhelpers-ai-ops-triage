"""Tests for deterministic message grouping, chronology sorting, and booking matching."""
from __future__ import annotations

from pathlib import Path

from app.modules.grouping import group_messages
from app.modules.ingestion import ingest, ingest_files
from app.pipeline import parse_snapshot

PROJECT_DIR = Path(__file__).resolve().parents[2]
SUPPLIED_BOOKINGS = PROJECT_DIR / "assignment_data" / "booking_register.csv"
SUPPLIED_INBOX = PROJECT_DIR / "assignment_data" / "shift_inbox.csv"


def test_supplied_inbox_groups_into_eight_issues_and_merges_sales_handoff() -> None:
    ing = ingest_files(SUPPLIED_BOOKINGS, SUPPLIED_INBOX, parse_snapshot("2026-11-23 09:00"))
    ctxs = group_messages(ing.messages, ing.bookings)
    assert len(ctxs) == 8

    by_msgs = {tuple(c.group.source_message_ids): c for c in ctxs}
    assert ("M01", "M07") in by_msgs  # T01 + S11 merged via B101
    assert ("M02", "M08") in by_msgs
    assert ("M03", "M09") in by_msgs
    assert ("M04",) in by_msgs
    assert ("M05",) in by_msgs
    assert ("M06", "M12") in by_msgs
    assert ("M10",) in by_msgs
    assert ("M11",) in by_msgs

    b101_ctx = by_msgs[("M01", "M07")]
    assert b101_ctx.group.booking_id == "B101"
    assert set(b101_ctx.group.thread_ids) == {"T01", "S11"}
    assert b101_ctx.booking is not None and b101_ctx.booking.booking_id == "B101"


def test_m10_locality_does_not_auto_link_booking() -> None:
    ing = ingest_files(SUPPLIED_BOOKINGS, SUPPLIED_INBOX, parse_snapshot("2026-11-23 09:00"))
    ctxs = group_messages(ing.messages, ing.bookings)
    m10 = next(c for c in ctxs if c.group.source_message_ids == ["M10"])
    assert m10.booking is None
    assert m10.group.booking_id is None
    assert m10.group.booking_match.status == "no_reference"
    assert set(m10.group.booking_match.possible_candidates) == {"B101", "B104"}


def test_chronology_sorting_and_conflicting_thread_booking_split() -> None:
    b_csv = (
        "booking_id,service,locality,scheduled_start_ist,updated_at_ist,operations_record,billing_record\n"
        "B101,Cooking,HSR,2026-11-23 08:00,2026-11-23 07:00,Assigned.,\n"
        "B102,Cooking,HSR,2026-11-23 09:00,2026-11-23 07:00,Assigned.,\n"
    ).encode("utf-8")
    i_csv = (
        "event_id,received_at_ist,thread_id,booking_id,channel,sender,message\n"
        "M02,2026-11-23 08:20,T01,B101,WhatsApp,Customer,Arrived now\n"
        "M01,2026-11-23 08:05,T01,B101,WhatsApp,Customer,Not arrived yet\n"
        "M03,2026-11-23 08:25,T01,B102,WhatsApp,Customer,Different booking in same thread\n"
        "M04,2026-11-23 08:30,T09,B999,WhatsApp,Customer,Unknown booking ref\n"
    ).encode("utf-8")
    ing = ingest(b_csv, i_csv, parse_snapshot("2026-11-23 09:00"))
    ctxs = group_messages(ing.messages, ing.bookings)
    assert len(ctxs) == 3
    assert ctxs[0].group.source_message_ids == ["M01", "M02"]  # re-sorted chronologically!
    assert ctxs[1].group.booking_id == "B102"  # split from T01 because different booking
    assert ctxs[2].group.booking_match.status == "unknown_reference"
    assert ctxs[2].booking is None

