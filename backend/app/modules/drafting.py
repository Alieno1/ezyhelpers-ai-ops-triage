"""Safe template drafts used by the rules baseline and as the fallback when an AI draft fails a guardrail.

Templates only state facts recorded in the register or said by the customer. They never promise
arrival times, replacements, refund approvals, payout dates or prices.
"""
from __future__ import annotations

from app.modules.business_rules import carer_word
from app.schemas import ActionCode, BookingFacts, Channel, IssueContext, Signals


def template_draft(action: ActionCode, ch: Channel, s: Signals, ctx: IssueContext) -> tuple[str | None, str | None]:
    """Returns (draft_response, hold_contact_reason)."""
    carer = carer_word(ctx)
    b = ctx.booking
    f = b.facts if b else BookingFacts()
    start = f"{b.scheduled_start_ist:%H:%M} " if b and b.scheduled_start_ist else ""
    svc = (b.service or "service").lower() if b else "service"
    if action == ActionCode.CARE_GAP_IMMEDIATE:
        opener = "I'm calling you now." if ch == Channel.PHONE else "We are on it now and will keep you updated here on WhatsApp."
        return (f"Hello, this is the EzyHelpers duty desk about today's {start}{svc} visit. We have your message that the {carer} "
                f"has not arrived. {opener} We are checking with the {carer} and our Sourcing team is looking for cover. "
                "We will only give you a time once it is confirmed.", None)
    if action == ActionCode.CARE_GAP_COVERED_CHASE_SOURCING:
        until = f" until {s.cover_until}" if s.cover_until else ""
        return (f"Hi, thank you for letting us know, and we're glad family can help{until}. Our Sourcing team is checking for a substitute "
                f"{carer} now. Nothing is confirmed yet; we'll message you here as soon as we have a confirmed update.", None)
    if action == ActionCode.SERVICE_GAP_CHECK_ARRIVAL:
        return (f"Hi, sorry that your {start}{svc} visit has not started. We are checking with the {carer} now and will update you here "
                "as soon as we have confirmed information.", None)
    if action == ActionCode.CLOSE_CONFIRMED_ARRIVAL:
        return (None, "Family confirmed the helper has arrived and asked to close; no callback needed.")
    if action == ActionCode.SCHEDULE_CHANGE_SOURCING_CHECK:
        when = f" ({b.scheduled_start_ist:%d %b})" if b and b.scheduled_start_ist else ""
        req = f" to {s.requested_change}" if s.requested_change else ""
        cur = f"{f.confirmed_start_time} " if f.confirmed_start_time else ""
        return (f"Hi, we've noted your request to change the {svc} visit{when}{req}. As you asked, we will check with your {carer} first. "
                f"Until we confirm with you, the current {cur}start time stays as booked.", None)
    if action == ActionCode.BILLING_VERIFY_DISPUTED_REFUND:
        paid = f" We can see your payment of {f.payment_amount} in our records." if f.payment_amount else ""
        return (f"Hi, thank you for following up.{paid} Your refund request is currently under review with our Billing team; "
                "we do not yet have a decision or payout date recorded. Billing is checking it and we will update you here once there "
                "is a confirmed decision.", None)
    if action == ActionCode.RELAY_APPROVED_REFUND_CHASE_PAYOUT:
        amt = f"of {f.refund_amount} " if f.refund_amount else ""
        return (f"Hi, your refund {amt}has been approved. The payout date is not confirmed yet; our Billing team is checking it and we'll "
                "share the date here as soon as it is recorded.", None)
    if action == ActionCode.RELAY_CONFIRMED_REFUND_FACTS:
        return (f"Hi, your refund of {f.refund_amount} has been approved and the recorded payout date is {f.payout_date}.", None)
    if action == ActionCode.SALES_ENQUIRY_NO_QUOTE:
        return ("Hi, thanks for your interest in EzyHelpers. Our Sales team will prepare a quote for you. To do that, could you share the "
                "days and hours you need, your locality and when you'd like to start?", None)
    if action == ActionCode.ASK_MINIMUM_BOOKING_IDENTITY:
        return ("Hi, we want to check this for you straight away. Could you share the booking number, or the phone number the booking "
                "was made with? That tells us exactly which visit you mean.", None)
    return (None, "Not classified automatically; coordinator to read the messages before any contact.")

