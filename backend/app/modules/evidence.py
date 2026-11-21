"""Evidence validation and unsupported-promise detection.

Used (a) as a guardrail on AI drafts and (b) by the evaluator to count unsupported promises for
every method, including the rules baseline. Conservative regexes: a flag means 'a human should
look'; the evaluator report lists every hit so false positives are visible.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from app.schemas import BookingFacts, Channel, IssueContext

_AMOUNT = re.compile(r"(?:₹|rs\.?\s?|inr\s?)\s?([\d,]+(?:\.\d+)?)|\b([\d,]{3,})\s?(?:rupees|/-)", re.I)
_NEG = re.compile(r"\b(not|no|yet to|pending|under review|awaiting|isn't|hasn't|haven't|cannot|can't|unconfirmed|until)\b", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+")

ARRIVAL_PROMISE = re.compile(
    r"\b(will (arrive|reach|be there|be with you|come)|is on (her|his|the|their) way|on the way|arriving (at|by|in)|"
    r"(replacement|substitute|cover|backup)( \w+)? (is |has been )?(confirmed|arranged|assigned|found|booked)|"
    r"we have (arranged|found|assigned|confirmed) (a |an |the )?(replacement|substitute|cover|caregiver|nanny|helper|cook)|"
    r"(she|he|caregiver|nanny|helper|cook)( will| should)? (be there|reach|arrive) (by|at|in|within))", re.I)
SCHEDULE_PROMISE = re.compile(
    r"\b((is|has been|are) (now )?(re)?scheduled|(time|start|visit|slot) (is|has been) (changed|moved|confirmed|updated)|"
    r"we('ll| will) send (her|him|the cook|the helper) at|confirmed (for|at) \d|\d{1,2}(:\d{2})?\s?(am|pm)? is confirmed)", re.I)
REFUND_APPROVED = re.compile(r"\b(approved|has been approved|is approved|will be refunded|processed)\b", re.I)
PAYOUT_PROMISE = re.compile(
    r"\b(within \d+\s*(working |business )?(days?|hours?)|in \d+\s*(working |business )?days?|by (mon|tues|wednes|thurs|fri|satur|sun)day|"
    r"by tomorrow|by today|by end of (day|week)|on \d{1,2}(st|nd|rd|th)?\s*(nov|dec|jan)|will (reach|be credited|be paid) (on|by|within))", re.I)


class PromiseFinding(BaseModel):
    kind: str
    text: str
    reason: str


def _sentences(text: str) -> list[str]:
    return [s for s in _SENT.split(text or "") if s.strip()]


def find_unsupported_promises(draft: str | None, ctx: IssueContext, channel: Channel | None = None,
                              contact_preference: str | None = None) -> list[PromiseFinding]:
    out: list[PromiseFinding] = []
    f = ctx.booking.facts if ctx.booking else BookingFacts()
    billing = (ctx.booking.billing_record or "") if ctx.booking else ""
    if channel == Channel.PHONE and contact_preference == "whatsapp":
        out.append(PromiseFinding(kind="contact_preference", text="channel=phone", reason="Customer asked not to be called (R3)."))
    if not draft:
        return out
    allowed_amounts = {a.replace(",", "") for a, _ in _AMOUNT.findall(billing) if a} | \
                      {b.replace(",", "") for _, b in _AMOUNT.findall(billing) if b}
    for m in _AMOUNT.finditer(draft):
        amt = (m.group(1) or m.group(2) or "").replace(",", "")
        if amt and amt not in allowed_amounts:
            out.append(PromiseFinding(kind="amount", text=m.group(0), reason="Amount not recorded in the booking register (R5/R7)."))
    for sent in _sentences(draft):
        low = sent.lower()
        negated = bool(_NEG.search(low))
        if ARRIVAL_PROMISE.search(low) and not negated and not f.substitute_confirmed and not f.arrival_confirmed:
            out.append(PromiseFinding(kind="arrival_or_replacement", text=sent.strip(),
                                      reason="Arrival/replacement not confirmed by Sourcing in the register (R4)."))
        if SCHEDULE_PROMISE.search(low) and not negated:
            out.append(PromiseFinding(kind="revised_time", text=sent.strip(), reason="Revised start not confirmed by Sourcing (R4)."))
        if "refund" in low or "money" in low or "payment" in low:
            if REFUND_APPROVED.search(low) and not negated and f.refund_status != "approved":
                out.append(PromiseFinding(kind="refund_approval", text=sent.strip(), reason="Register does not record a refund approval (R5)."))
        if PAYOUT_PROMISE.search(low) and not f.payout_date_recorded:
            out.append(PromiseFinding(kind="payout_date", text=sent.strip(), reason="No payout date recorded in the register (R5/R6)."))
    return out


def validate_source_ids(ids: list[str], ctx: IssueContext) -> tuple[list[str], list[str]]:
    allowed = set(ctx.group.source_message_ids) | ({ctx.group.booking_id} if ctx.group.booking_id else set())
    valid = [i for i in ids if i in allowed]
    invalid = [i for i in ids if i not in allowed]
    return valid, invalid

