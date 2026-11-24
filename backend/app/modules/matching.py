"""Booking matching and deterministic fact extraction from the register.

The register is the authority for refunds, amounts, payout dates and confirmations.
These parsers are intentionally conservative: anything not explicitly recorded is ``None``/False.
"""
from __future__ import annotations

import re

from app.schemas import BookingFacts, BookingMatch, BookingRecord, Message

_AMOUNT = r"(?:₹|rs\.?\s?|inr\s?)\s?([\d,]+(?:\.\d+)?)"
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"


def _extract_payment_amount(bill: str) -> str | None:
    patterns = (
        _AMOUNT + r"\s+(?:original\s+)?(?:payment|paid|deposit|advance|received|collected)\b",
        r"\b(?:original\s+payment|payment\s+(?:received|of|amount)?|amount\s+paid|paid(?:\s+amount)?|total\s+paid|deposited)\s*(?:is|of|was|:|-)?\s*" + _AMOUNT,
    )
    for pat in patterns:
        m = re.search(pat, bill)
        if m:
            return "₹" + m.group(1)
    return None


def _extract_refund_amount(bill: str) -> str | None:
    patterns = (
        _AMOUNT + r"\s+(?:partial\s+|approved\s+|eligible\s+)?refund\b",
        r"\b(?:approved\s+refund|partial\s+refund|refund\s+(?:approved|amount|sanctioned|eligible|of)?)\s*(?:is|of|for|was|:|-)?\s*" + _AMOUNT,
    )
    for pat in patterns:
        m = re.search(pat, bill)
        if m:
            return "₹" + m.group(1)
    return None


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

    # Extract amounts associated with their explicit billing role (never first/largest blindly).
    f.payment_amount = _extract_payment_amount(bill)
    f.refund_amount = _extract_refund_amount(bill)

    # Determine refund status while detecting negations, rejections, pending states, and ambiguity.
    has_rejected = bool(re.search(
        r"\b(refund\s+(?:is\s+|was\s+|has\s+been\s+)?(?:rejected|denied|declined)|not\s+eligible\s+for\s+(?:a\s+)?refund|no\s+refund\s+(?:approved|applicable|eligible))\b",
        bill,
    ))
    has_no_approval = bool(re.search(
        r"\b(no\s+approval|not\s+(?:yet\s+)?approved|unapproved|approval\s+pending|awaiting\s+approval)\b",
        bill,
    ))
    has_under_review = bool(re.search(
        r"\b(under\s+review|being\s+reviewed|in\s+review|verifying|being\s+checked)\b",
        bill,
    ))
    has_pending_refund = bool(re.search(
        r"\brefund\s+(?:status\s+)?(?:is\s+)?pending\b|\bpending\s+refund\b",
        bill,
    ))
    has_approved = bool(re.search(
        r"\b(?:refund(?:\s+(?:of|for)\s+(?:rs\.?\s*|inr\s*|₹)?[\d,]+(?:\.\d+)?)?\s+(?:is\s+|was\s+|has\s+been\s+)?(?:approved|sanctioned)|approved\s+refund)\b",
        bill,
    )) and not has_no_approval
    has_ambiguous_words = bool(re.search(
        r"\b(unclear|ambiguous|tbd|unknown|incomplete|discrepancy|confirm\s+with\s+billing|check\s+with\s+billing)\b",
        bill,
    ))

    if (has_approved and (has_rejected or has_under_review)) or has_ambiguous_words:
        f.refund_status = "ambiguous"
        f.billing_ambiguous = True
        f.billing_ambiguity_reason = "Billing record contains conflicting or unclear refund information."
    elif has_rejected:
        f.refund_status = "rejected"
    elif has_approved:
        f.refund_status = "approved"
        if not f.refund_amount:
            f.billing_ambiguous = True
            f.billing_ambiguity_reason = "Billing record states refund is approved but does not specify the approved refund amount."
    elif has_under_review or has_no_approval:
        f.refund_status = "under_review"
    elif has_pending_refund:
        f.refund_status = "pending"
    elif "refund" in bill:
        f.refund_status = "ambiguous"
        f.billing_ambiguous = True
        f.billing_ambiguity_reason = "Billing record mentions a refund without a clear approval status."
    elif bill.strip() and not f.payment_amount and not f.refund_amount:
        f.refund_status = "ambiguous"
        f.billing_ambiguous = True
        f.billing_ambiguity_reason = "Billing record is incomplete or cannot be parsed unambiguously."

    if re.search(r"payout(?:\s+date)?\s*(?:is|:|-)?\s*(?:pending|tbd|unconfirmed|not\s+(?:yet\s+)?(?:confirmed|recorded|set))|no\s+[^.]*payout\s+date", bill):
        f.payout_date_recorded = False
    else:
        m = re.search(
            rf"payout(?:\s+date)?\s*(?:on|by|:|-|is)?\s*(\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}\s+{_MONTH}(?:\s+\d{{4}})?|{_MONTH}\s+\d{{1,2}}(?:,?\s+\d{{4}})?)",
            bill,
        )
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

