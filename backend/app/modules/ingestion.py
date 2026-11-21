"""CSV ingestion + data validation.

Responsibilities
* decode bytes (UTF-8, UTF-8 BOM, cp1252 fallback with a warning)
* detect missing columns, missing values, invalid formats, duplicates, orphan references
* keep the ORIGINAL cell strings (``raw``) next to the normalised typed values
* never drop a record: invalid rows are kept and reported
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.modules.matching import derive_booking_facts
from app.modules.normalisation import clean_cell, normalise_text
from app.schemas import BookingRecord, DQIssue, IngestResult, Message

BOOKING_COLUMNS = [
    "booking_id", "service", "locality", "scheduled_start_ist", "updated_at_ist", "operations_record", "billing_record",
]
INBOX_COLUMNS = ["event_id", "received_at_ist", "thread_id", "booking_id", "channel", "sender", "message"]
BOOKING_ID_RE = re.compile(r"^B\d{3,}$")
EVENT_ID_RE = re.compile(r"^[A-Z]\d{2,}$")
THREAD_ID_RE = re.compile(r"^[A-Z]\d{2,}$")
TS_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M")
INTERNAL_SENDERS = {"sales", "billing", "sourcing", "duty ops", "ops"}
MAX_ROWS = 5000


class IngestionError(ValueError):
    """Raised for unrecoverable file problems (empty file, wrong file, too large)."""


def decode_bytes(data: bytes, source: str, dq: list[DQIssue]) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        dq.append(DQIssue(source_file=source, record_id="(file)", field="(encoding)", original_value="UTF-8 BOM",
                          normalised_value="UTF-8", issue_type="encoding", problem="File starts with a UTF-8 byte-order mark; it was removed before parsing.",
                          severity="info", recommended_action="None required.", human_review_required=False))
        return data[3:].decode("utf-8")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        dq.append(DQIssue(source_file=source, record_id="(file)", field="(encoding)", original_value="non-UTF-8",
                          normalised_value="cp1252", issue_type="encoding", problem="File is not valid UTF-8; decoded as cp1252. Currency symbols may be wrong.",
                          severity="warning", recommended_action="Re-export the file as UTF-8.", human_review_required=True))
        return data.decode("cp1252", errors="replace")


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in TS_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _read_rows(text: str, source: str, expected: list[str], dq: list[DQIssue]) -> list[tuple[int, dict[str, str | None]]]:
    if not text.strip():
        raise IngestionError(f"{source}: file is empty")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        raise IngestionError(f"{source}: no header row")
    header_map = {h: (h or "").strip().lower() for h in reader.fieldnames}
    present = set(header_map.values())
    missing = [c for c in expected if c not in present]
    for col in missing:
        dq.append(DQIssue(source_file=source, record_id="(file)", field=col, original_value=None, issue_type="missing_column",
                          problem=f"Required column '{col}' is missing; every row will have no value for it.", severity="error",
                          recommended_action="Fix the export and re-import.", human_review_required=True))
    if len(missing) == len(expected):
        raise IngestionError(f"{source}: none of the expected columns {expected} were found")
    rows: list[tuple[int, dict[str, str | None]]] = []
    for i, row in enumerate(reader, start=2):  # row 1 is the header
        if i - 1 > MAX_ROWS:
            raise IngestionError(f"{source}: more than {MAX_ROWS} rows")
        extra = row.pop(None, None)  # type: ignore[call-overload]
        rec = {header_map.get(k, k): v for k, v in row.items()}
        if extra:
            dq.append(DQIssue(source_file=source, record_id=f"row {i}", field="(row)", original_value=str(extra), issue_type="invalid_format",
                              problem="Row has more cells than the header (unquoted comma?).", severity="warning",
                              recommended_action="Check quoting in the source export.", human_review_required=True))
        if all(not (v or "").strip() for v in rec.values()):
            continue  # blank line, nothing to keep
        rows.append((i, rec))
    return rows


def _note_whitespace(source: str, rid: str, field: str, raw: str | None, clean: str | None, dq: list[DQIssue]) -> None:
    if raw is not None and clean is not None and raw != clean:
        dq.append(DQIssue(source_file=source, record_id=rid, field=field, original_value=raw, normalised_value=clean, issue_type="normalised",
                          problem="Leading/trailing or repeated whitespace removed.", severity="info",
                          recommended_action="None; original value preserved in raw.", human_review_required=False))


def ingest_bookings(data: bytes, source: str = "booking_register.csv") -> tuple[list[BookingRecord], list[DQIssue]]:
    dq: list[DQIssue] = []
    rows = _read_rows(decode_bytes(data, source, dq), source, BOOKING_COLUMNS, dq)
    out: list[BookingRecord] = []
    seen: dict[str, int] = {}
    for row_no, rec in rows:
        raw = {c: rec.get(c) for c in BOOKING_COLUMNS}
        clean = {c: clean_cell(raw[c]) for c in BOOKING_COLUMNS}
        rid = clean["booking_id"] or f"row {row_no}"
        for c in BOOKING_COLUMNS:
            _note_whitespace(source, rid, c, raw[c], clean[c], dq)
        if not clean["booking_id"]:
            dq.append(DQIssue(source_file=source, record_id=rid, field="booking_id", original_value=raw["booking_id"], issue_type="missing_value",
                              problem="Booking row has no booking_id; it cannot be referenced.", severity="error",
                              recommended_action="Ask Ops to supply the booking ID.", human_review_required=True))
        elif not BOOKING_ID_RE.match(clean["booking_id"]):
            dq.append(DQIssue(source_file=source, record_id=rid, field="booking_id", original_value=raw["booking_id"], issue_type="invalid_format",
                              problem="booking_id does not match the expected pattern B<digits>.", severity="warning",
                              recommended_action="Confirm the ID with Ops.", human_review_required=True))
        if clean["booking_id"]:
            if clean["booking_id"] in seen:
                dq.append(DQIssue(source_file=source, record_id=rid, field="booking_id", original_value=raw["booking_id"], issue_type="duplicate",
                                  problem=f"Duplicate booking_id (also on row {seen[clean['booking_id']]}). Both rows kept; the later row is NOT used for lookups.",
                                  severity="error", recommended_action="Ops to confirm which row is authoritative.", human_review_required=True))
            else:
                seen[clean["booking_id"]] = row_no
        sched = parse_ts(clean["scheduled_start_ist"])
        upd = parse_ts(clean["updated_at_ist"])
        for field, val, parsed in (("scheduled_start_ist", clean["scheduled_start_ist"], sched), ("updated_at_ist", clean["updated_at_ist"], upd)):
            if val and parsed is None:
                dq.append(DQIssue(source_file=source, record_id=rid, field=field, original_value=raw[field], issue_type="invalid_format",
                                  problem="Timestamp could not be parsed (expected YYYY-MM-DD HH:MM IST).", severity="warning",
                                  recommended_action="Correct the timestamp in the register.", human_review_required=True))
        ops = clean["operations_record"] or ""
        if not clean["scheduled_start_ist"]:
            closed = "closed" in ops.lower()
            dq.append(DQIssue(source_file=source, record_id=rid, field="scheduled_start_ist", original_value=raw["scheduled_start_ist"], issue_type="missing_value",
                              problem=("No scheduled start recorded. Operations record says the booking is closed, so this is consistent (missing, not incorrect)."
                                       if closed else "No scheduled start recorded for an active booking."),
                              severity="info" if closed else "warning",
                              recommended_action="None." if closed else "Ops to add the scheduled start.", human_review_required=not closed))
        if not clean["billing_record"]:
            dq.append(DQIssue(source_file=source, record_id=rid, field="billing_record", original_value=raw["billing_record"], issue_type="missing_value",
                              problem="No billing record. This means no billing facts are available - it does NOT mean no payment or refund exists.",
                              severity="info", recommended_action="Do not state any billing fact for this booking.", human_review_required=False))
        if not clean["operations_record"]:
            dq.append(DQIssue(source_file=source, record_id=rid, field="operations_record", original_value=raw["operations_record"], issue_type="missing_value",
                              problem="No operations record.", severity="warning", recommended_action="Ops to update the register.", human_review_required=True))
        out.append(BookingRecord(
            booking_id=clean["booking_id"] or f"UNKNOWN-row{row_no}", service=clean["service"], locality=clean["locality"],
            scheduled_start_ist=sched, updated_at_ist=upd, operations_record=clean["operations_record"],
            billing_record=clean["billing_record"], raw=raw, row_number=row_no,
            facts=derive_booking_facts(clean["operations_record"], clean["billing_record"]),
        ))
    return out, dq


def ingest_inbox(data: bytes, source: str = "shift_inbox.csv") -> tuple[list[Message], list[DQIssue]]:
    dq: list[DQIssue] = []
    rows = _read_rows(decode_bytes(data, source, dq), source, INBOX_COLUMNS, dq)
    out: list[Message] = []
    seen_ids: dict[str, int] = {}
    seen_text: dict[tuple[str | None, str], str] = {}
    prev_ts: datetime | None = None
    for row_no, rec in rows:
        raw = {c: rec.get(c) for c in INBOX_COLUMNS}
        clean = {c: clean_cell(raw[c]) for c in INBOX_COLUMNS}
        rid = clean["event_id"] or f"row {row_no}"
        for c in INBOX_COLUMNS:
            if c != "message":
                _note_whitespace(source, rid, c, raw[c], clean[c], dq)
        if not clean["event_id"]:
            dq.append(DQIssue(source_file=source, record_id=rid, field="event_id", original_value=raw["event_id"], issue_type="missing_value",
                              problem="Message has no event_id; a synthetic ID was assigned for traceability.", severity="error",
                              recommended_action="Fix the export.", human_review_required=True))
            clean["event_id"] = f"ROW{row_no:03d}"
        elif not EVENT_ID_RE.match(clean["event_id"]):
            dq.append(DQIssue(source_file=source, record_id=rid, field="event_id", original_value=raw["event_id"], issue_type="invalid_format",
                              problem="event_id does not match the expected pattern (letter + digits).", severity="warning",
                              recommended_action="Confirm the ID.", human_review_required=False))
        if clean["event_id"] in seen_ids:
            dq.append(DQIssue(source_file=source, record_id=rid, field="event_id", original_value=raw["event_id"], issue_type="duplicate",
                              problem=f"Duplicate event_id (also row {seen_ids[clean['event_id']]}). Kept with suffix for traceability.",
                              severity="error", recommended_action="Check whether the message was exported twice.", human_review_required=True))
            clean["event_id"] = f"{clean['event_id']}-dup{row_no}"
        seen_ids.setdefault(clean["event_id"], row_no)
        ts = parse_ts(clean["received_at_ist"])
        if not clean["received_at_ist"]:
            dq.append(DQIssue(source_file=source, record_id=rid, field="received_at_ist", original_value=raw["received_at_ist"], issue_type="missing_value",
                              problem="No received time; chronology falls back to file order.", severity="warning",
                              recommended_action="Check the channel log for the time.", human_review_required=True))
        elif ts is None:
            dq.append(DQIssue(source_file=source, record_id=rid, field="received_at_ist", original_value=raw["received_at_ist"], issue_type="invalid_format",
                              problem="Timestamp could not be parsed; chronology falls back to file order.", severity="warning",
                              recommended_action="Correct the timestamp.", human_review_required=True))
        if ts and prev_ts and ts < prev_ts:
            dq.append(DQIssue(source_file=source, record_id=rid, field="received_at_ist", original_value=raw["received_at_ist"], issue_type="chronology",
                              problem="Message is earlier than the previous row; file is not in arrival order. Messages are re-sorted by time.",
                              severity="info", recommended_action="None.", human_review_required=False))
        prev_ts = ts or prev_ts
        if clean["thread_id"] and not THREAD_ID_RE.match(clean["thread_id"]):
            dq.append(DQIssue(source_file=source, record_id=rid, field="thread_id", original_value=raw["thread_id"], issue_type="invalid_format",
                              problem="thread_id has an unexpected format.", severity="info", recommended_action="None.", human_review_required=False))
        if clean["booking_id"] and not BOOKING_ID_RE.match(clean["booking_id"]):
            dq.append(DQIssue(source_file=source, record_id=rid, field="booking_id", original_value=raw["booking_id"], issue_type="invalid_format",
                              problem="booking_id does not match B<digits>; treated as an unverified reference.", severity="warning",
                              recommended_action="Confirm the booking with the customer.", human_review_required=True))
        text = raw["message"] or ""
        if not text.strip():
            dq.append(DQIssue(source_file=source, record_id=rid, field="message", original_value=raw["message"], issue_type="missing_value",
                              problem="Empty message body.", severity="warning", recommended_action="Check the original channel.", human_review_required=True))
        sender = clean["sender"]
        if not sender:
            dq.append(DQIssue(source_file=source, record_id=rid, field="sender", original_value=raw["sender"], issue_type="missing_value",
                              problem="Sender missing; treated as an unknown external sender.", severity="warning",
                              recommended_action="Check the channel log.", human_review_required=True))
        norm = normalise_text(text)
        key = (clean["thread_id"], norm)
        if norm and key in seen_text:
            dq.append(DQIssue(source_file=source, record_id=rid, field="message", original_value=text, issue_type="duplicate",
                              problem=f"Same text as {seen_text[key]} in the same thread (possible double send). Kept; grouped into the same issue.",
                              severity="warning", recommended_action="Treat as one request.", human_review_required=False))
        else:
            seen_text[key] = clean["event_id"]
        is_internal = (sender or "").strip().lower() in INTERNAL_SENDERS or "handoff" in (clean["channel"] or "").lower() \
            or "note" in (clean["channel"] or "").lower()
        out.append(Message(event_id=clean["event_id"], received_at_ist=ts, thread_id=clean["thread_id"], booking_id=clean["booking_id"],
                           channel=clean["channel"], sender=sender, message=text.strip(), text_normalised=norm,
                           is_internal=is_internal, raw=raw, row_number=row_no))
    return out, dq


def cross_validate(bookings: list[BookingRecord], messages: list[Message], snapshot: datetime | None) -> list[DQIssue]:
    """Checks that need both files: orphan references, missing references, stale register rows."""
    dq: list[DQIssue] = []
    known = {b.booking_id for b in bookings}
    by_id = {b.booking_id: b for b in bookings}
    threads_by_booking: dict[str, set[str]] = {}
    for m in messages:
        if m.booking_id:
            threads_by_booking.setdefault(m.booking_id, set()).add(m.thread_id or "?")
            if m.booking_id not in known:
                dq.append(DQIssue(source_file="shift_inbox.csv", record_id=m.event_id, field="booking_id", original_value=m.raw.get("booking_id"),
                                  issue_type="orphan_reference", problem=f"Booking {m.booking_id} is not in the booking register.",
                                  severity="warning", recommended_action="Keep the issue open; confirm the booking with the customer.", human_review_required=True))
        else:
            ext = (m.sender or "").lower() == "prospect"
            dq.append(DQIssue(source_file="shift_inbox.csv", record_id=m.event_id, field="booking_id", original_value=m.raw.get("booking_id"),
                              issue_type="missing_value",
                              problem=("No booking reference - expected for a prospect's new enquiry." if ext else
                                       "No booking reference from an existing customer; booking identity is unknown and must not be guessed."),
                              severity="info" if ext else "warning",
                              recommended_action="Route to Sales." if ext else "Ask the customer for the booking number or registered phone number.",
                              human_review_required=not ext))
        if snapshot and m.received_at_ist and m.received_at_ist > snapshot:
            dq.append(DQIssue(source_file="shift_inbox.csv", record_id=m.event_id, field="received_at_ist", original_value=m.raw.get("received_at_ist"),
                              issue_type="chronology", problem="Message arrived after the shift snapshot time.", severity="info",
                              recommended_action="Include in the next queue refresh.", human_review_required=False))
    for bid, threads in threads_by_booking.items():
        if len(threads) > 1:
            dq.append(DQIssue(source_file="shift_inbox.csv", record_id=bid, field="thread_id", original_value=", ".join(sorted(threads)),
                              issue_type="cross_reference", problem=f"Booking {bid} appears in {len(threads)} threads ({', '.join(sorted(threads))}). Grouped into one issue by booking ID.",
                              severity="info", recommended_action="None; the grouping reason is shown on the issue.", human_review_required=False))
    for b in bookings:
        if snapshot and b.updated_at_ist and b.scheduled_start_ist and b.updated_at_ist < b.scheduled_start_ist <= snapshot \
                and b.facts.arrival_confirmed is not True:
            hours = (snapshot - b.updated_at_ist).total_seconds() / 3600
            dq.append(DQIssue(source_file="booking_register.csv", record_id=b.booking_id, field="updated_at_ist", original_value=b.raw.get("updated_at_ist"),
                              issue_type="reconciliation",
                              problem=f"Register row last updated {hours:.0f}h before the snapshot, before the {b.scheduled_start_ist:%H:%M} start. Arrival status may be stale.",
                              severity="warning", recommended_action="Duty Ops to check live arrival status before relying on the register.", human_review_required=True))
        later_customer = [m for m in messages if m.booking_id == b.booking_id and m.received_at_ist and b.updated_at_ist
                          and m.received_at_ist > b.updated_at_ist and not m.is_internal]
        if later_customer and b.facts.arrival_confirmed is False:
            ids = ", ".join(m.event_id for m in later_customer)
            dq.append(DQIssue(source_file="booking_register.csv", record_id=b.booking_id, field="operations_record", original_value=b.operations_record,
                              issue_type="reconciliation", problem=f"Customer messages ({ids}) arrived after the last register update; the register may not reflect them.",
                              severity="info", recommended_action="Update the register after the issue is handled.", human_review_required=False))
    _ = by_id
    return dq


def ingest(bookings_bytes: bytes, inbox_bytes: bytes, snapshot: datetime | None = None) -> IngestResult:
    bookings, dq_b = ingest_bookings(bookings_bytes)
    messages, dq_m = ingest_inbox(inbox_bytes)
    dq = dq_b + dq_m + cross_validate(bookings, messages, snapshot)
    files: dict[str, dict[str, Any]] = {
        "booking_register.csv": {"rows": len(bookings), "bytes": len(bookings_bytes)},
        "shift_inbox.csv": {"rows": len(messages), "bytes": len(inbox_bytes)},
    }
    return IngestResult(bookings=bookings, messages=messages, dq_issues=dq, files=files)


def ingest_files(bookings_path: Path, inbox_path: Path, snapshot: datetime | None = None) -> IngestResult:
    return ingest(bookings_path.read_bytes(), inbox_path.read_bytes(), snapshot)

