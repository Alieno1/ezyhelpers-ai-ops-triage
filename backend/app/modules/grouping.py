"""Deterministic issue grouping.

Algorithm (messages processed in chronological order, file order as tie-break):
1. If the message carries a booking_id already attached to an open group -> join that group
   (this links internal handoffs from other threads, e.g. a Sales handoff thread).
2. Else if the message's thread_id already belongs to a group -> join it (unless that group is
   bound to a *different* booking, in which case a new group is created and the conflict noted).
3. Else start a new group.
Messages without booking_id AND without thread_id always form their own group.
Locality / similar wording is never used to merge groups.
"""
from __future__ import annotations

from datetime import datetime

from app.modules.matching import match_booking
from app.schemas import BookingRecord, IssueContext, IssueGroup, Message


def _sort_key(m: Message) -> tuple[datetime, int]:
    return (m.received_at_ist or datetime.max, m.row_number)


def group_messages(messages: list[Message], bookings: list[BookingRecord]) -> list[IssueContext]:
    groups: list[dict] = []
    by_booking: dict[str, int] = {}
    by_thread: dict[str, int] = {}
    for m in sorted(messages, key=_sort_key):
        idx: int | None = None
        reason = ""
        if m.booking_id and m.booking_id in by_booking:
            idx = by_booking[m.booking_id]
            g = groups[idx]
            if m.thread_id and m.thread_id not in g["threads"]:
                kind = "internal handoff" if m.is_internal else "message"
                reason = f"{m.event_id}: {kind} in thread {m.thread_id} references the same booking {m.booking_id}"
            else:
                reason = f"{m.event_id}: same thread {m.thread_id} and booking {m.booking_id}"
        elif m.thread_id and m.thread_id in by_thread:
            cand = by_thread[m.thread_id]
            gb = groups[cand]["booking_id"]
            if m.booking_id and gb and gb != m.booking_id:
                reason = f"{m.event_id}: thread {m.thread_id} already bound to {gb} but message cites {m.booking_id}; kept separate"
            else:
                idx = cand
                reason = f"{m.event_id}: same thread {m.thread_id}"
        if idx is None:
            groups.append({"threads": [], "booking_id": None, "messages": [], "reasons": []})
            idx = len(groups) - 1
            reason = reason or f"{m.event_id}: first message of a new issue"
        g = groups[idx]
        g["messages"].append(m)
        g["reasons"].append(reason)
        if m.thread_id and m.thread_id not in g["threads"]:
            g["threads"].append(m.thread_id)
            by_thread.setdefault(m.thread_id, idx)
        if m.booking_id and not g["booking_id"]:
            g["booking_id"] = m.booking_id
            by_booking[m.booking_id] = idx
    by_id = {}
    for b in bookings:
        by_id.setdefault(b.booking_id, b)
    out: list[IssueContext] = []
    for n, g in enumerate(groups, start=1):
        match = match_booking(g["booking_id"], g["messages"], bookings)
        out.append(IssueContext(
            group=IssueGroup(issue_id=f"ISS-{n:02d}", thread_ids=g["threads"], booking_id=g["booking_id"],
                             source_message_ids=[m.event_id for m in g["messages"]], grouping_reasons=g["reasons"],
                             booking_match=match),
            messages=g["messages"],
            booking=by_id.get(g["booking_id"]) if match.status == "matched" else None,
        ))
    return out

