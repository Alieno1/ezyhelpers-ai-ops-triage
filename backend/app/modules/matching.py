"""Booking matching and deterministic fact extraction from the register.

The register is the authority for refunds, amounts, payout dates and confirmations.
These parsers are intentionally conservative: anything not explicitly recorded is ``None``/False.
"""
from __future__ import annotations

import re

from app.schemas import BookingFacts, BookingMatch, BookingRecord, Message

_AMOUNT = r"(?:₹|rs\.?\s?|inr\s?)\s?([\d,]+(?:\.\d+)?)"


def derive_booking_facts(operations: str | None, billing: str | None) -> BookingFacts:
    ops = (operations or "").lower()
    bill = (billing or "").lower()
    f = BookingFacts()
    f.booking_closed = "booking closed" in ops
    if "arrival unconfirmed" in ops or "arrival pending" in ops:
        f.arrival_confirmed = False
    elif re.search(r"\barrived\b|arrival confirmed", ops):
        f.arrival_confirmed = True
    if re.search(r"no substitute confirmed|no replacement confirmed", ops):
        f.substitute_confirmed = False
    elif re.search(r"substitute confirmed|replacement confirmed", ops):
        f.substitute_confirmed = True
    m = re.search(r"(\d{1,2}:\d{2}) start confirmed", ops)
    if m:
        f.confirmed_start_time = m.group(1)
    f.sourcing_checking = "sourcing is checking" in ops
    if re.search(r"refund approved", bill) and "no approval" not in bill:
        f.refund_status = "approved"
    elif re.search(r"under review|no approval", bill):
        f.refund_status = "under_review"
    m = re.search(_AMOUNT + r"\s+refund", bill)
    if m:
        f.refund_amount = "₹" + m.group(1)
    m = re.search(_AMOUNT + r"\s+payment", bill)
    if m:
        f.payment_amount = "₹" + m.group(1)
    if re.search(r"payout date pending|no [^.]*payout date", bill):
        f.payout_date_recorded = False
    else:
        m = re.search(r"payout (?:date )?(?:on |:)?\s*(\d{4}-\d{2}-\d{2}|\d{1,2} \w{3})", bill)
        if m:
            f.payout_date, f.payout_date_recorded = m.group(1), True
    return f


def match_booking(booking_id: str | None, messages: list[Message], bookings: list[BookingRecord]) -> BookingMatch:
    by_id: dict[str, BookingRecord] = {}
    for b in bookings:
        by_id.setdefault(b.booking_id, b)  # first row wins on duplicates (reported in DQ)
    if booking_id:
        if booking_id in by_id:
            return BookingMatch(status="matched", booking_id=booking_id, note=f"Exact booking_id match to register row {by_id[booking_id].row_number}.")
        return BookingMatch(status="unknown_reference", booking_id=booking_id,
                            note=f"{booking_id} is not in the register. Issue kept open; identity must be confirmed.")
    text = " ".join(m.text_normalised for m in messages)
    candidates = [b.booking_id for b in bookings if b.locality and _locality_mentioned(b.locality, text) and not b.facts.booking_closed]
    note = "No booking reference supplied."
    if candidates:
        note += (f" Locality mentioned matches {', '.join(candidates)}, but locality alone is insufficient to establish identity;"
                 " the issue is NOT linked to any booking.")
    return BookingMatch(status="no_reference", booking_id=None, possible_candidates=candidates, note=note)


def _locality_mentioned(locality: str, text: str) -> bool:
    loc = locality.lower()
    first = loc.split()[0]
    return loc in text or (len(first) >= 3 and re.search(rf"\b{re.escape(first)}\b", text) is not None)

