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
REFUND_APPROVED = re.compile(r"\b(approved|has been approved|is approved|will be refunded|processed|sanctioned)\b", re.I)
PAYOUT_PROMISE = re.compile(
    r"\b(within \d+\s*(working |business )?(days?|hours?)|in \d+\s*(working |business )?days?|by (mon|tues|wednes|thurs|fri|satur|sun)day|"
    r"(by |on )?(tomorrow|today|tonight|next week|this week)|by end of (day|week)|"
    r"on \d{1,2}(st|nd|rd|th)?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)|"
    r"will (reach|be credited|be paid|be processed|arrive) (on|by|within|tomorrow|today|next))",
    re.I,
)
_REFUND_CTX = re.compile(r"\b(refund|refunded|reimburse|reimbursement|credit\s+back|money\s+back)\b", re.I)
_PAYMENT_CTX = re.compile(r"\b(original\s+payment|payment|paid|receipt|deposit|deposited)\b", re.I)


class PromiseFinding(BaseModel):
    kind: str
    text: str
    reason: str


def _sentences(text: str) -> list[str]:
    return [s for s in _SENT.split(text or "") if s.strip()]


def _norm_amount(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"[^\d.]", "", raw)
    if not cleaned:
        return None
    if "." in cleaned:
        cleaned = cleaned.rstrip("0").rstrip(".")
    return cleaned or None


def validate_refund_draft(draft: str | None, facts: BookingFacts, billing_record: str | None = None) -> list[PromiseFinding]:
    """Deterministic refund validation against authoritative BookingFacts.

    Distinguishes original payment from approved refund, verifies refund status,
    blocks unsupported payout promises, and flags ambiguous/incomplete billing records.
    """
    out: list[PromiseFinding] = []
    if not draft:
        return out

    billing = billing_record or ""
    recorded_amounts = {
        a for a in (
            _norm_amount(facts.refund_amount),
            _norm_amount(facts.payment_amount),
            *(_norm_amount(a or b) for a, b in _AMOUNT.findall(billing)),
        )
        if a
    }
    approved_refund_amt = _norm_amount(facts.refund_amount)
    original_payment_amt = _norm_amount(facts.payment_amount)

    for sent in _sentences(draft):
        low = sent.lower()
        negated = bool(_NEG.search(low))
        is_refund_sent = bool(_REFUND_CTX.search(low))
        claims_approval = bool(REFUND_APPROVED.search(low)) and not negated

        # 1. Approval status & billing ambiguity verification (R5/R6)
        if (is_refund_sent or "money" in low or "payment" in low) and claims_approval:
            if facts.billing_ambiguous or facts.refund_status == "ambiguous":
                out.append(PromiseFinding(
                    kind="billing_ambiguous",
                    text=sent.strip(),
                    reason=(
                        f"Billing record is incomplete or ambiguous ({facts.billing_ambiguity_reason or 'needs Billing confirmation'}); "
                        "cannot confirm refund without human and Billing review (R5/R6)."
                    ),
                ))
            elif facts.refund_status == "rejected":
                out.append(PromiseFinding(
                    kind="refund_approval",
                    text=sent.strip(),
                    reason="Register records the refund as rejected; cannot claim approval (R5).",
                ))
            elif facts.refund_status == "pending":
                out.append(PromiseFinding(
                    kind="refund_approval",
                    text=sent.strip(),
                    reason="Register records the refund as pending; Billing confirmation is required before claiming approval (R5/R6).",
                ))
            elif facts.refund_status != "approved":
                out.append(PromiseFinding(
                    kind="refund_approval",
                    text=sent.strip(),
                    reason="Register does not record a refund approval; Billing verification is required (R5/R6).",
                ))

        # 2. Semantic amount verification: never accept an amount merely because it appears in billing_record
        for m in _AMOUNT.finditer(sent):
            amt = _norm_amount(m.group(1) or m.group(2))
            if not amt:
                continue
            start, end = max(0, m.start() - 35), min(len(sent), m.end() + 25)
            window = sent[start:end].lower()
            local_payment = bool(_PAYMENT_CTX.search(window))
            local_refund = bool(_REFUND_CTX.search(window) or REFUND_APPROVED.search(window))

            if is_refund_sent and (local_refund or not local_payment):
                if facts.refund_status == "approved" and approved_refund_amt:
                    if amt != approved_refund_amt:
                        if original_payment_amt and amt == original_payment_amt:
                            out.append(PromiseFinding(
                                kind="refund_amount_mismatch",
                                text=m.group(0),
                                reason=(
                                    f"Draft states original payment ({m.group(0)}) as the refund amount; "
                                    f"register approves {facts.refund_amount} refund (R5)."
                                ),
                            ))
                        else:
                            out.append(PromiseFinding(
                                kind="refund_amount_mismatch",
                                text=m.group(0),
                                reason=(
                                    f"Draft states refund amount {m.group(0)}, which does not match the approved refund "
                                    f"of {facts.refund_amount} in the register (R5)."
                                ),
                            ))
                elif facts.refund_status == "approved" and not approved_refund_amt:
                    out.append(PromiseFinding(
                        kind="billing_ambiguous",
                        text=m.group(0),
                        reason="Register marks refund approved without a recorded refund amount; Billing confirmation required (R5/R6).",
                    ))
                elif amt not in recorded_amounts:
                    out.append(PromiseFinding(
                        kind="amount",
                        text=m.group(0),
                        reason="Amount not recorded in the booking register (R5/R7).",
                    ))
            elif amt not in recorded_amounts:
                out.append(PromiseFinding(
                    kind="amount",
                    text=m.group(0),
                    reason="Amount not recorded in the booking register (R5/R7).",
                ))

        # 3. Payout date promise verification (R5/R6)
        is_payout_sent = is_refund_sent or bool(re.search(r"\b(payout|payment|money|credited|credit|paid|transfer|transferred|account|bank)\b", low))
        if is_payout_sent and PAYOUT_PROMISE.search(low) and not negated and not facts.payout_date_recorded:
            out.append(PromiseFinding(
                kind="payout_date",
                text=sent.strip(),
                reason="No payout date recorded in the register; payout date is pending Billing confirmation (R5/R6).",
            ))

    return out


def find_unsupported_promises(draft: str | None, ctx: IssueContext, channel: Channel | None = None,
                              contact_preference: str | None = None) -> list[PromiseFinding]:
    out: list[PromiseFinding] = []
    f = ctx.booking.facts if ctx.booking else BookingFacts()
    billing = (ctx.booking.billing_record or "") if ctx.booking else ""
    if channel == Channel.PHONE and contact_preference == "whatsapp":
        out.append(PromiseFinding(kind="contact_preference", text="channel=phone", reason="Customer asked not to be called (R3)."))
    if not draft:
        return out
    out.extend(validate_refund_draft(draft, f, billing))
    for sent in _sentences(draft):
        low = sent.lower()
        negated = bool(_NEG.search(low))
        if ARRIVAL_PROMISE.search(low) and not negated and not f.substitute_confirmed and not f.arrival_confirmed:
            out.append(PromiseFinding(kind="arrival_or_replacement", text=sent.strip(),
                                      reason="Arrival/replacement not confirmed by Sourcing in the register (R4)."))
        if SCHEDULE_PROMISE.search(low) and not negated:
            out.append(PromiseFinding(kind="revised_time", text=sent.strip(), reason="Revised start not confirmed by Sourcing (R4)."))
    return out


def validate_source_ids(ids: list[str], ctx: IssueContext) -> tuple[list[str], list[str]]:
    allowed = set(ctx.group.source_message_ids) | ({ctx.group.booking_id} if ctx.group.booking_id else set())
    valid = [i for i in ids if i in allowed]
    invalid = [i for i in ids if i not in allowed]
    return valid, invalid

