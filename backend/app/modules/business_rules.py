"""Deterministic business rules from the assignment PDF.

Every customer-impacting decision (owner, action, channel, refund facts, closure) is made here,
in code. The LLM may supply *interpretation* (Signals) but cannot override these functions.
"""
from __future__ import annotations

from app.modules.rules_classifier import detect_no_call, is_care_service
from app.schemas import (
    ActionCode, BookingFacts, Category, Channel, Department, EvidenceItem, IssueContext, IssueStatus, Signals,
)

RULES: dict[str, str] = {
    "R1": "Duty Ops owns active service gaps, schedule changes and unclear existing bookings.",
    "R2": "A current care gap with nobody to cover takes first priority.",
    "R3": "Respect the customer's contact preference.",
    "R4": "A replacement or revised start time can be promised only after Sourcing records confirmation. Duty Ops owns the family update.",
    "R5": "The register is the authority for refund approval, amount and payout date. A coordinator can relay a confirmed fact.",
    "R6": "Billing checks disputed amounts and missing dates.",
    "R7": "Sales owns new enquiries and prepares quotes. There is no rate card, so no price may be quoted.",
    "R8": "Group messages about the same issue.",
    "R9": "A family's arrival confirmation can close a missed shift.",
    "R10": "Where booking identity is uncertain, keep it open and ask for the minimum detail needed to identify it.",
    "R11": "Outgoing replies are drafts; nothing is sent automatically.",
}

DEPARTMENT_BY_CATEGORY: dict[Category, Department] = {
    Category.CARE_GAP: Department.DUTY_OPS,
    Category.SERVICE_GAP: Department.DUTY_OPS,
    Category.ARRIVAL_CONFIRMED: Department.DUTY_OPS,
    Category.SCHEDULE_CHANGE: Department.DUTY_OPS,
    Category.UNIDENTIFIED_BOOKING: Department.DUTY_OPS,
    Category.REFUND_QUERY: Department.BILLING,
    Category.NEW_ENQUIRY: Department.SALES,
    Category.OTHER: Department.DUTY_OPS,
}
RULE_BY_CATEGORY = {
    Category.CARE_GAP: ["R1", "R2", "R3", "R4"], Category.SERVICE_GAP: ["R1", "R3", "R4"], Category.ARRIVAL_CONFIRMED: ["R9", "R8"],
    Category.SCHEDULE_CHANGE: ["R1", "R4", "R3"], Category.UNIDENTIFIED_BOOKING: ["R1", "R10"], Category.REFUND_QUERY: ["R5", "R6"],
    Category.NEW_ENQUIRY: ["R7"], Category.OTHER: ["R1"],
}


def enforce_signal_constraints(ctx: IssueContext, s: Signals) -> tuple[Signals, list[tuple[str, str, object, object, str]]]:
    """Hard constraints on the interpretation that come from source data, not language.

    Returns the corrected signals and a list of (rule_id, field, original, enforced, reason).
    """
    events: list[tuple[str, str, object, object, str]] = []
    s = s.model_copy()
    matched = ctx.group.booking_match.status == "matched"
    first_sender = (ctx.messages[0].sender or "").lower() if ctx.messages else ""
    all_text = " ".join(m.text_normalised for m in ctx.messages)
    # Booking identity (R10): without a matched booking only a prospect enquiry or an unidentified booking is possible.
    if not matched:
        allowed = {Category.UNIDENTIFIED_BOOKING} | ({Category.NEW_ENQUIRY} if first_sender == "prospect" else set())
        if s.issue_category not in allowed:
            target = Category.NEW_ENQUIRY if first_sender == "prospect" else Category.UNIDENTIFIED_BOOKING
            events.append(("R10", "issue_category", s.issue_category.value, target.value,
                           "No booking matched in the register; identity must be confirmed before acting on the booking."))
            s.issue_category = target
            s.resolved_by_customer = False
    elif s.issue_category == Category.NEW_ENQUIRY and first_sender != "prospect":
        events.append(("R1", "issue_category", s.issue_category.value, Category.OTHER.value,
                       "Message references an existing booking; it is not a new enquiry. Sent to manual triage."))
        s.issue_category = Category.OTHER
    elif s.issue_category == Category.UNIDENTIFIED_BOOKING:
        events.append(("R10", "issue_category", s.issue_category.value, Category.OTHER.value,
                       "Booking is matched in the register, so identity is not uncertain. Sent to manual triage."))
        s.issue_category = Category.OTHER
    # Care vs non-care is a register fact (service type).
    if matched and s.issue_category in (Category.CARE_GAP, Category.SERVICE_GAP):
        target = Category.CARE_GAP if is_care_service(ctx.booking) else Category.SERVICE_GAP
        if target != s.issue_category:
            events.append(("R2", "issue_category", s.issue_category.value, target.value,
                           f"Register service is '{ctx.booking.service if ctx.booking else '?'}'."))
            s.issue_category = target
    # Closure (R9) needs a customer confirmation that is not negated.
    if s.issue_category == Category.ARRIVAL_CONFIRMED or s.resolved_by_customer:
        from app.modules.rules_classifier import NEGATED_CLOSURE
        ext = [m for m in ctx.messages if not m.is_internal and (m.sender or "").lower() == "customer"]
        last = ext[-1].text_normalised if ext else ""
        if not ext or NEGATED_CLOSURE.search(last):
            events.append(("R9", "issue_category", s.issue_category.value, Category.SERVICE_GAP.value if not is_care_service(ctx.booking) else Category.CARE_GAP.value,
                           "Closure requires a non-negated arrival confirmation from the family."))
            s.issue_category = Category.CARE_GAP if is_care_service(ctx.booking) else Category.SERVICE_GAP
            s.resolved_by_customer = False
        elif s.resolved_by_customer and s.issue_category in (Category.CARE_GAP, Category.SERVICE_GAP):
            events.append(("R9", "issue_category", s.issue_category.value, Category.ARRIVAL_CONFIRMED.value,
                           "Family confirmed arrival (resolved_by_customer=True); normalized category to arrival_confirmed."))
            s.issue_category = Category.ARRIVAL_CONFIRMED
    # Contact preference (R3): an explicit 'don't call' in the source text always wins.
    if detect_no_call(all_text) and s.contact_preference != "whatsapp":
        events.append(("R3", "contact_preference", s.contact_preference, "whatsapp", "Source message explicitly asks not to be called."))
        s.contact_preference = "whatsapp"
    if s.issue_category != Category.CARE_GAP and s.cover_available not in ("not_applicable",):
        s.cover_available = "not_applicable"
        s.cover_until = None
    return s, events


def decide_action(cat: Category, s: Signals, facts: BookingFacts | None) -> ActionCode:
    if cat == Category.CARE_GAP:
        return ActionCode.CARE_GAP_COVERED_CHASE_SOURCING if s.cover_available == "yes" else ActionCode.CARE_GAP_IMMEDIATE
    if cat == Category.SERVICE_GAP:
        return ActionCode.SERVICE_GAP_CHECK_ARRIVAL
    if cat == Category.ARRIVAL_CONFIRMED:
        return ActionCode.CLOSE_CONFIRMED_ARRIVAL
    if cat == Category.SCHEDULE_CHANGE:
        return ActionCode.SCHEDULE_CHANGE_SOURCING_CHECK
    if cat == Category.NEW_ENQUIRY:
        return ActionCode.SALES_ENQUIRY_NO_QUOTE
    if cat == Category.UNIDENTIFIED_BOOKING:
        return ActionCode.ASK_MINIMUM_BOOKING_IDENTITY
    if cat == Category.REFUND_QUERY:
        f = facts or BookingFacts()
        if f.refund_status != "approved":
            return ActionCode.BILLING_VERIFY_DISPUTED_REFUND  # under review / no record: Billing must verify (R5, R6)
        if not f.payout_date_recorded:
            return ActionCode.RELAY_APPROVED_REFUND_CHASE_PAYOUT
        return ActionCode.RELAY_CONFIRMED_REFUND_FACTS
    return ActionCode.MANUAL_TRIAGE


def decide_channel(action: ActionCode, s: Signals) -> Channel:
    if action in (ActionCode.CLOSE_CONFIRMED_ARRIVAL, ActionCode.MANUAL_TRIAGE):
        return Channel.NONE if action == ActionCode.CLOSE_CONFIRMED_ARRIVAL else Channel.WHATSAPP
    if s.contact_preference == "whatsapp":
        return Channel.WHATSAPP
    if s.contact_preference == "phone":
        return Channel.PHONE
    # No stated preference: an uncovered care gap justifies a call; everything else is answered on the inbound channel.
    return Channel.PHONE if action == ActionCode.CARE_GAP_IMMEDIATE else Channel.WHATSAPP


def supporting_departments(action: ActionCode) -> list[Department]:
    if action in (ActionCode.CARE_GAP_IMMEDIATE, ActionCode.CARE_GAP_COVERED_CHASE_SOURCING, ActionCode.SERVICE_GAP_CHECK_ARRIVAL,
                  ActionCode.SCHEDULE_CHANGE_SOURCING_CHECK):
        return [Department.SOURCING]
    if action == ActionCode.BILLING_VERIFY_DISPUTED_REFUND:
        return [Department.SALES, Department.DUTY_OPS]
    if action in (ActionCode.RELAY_APPROVED_REFUND_CHASE_PAYOUT, ActionCode.RELAY_CONFIRMED_REFUND_FACTS):
        return [Department.DUTY_OPS]
    return []


def carer_word(ctx: IssueContext) -> str:
    svc = (ctx.booking.service or "").lower() if ctx.booking else ""
    return {"elder companionship": "caregiver", "childcare": "nanny", "cooking": "cook", "housekeeping": "helper"}.get(svc, "helper")


def next_action_text(action: ActionCode, ch: Channel, s: Signals, ctx: IssueContext) -> str:
    carer = carer_word(ctx)
    how = {"phone": "Call", "whatsapp": "WhatsApp", "none": "No contact needed:"}[ch.value]
    f = ctx.booking.facts if ctx.booking else BookingFacts()
    if action == ActionCode.CARE_GAP_IMMEDIATE:
        dl = f" before {s.deadline}" if s.deadline else ""
        return (f"Duty Ops: {how} the customer now{dl}. In parallel ask Sourcing to reach the assigned {carer} and look for cover. "
                "Give no arrival time or replacement until Sourcing records confirmation.")
    if action == ActionCode.CARE_GAP_COVERED_CHASE_SOURCING:
        until = f" (family cover ends {s.cover_until})" if s.cover_until else ""
        return (f"Duty Ops: chase Sourcing for a substitute {carer}{until}; send the family a {ch.value} update. "
                "Do not promise a substitute until Sourcing records it.")
    if action == ActionCode.SERVICE_GAP_CHECK_ARRIVAL:
        return f"Duty Ops: check the {carer}'s arrival with Sourcing; {how} the customer with a holding update. No ETA unless confirmed."
    if action == ActionCode.CLOSE_CONFIRMED_ARRIVAL:
        return "Duty Ops: close the issue on the family's confirmation (coordinator to confirm) and update the register. No callback needed."
    if action == ActionCode.SCHEDULE_CHANGE_SOURCING_CHECK:
        req = f" to {s.requested_change}" if s.requested_change else ""
        return (f"Duty Ops: ask Sourcing to check the {carer}'s availability for the requested change{req}; {how} the customer an acknowledgement. "
                "Keep the current confirmed time until Sourcing confirms.")
    if action == ActionCode.BILLING_VERIFY_DISPUTED_REFUND:
        return ("Billing: verify the refund decision (register says under review, no approval or payout date) and the 'approved' claim with Sales; "
                f"Duty Ops sends a {ch.value} holding reply that does not confirm approval.")
    if action == ActionCode.RELAY_APPROVED_REFUND_CHASE_PAYOUT:
        return (f"Coordinator: relay the recorded approval ({f.refund_amount or 'amount per register'}) by {ch.value}; "
                "Billing to confirm and record the payout date.")
    if action == ActionCode.RELAY_CONFIRMED_REFUND_FACTS:
        return f"Coordinator: relay the recorded refund amount and payout date ({f.payout_date}) by {ch.value}."
    if action == ActionCode.SALES_ENQUIRY_NO_QUOTE:
        return "Sales: reply to the enquiry and collect requirements; prepare a quote. Quote no price (no rate card)."
    if action == ActionCode.ASK_MINIMUM_BOOKING_IDENTITY:
        cands = ctx.group.booking_match.possible_candidates
        hint = f" Possible matches by locality only ({', '.join(cands)}) are NOT confirmed." if cands else ""
        return f"Duty Ops: {how} the customer asking only for the booking number or registered phone number; keep the issue open.{hint}"
    return "Coordinator: read the messages and decide manually; the system could not classify this issue."


def missing_information(action: ActionCode, s: Signals, ctx: IssueContext) -> list[str]:
    carer = carer_word(ctx)
    f = ctx.booking.facts if ctx.booking else BookingFacts()
    out: list[str] = []
    if action == ActionCode.CARE_GAP_IMMEDIATE:
        out += [f"Current status / ETA of the assigned {carer} (register: arrival unconfirmed)",
                "Sourcing confirmation of a replacement or cover (none recorded)"]
        if s.cover_available == "unknown":
            out.append("Whether anyone is with the dependant now")
    elif action == ActionCode.CARE_GAP_COVERED_CHASE_SOURCING:
        out += ["Sourcing confirmation of a substitute (none recorded)"]
        if not s.cover_until:
            out.append("How long the family cover lasts")
    elif action == ActionCode.SERVICE_GAP_CHECK_ARRIVAL:
        out += [f"Current status / ETA of the {carer} (not recorded)"]
    elif action == ActionCode.SCHEDULE_CHANGE_SOURCING_CHECK:
        out += [f"{carer.capitalize()}'s availability at the requested time (Sourcing to confirm with the helper)"]
        if not s.requested_change:
            out.append("Exact requested new time (confirm with the customer)")
    elif action == ActionCode.BILLING_VERIFY_DISPUTED_REFUND:
        out += ["Refund decision (register: under review, no approval recorded)", "Payout date (not recorded)",
                "Who in Sales said the refund was approved (customer claim not supported by the register)" if s.refund_claimed_approved else ""]
    elif action == ActionCode.RELAY_APPROVED_REFUND_CHASE_PAYOUT:
        out += ["Payout date (register: pending)"]
    elif action == ActionCode.SALES_ENQUIRY_NO_QUOTE:
        out += ["Rate card / pricing (not provided in the exercise)", "Customer requirements: days, hours, start date, address"]
    elif action == ActionCode.ASK_MINIMUM_BOOKING_IDENTITY:
        out += ["Booking number or registered phone number (booking identity unknown)"]
    elif action == ActionCode.MANUAL_TRIAGE:
        out += ["Issue type could not be determined automatically"]
    if ctx.booking is None and ctx.group.booking_match.status == "unknown_reference":
        out.append(f"Booking {ctx.group.booking_id} is not in the register")
    _ = f
    return [x for x in out if x]


def review_reasons(action: ActionCode, s: Signals, ctx: IssueContext) -> list[str]:
    r: list[str] = []
    if action == ActionCode.CARE_GAP_IMMEDIATE:
        r.append("Critical care gap: coordinator confirms the callback and owns the family update")
    if action == ActionCode.CLOSE_CONFIRMED_ARRIVAL:
        r.append("Closing an issue is a coordinator decision (confirm the family's message)")
    if action == ActionCode.ASK_MINIMUM_BOOKING_IDENTITY:
        r.append("Booking identity unknown; do not link to a booking without confirmation")
    if action == ActionCode.BILLING_VERIFY_DISPUTED_REFUND:
        r.append("Customer refund claim conflicts with the register" if s.refund_claimed_approved else "Refund not approved in the register")
    if action == ActionCode.MANUAL_TRIAGE:
        r.append("Unclassified: needs a human read")
    if ctx.group.booking_match.status == "unknown_reference":
        r.append("Booking reference not found in the register")
    return r


def rule_evidence(cat: Category) -> list[EvidenceItem]:
    return [EvidenceItem(source_id=rid, kind="rule", quote=RULES[rid]) for rid in RULE_BY_CATEGORY.get(cat, [])]


def status_for(action: ActionCode) -> IssueStatus:
    if action == ActionCode.CLOSE_CONFIRMED_ARRIVAL:
        return IssueStatus.RESOLVED
    if action == ActionCode.ASK_MINIMUM_BOOKING_IDENTITY:
        return IssueStatus.AWAITING_INFO
    return IssueStatus.OPEN

