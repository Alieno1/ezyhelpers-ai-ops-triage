"""Transparent priority engine.

Hard tiers come first (business rules); a numeric tie-break only orders issues *inside* a tier.

Tier (urgency)                                                          Rule
CRITICAL  open care gap with nobody confirmed as cover, or cover ending <= 60 min     R2
HIGH      care gap with temporary cover; open service gap; unknown booking that may
          concern today's service; booking reference not in register                  R1, R10
MEDIUM    schedule change; refund query; unknown booking (not same-day); unclassified R1, R5, R6
LOW       new enquiry                                                                  R7
NONE      resolved (family confirmed arrival)                                         R9

Inside a tier: minutes until the deadline (earliest first; issues without a deadline after
those with one), then the time the first message arrived (oldest first).
Limitation: deadlines are parsed from text; a missed deadline phrase drops an issue to the
'no deadline' position inside its tier, never to a lower tier.
"""
from __future__ import annotations

from datetime import datetime

from app.schemas import URGENCY_ORDER, ActionCode, Category, IssueContext, IssueStatus, Recommendation, Urgency


def _minutes_until(hhmm: str | None, now: datetime) -> float | None:
    if not hhmm:
        return None
    try:
        h, m = (int(x) for x in hhmm.split(":"))
    except ValueError:
        return None
    return (now.replace(hour=h, minute=m, second=0, microsecond=0) - now).total_seconds() / 60


def assess_urgency(rec: Recommendation, ctx: IssueContext, now: datetime) -> tuple[Urgency, str, str | None]:
    """Returns (urgency, reason, deadline HH:MM or ISO)."""
    s = rec.signals
    if rec.status == IssueStatus.RESOLVED:
        return Urgency.NONE, "Resolved: family confirmed arrival (R9). No callback.", None
    cat = rec.issue_category
    deadline = s.deadline if s else None
    if cat == Category.CARE_GAP:
        cover = s.cover_available if s else "unknown"
        mins = _minutes_until(s.cover_until if s else None, now)
        if cover != "yes":
            dl = f"; customer deadline {deadline}" if deadline else ""
            return Urgency.CRITICAL, f"Current care gap with nobody confirmed as cover (R2){dl}.", deadline
        if mins is not None and mins <= 60:
            return Urgency.CRITICAL, f"Care gap; family cover ends at {s.cover_until} (within 60 min) (R2).", s.cover_until
        until = f" until {s.cover_until}" if s and s.cover_until else ""
        return Urgency.HIGH, f"Care gap, but family cover is in place{until}; no substitute confirmed yet.", (s.cover_until if s else None) or deadline
    if cat == Category.SERVICE_GAP:
        return Urgency.HIGH, "Open service gap (helper not arrived); no dependant at risk recorded.", deadline
    if ctx.group.booking_match.status == "unknown_reference":
        return Urgency.HIGH, "Booking reference not found in the register; identity must be confirmed (R10).", deadline
    if cat == Category.UNIDENTIFIED_BOOKING:
        if s and s.mentions_today:
            return Urgency.HIGH, "Booking identity unknown and the customer refers to today's visit; could be a live gap (R10).", deadline
        return Urgency.MEDIUM, "Booking identity unknown; not time-critical from the text (R10).", deadline
    if cat == Category.SCHEDULE_CHANGE:
        start = ctx.booking.scheduled_start_ist if ctx.booking else None
        dl = start.strftime("%Y-%m-%d %H:%M") if start else deadline
        return Urgency.MEDIUM, f"Schedule change for a future visit{f' ({dl})' if dl else ''}; Sourcing must confirm first (R4).", dl
    if cat == Category.REFUND_QUERY:
        if rec.action_code == ActionCode.BILLING_VERIFY_DISPUTED_REFUND:
            return Urgency.MEDIUM, "Refund dispute: customer claim not supported by the register (R5, R6).", None
        return Urgency.MEDIUM, "Refund approved in register; payout date missing (R5, R6).", None
    if cat == Category.NEW_ENQUIRY:
        return Urgency.LOW, "New enquiry; no service at risk (R7).", None
    return Urgency.MEDIUM, "Unclassified issue; medium until a coordinator reads it.", deadline


def _deadline_minutes(dl: str | None, now: datetime) -> float:
    if not dl:
        return float("inf")
    if len(dl) == 5:
        v = _minutes_until(dl, now)
        return v if v is not None else float("inf")
    try:
        return (datetime.strptime(dl, "%Y-%m-%d %H:%M") - now).total_seconds() / 60
    except ValueError:
        return float("inf")


def rank(items: list[tuple[Recommendation, IssueContext]], now: datetime,
         urgency_overrides: dict[str, Urgency] | None = None) -> list[tuple[Recommendation, IssueContext]]:
    """Sets urgency/reason/deadline/rank on each recommendation and returns them sorted.

    ``urgency_overrides`` are coordinator decisions (human review) and always win.
    """
    for rec, ctx in items:
        u, reason, dl = assess_urgency(rec, ctx, now)
        ov = (urgency_overrides or {}).get(ctx.group.issue_id)
        if ov is not None and ov != u:
            reason = f"Coordinator override: {u.value} -> {ov.value}. Rule assessment was: {reason}"
            u = ov
        rec.urgency, rec.priority_reason, rec.deadline = u, reason, dl

    def key(pair: tuple[Recommendation, IssueContext]):
        rec, ctx = pair
        first = min((m.received_at_ist for m in ctx.messages if m.received_at_ist), default=datetime.max)
        return (URGENCY_ORDER[rec.urgency], _deadline_minutes(rec.deadline, now), first)

    ordered = sorted(items, key=key)
    for i, (rec, _) in enumerate(ordered, start=1):
        rec.priority_rank = i
    return ordered


def first_callback(ordered: list[tuple[Recommendation, IssueContext]]) -> tuple[Recommendation, IssueContext] | None:
    """The first open issue whose next action is a phone call."""
    from app.schemas import Channel
    for rec, ctx in ordered:
        if rec.status != IssueStatus.RESOLVED and rec.contact_channel == Channel.PHONE:
            return rec, ctx
    return None
