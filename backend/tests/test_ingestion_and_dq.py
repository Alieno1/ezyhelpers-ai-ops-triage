"""Tests for CSV ingestion, UTF-8 BOM, normalisation, and data quality reporting."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.ingestion import IngestionError, ingest, ingest_bookings, ingest_files, ingest_inbox
from app.pipeline import parse_snapshot

PROJECT_DIR = Path(__file__).resolve().parents[2]
SUPPLIED_BOOKINGS = PROJECT_DIR / "shift_data" / "booking_register.csv"
SUPPLIED_INBOX = PROJECT_DIR / "shift_data" / "shift_inbox.csv"


def test_supplied_csvs_utf8_bom_and_record_preservation() -> None:
    snap = parse_snapshot("2026-11-23 09:00")
    res = ingest_files(SUPPLIED_BOOKINGS, SUPPLIED_INBOX, snap)
    assert len(res.bookings) == 6
    assert len(res.messages) == 12
    encoding_issues = [d for d in res.dq_issues if d.issue_type == "encoding"]
    assert len(encoding_issues) == 2  # both supplied CSVs start with UTF-8 BOM
    # B103 and B106 are closed and have no scheduled_start_ist -> missing, not error
    b103_sched = [d for d in res.dq_issues if d.record_id == "B103" and d.field == "scheduled_start_ist"]
    assert len(b103_sched) == 1 and b103_sched[0].severity == "info" and not b103_sched[0].human_review_required
    # M10 missing booking_id from Customer -> warning + human_review_required
    m10_dq = [d for d in res.dq_issues if d.record_id == "M10" and d.field == "booking_id"]
    assert len(m10_dq) == 1 and m10_dq[0].severity == "warning" and m10_dq[0].human_review_required


def test_missing_columns_and_empty_files() -> None:
    with pytest.raises(IngestionError):
        ingest_bookings(b"   \n")
    with pytest.raises(IngestionError):
        ingest_inbox(b"col1,col2\n1,2\n")

    # Partial missing column keeps records and reports missing_column error
    bad_b = b"booking_id,service,locality\nB999,Cooking,HSR Layout\n"
    bookings, dq = ingest_bookings(bad_b)
    assert len(bookings) == 1
    assert any(d.issue_type == "missing_column" and d.severity == "error" for d in dq)


def test_invalid_timestamps_duplicates_orphans_and_whitespace() -> None:
    b_csv = (
        "booking_id,service,locality,scheduled_start_ist,updated_at_ist,operations_record,billing_record\n"
        " B101 ,Cooking,HSR Layout,not-a-date,2026-11-22 18:00,Helper assigned.,\n"
        "B101,Cooking,HSR Layout,2026-11-23 08:00,2026-11-22 18:00,Duplicate row.,\n"
        "BADID,Housekeeping,,2026-11-23 09:00,, ,\n"
    ).encode("utf-8")
    i_csv = (
        "event_id,received_at_ist,thread_id,booking_id,channel,sender,message\n"
        "M02,2026-11-23 08:30,T01,B999,WhatsApp,Customer,Second chronologically but first in file\n"
        "M01,2026-11-23 08:15,T01,B101,WhatsApp,Customer,  First   chronologically  \n"
        "M01,2026-11-23 08:16,T01,B101,WhatsApp,Customer,  First   chronologically  \n"
        "M03,bad-ts,T02,,WhatsApp,,\n"
    ).encode("utf-8")

    res = ingest(b_csv, i_csv, parse_snapshot("2026-11-23 09:00"))
    # Never drop invalid or duplicate rows
    assert len(res.bookings) == 3
    assert len(res.messages) == 4
    types = {d.issue_type for d in res.dq_issues}
    assert {"normalised", "duplicate", "invalid_format", "missing_value", "chronology", "orphan_reference"} <= types
    # Raw value preserved untouched while normalised copy cleaned
    first_b = res.bookings[0]
    assert first_b.raw["booking_id"] == " B101 "
    assert first_b.booking_id == "B101"


def test_non_utf8_fallback_encoding() -> None:
    b_csv = "booking_id,service,locality,scheduled_start_ist,updated_at_ist,operations_record,billing_record\nB101,Cooking,HSR,2026-11-23 08:00,2026-11-23 08:00,OK,\xa3100\n".encode("latin-1")
    bookings, dq = ingest_bookings(b_csv)
    assert len(bookings) == 1
    assert any(d.issue_type == "encoding" and d.severity == "warning" and d.human_review_required for d in dq)

