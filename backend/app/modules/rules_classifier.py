"""Rules-only interpretation of an issue (the baseline 'signal extractor').

Deliberately simple and transparent: English keyword patterns + regexes for times.
Versioned so the improvement step can be compared honestly (v1 is the frozen baseline).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.schemas import BookingRecord, Category, IssueContext, Message, Signals

CARE_SERVICES = {"elder companionship", "childcare", "elder care", "nanny", "patient care"}

KEYWORDS_V1: dict[str, list[str]] = {
    "enquiry": [r"\bcost\b", r"\bprice\b", r"\bquote\b", r"\brates?\b", r"\bhow much\b", r"\bcharges?\b"],
    "refund": [r"\brefund"],
    "arrived": [r"\bhere now\b", r"\bhas arrived\b", r"\barrived\b", r"\ball sorted\b", r"\bplease close\b"],
    "gap": [r"nobody has come", r"no one (has )?come", r"has ?n[o']t (come|started|arrived)", r"hasn'?t (come|started|arrived)",
            r"didn'?t (come|turn up)", r"\bnot (come|arrived|started)\b", r"\bmissed\b", r"\bis out\b", r"\bunavailable\b",
            r"\bon leave\b", r"\bno[- ]?show\b"],
    "schedule": [r"\binstead of\b", r"\breschedul", r"\bchange (the )?(time|timing|slot)\b", r"\bmove (it |the booking |the visit )?to\b",
                 r"\bpostpone\b"],
    "cover": [r"\bcan cover\b", r"\bcover(ing)? (until|till)\b", r"\bis with (the|him|her)\b"],
    "no_call": [r"don'?t call", r"do not call", r"\bno calls?\b", r"whatsapp me", r"message me", r"text me", r"only whatsapp",
                r"can'?t take calls"],
    "call": [r"\bcall me\b", r"\bplease call\b", r"\bcallback\b", r"\bcall back\b"],
    "today": [r"\btoday\b", r"\bnow\b", r"\bthis morning\b"],
    "claim_approved": [r"refund (was |is |has been )?approved", r"\bit was approved\b", r"\bapproved\b"],
}

# Targeted Hinglish improvement (v2) added after evaluating v1 against expected_actions.json:
# fixes Hinglish schedule change requests (e.g. M04 "ki jagah 10 baje bhej sakte ho")
# and Hinglish care/service gap & callback phrasing (e.g. H01 "nahi aayi", "call karo").
KEYWORDS_V2: dict[str, list[str]] = {k: list(v) for k, v in KEYWORDS_V1.items()}
KEYWORDS_V2["schedule"] += [r"\bki jagah\b", r"\bbaje\b.*\b(bhej|bulao|aana)", r"\b(bhej|bulao) sakte\b"]
KEYWORDS_V2["gap"] += [r"\bnahi aay[ie]\b", r"\bnahi aaya\b", r"\babhi tak nahi\b"]
KEYWORDS_V2["call"] += [r"\bcall karo\b", r"\bphone karo\b"]

KEYWORD_SETS = {"v1": KEYWORDS_V1, "v2": KEYWORDS_V2}
NEGATED_CLOSURE = re.compile(r"(don'?t|do not|not) (close|sorted)|still (hasn'?t|has not|not) (come|arrived)|not (here|arrived) yet")

_TIME = re.compile(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b")
_REL = re.compile(r"\bin (\d{1,3}) (minutes|mins|min|hours|hrs|hour)\b")


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def is_care_service(booking: BookingRecord | None) -> bool:
    return bool(booking and booking.service and booking.service.lower() in CARE_SERVICES)


def _to_hhmm(h: str, mm: str | None, ampm: str | None) -> str | None:
    hour = int(h)
    minute = int(mm) if mm else 0
    if ampm == "pm" and hour < 12:
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


_TIME_AFTER = re.compile(r"\b(at|by|before|until|till)\s+(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?")
_TIME_TAK = re.compile(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\s+(?:baje\s+)?tak\b")


def future_times(text: str, received: datetime | None, words: tuple[str, ...] = ("at", "by", "before", "until", "till")) -> list[str]:
    """All clock times introduced by the given words that are later than the message time."""
    out: list[str] = []
    for m in _TIME_AFTER.finditer(text):
        if m.group(1) in words:
            t = _to_hhmm(m.group(2), m.group(3), m.group(4))
            if t:
                out.append(t)
    for m in _TIME_TAK.finditer(text):
        t = _to_hhmm(m.group(1), m.group(2), m.group(3))
        if t:
            out.append(t)
    if received:
        out = [t for t in out if t > received.strftime("%H:%M")]
    return sorted(set(out))


def relative_deadline(text: str, received: datetime | None) -> str | None:
    m = _REL.search(text)
    if not (m and received):
        return None
    n = int(m.group(1))
    delta = timedelta(hours=n) if m.group(2).startswith("h") else timedelta(minutes=n)
    return (received + delta).strftime("%H:%M")


def detect_no_call(text: str) -> bool:
    return _any(KEYWORDS_V1["no_call"], text)


def rules_signals(ctx: IssueContext, version: str = "v1") -> Signals:
    kw = KEYWORD_SETS[version]
    msgs = ctx.messages
    ext: list[Message] = [m for m in msgs if not m.is_internal]
    all_text = " ".join(m.text_normalised for m in msgs)
    ext_text = " ".join(m.text_normalised for m in ext) or all_text
    first_sender = (msgs[0].sender or "").lower() if msgs else ""
    booking = ctx.booking
    has_booking = ctx.group.booking_match.status == "matched"

    pref = "no_preference"
    if _any(kw["no_call"], all_text):
        pref = "whatsapp"
    elif _any(kw["call"], all_text):
        pref = "phone"

    cover = "not_applicable"
    cover_until = None
    deadline = None
    for m in msgs:
        t = m.text_normalised
        if _any(kw["cover"], t):
            cover = "yes"
            cover_until = (future_times(t, m.received_at_ist, ("until", "till")) or [cover_until])[0]
        cands = future_times(t, m.received_at_ist) + [x for x in [relative_deadline(t, m.received_at_ist)] if x]
        if cands:
            deadline = min([deadline, *cands]) if deadline else min(cands)
    refund_claim = _any(kw["claim_approved"], ext_text) and _any(kw["refund"], ext_text)

    if first_sender == "prospect" or (not has_booking and _any(kw["enquiry"], ext_text) and not _any(kw["refund"], ext_text)):
        cat, intent = Category.NEW_ENQUIRY, "New enquiry asking about price/availability."
    elif not has_booking:
        cat, intent = Category.UNIDENTIFIED_BOOKING, "Existing customer without a usable booking reference."
    elif _any(kw["refund"], ext_text):
        cat, intent = Category.REFUND_QUERY, "Asking about refund status / payout."
    else:
        gap = _any(kw["gap"], ext_text)
        last_ext = ext[-1].text_normalised if ext else ""
        arrived_later = len(ext) > 1 and _any(kw["arrived"], last_ext) and not NEGATED_CLOSURE.search(last_ext)
        if arrived_later or (not gap and _any(kw["arrived"], last_ext) and not NEGATED_CLOSURE.search(last_ext)):
            cat, intent = Category.ARRIVAL_CONFIRMED, "Family confirmed the helper arrived; asked to close."
        elif gap:
            care = is_care_service(booking)
            cat = Category.CARE_GAP if care else Category.SERVICE_GAP
            intent = "Scheduled carer has not arrived / is unavailable; needs help." if care else "Scheduled service has not started."
            if care and cover == "not_applicable":
                cover = "no" if re.search(r"\balone\b|\bakeli\b|\bakela\b", all_text) else "unknown"
        elif _any(kw["schedule"], ext_text):
            cat, intent = Category.SCHEDULE_CHANGE, "Wants to change the start time of a booked visit."
        else:
            cat, intent = Category.OTHER, "Could not be classified by keyword rules."
    if cat != Category.CARE_GAP:
        cover = "not_applicable"
    requested_change: str | None = None
    if version == "v2" and cat == Category.SCHEDULE_CHANGE:
        m_req = re.search(r"ki jagah\s+(\d{1,2})(?:[:.](\d{2}))?\s*(?:baje\s*)?(am|pm)?", ext_text)
        if m_req:
            requested_change = _to_hhmm(m_req.group(1), m_req.group(2), m_req.group(3))
    return Signals(issue_category=cat, customer_intent=intent, resolved_by_customer=cat == Category.ARRIVAL_CONFIRMED,
                   cover_available=cover, cover_until=cover_until if cat == Category.CARE_GAP else None, deadline=deadline,
                   contact_preference=pref, refund_claimed_approved=refund_claim,
                   mentions_today=_any(kw["today"], ext_text), requested_change=requested_change, source="rules")
