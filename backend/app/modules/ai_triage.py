"""AI-assisted interpretation and drafting for ONE issue.

The model receives only what it needs (anonymised messages, the matched register row, the rules)
and returns strict JSON (AITriageOutput). Business decisions are re-derived in code afterwards.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.modules.business_rules import RULES
from app.modules.llm_client import OpenRouterClient, parse_json_content
from app.modules.normalisation import redact_pii
from app.schemas import ActionCode, AITriageOutput, Category, Department, IssueContext, LLMCallRecord, Urgency

PROMPT_VERSION_DEFAULT = "v1"

_ENUM_CAT = [c.value for c in Category]
_ENUM_ACT = [a.value for a in ActionCode]
_ENUM_DEP = [d.value for d in Department]
_ENUM_URG = [u.value for u in Urgency]

ACTION_GUIDE = {
    "CARE_GAP_IMMEDIATE": "Dependant (elder/child) without the scheduled carer and nobody confirmed as cover: contact now, Sourcing looks for cover.",
    "CARE_GAP_COVERED_CHASE_SOURCING": "Care gap where a family member is temporarily covering: chase Sourcing, update on preferred channel.",
    "SERVICE_GAP_CHECK_ARRIVAL": "Non-care service has not started and is not resolved: check arrival with Sourcing, holding update.",
    "CLOSE_CONFIRMED_ARRIVAL": "Family confirmed the helper arrived: close, no callback.",
    "SCHEDULE_CHANGE_SOURCING_CHECK": "Customer asks to change a visit time: Sourcing checks the helper first; acknowledge without promising.",
    "BILLING_VERIFY_DISPUTED_REFUND": "Refund not approved in the register, or the customer's claim conflicts with it: Billing verifies; holding reply.",
    "RELAY_APPROVED_REFUND_CHASE_PAYOUT": "Register records the refund as approved but no payout date: relay approval/amount, Billing gets the date.",
    "RELAY_CONFIRMED_REFUND_FACTS": "Register records approval AND payout date: relay them.",
    "SALES_ENQUIRY_NO_QUOTE": "New enquiry from a prospect: Sales collects requirements; no price (no rate card).",
    "ASK_MINIMUM_BOOKING_IDENTITY": "Existing customer but booking identity uncertain: ask only for booking number or registered phone.",
    "MANUAL_TRIAGE": "Cannot be determined from the evidence.",
}

SYSTEM_PROMPT_V1 = f"""You are a triage assistant for the EzyHelpers duty desk (home-services company in Bengaluru).
You interpret ONE customer issue (one or more related messages) and draft a reply for a human coordinator to approve.

Hard rules (from the operations manual; never break them):
{chr(10).join(f'- {k}: {v}' for k, v in RULES.items())}

Facts policy:
- The booking register row in the input is the ONLY authority for bookings, arrival status, substitutes, refunds, amounts and payout dates.
- A customer's or salesperson's claim is NOT a fact. If the register does not record it, say it is being checked.
- Never state an arrival time, replacement, revised start time, refund approval, payout date or price unless the register records it.
- If there is no booking in the input, do not guess one from the locality.
- Messages can be in English, Hindi or Hinglish. Interpret them carefully, including negations.
- Times are IST. "Now" is the snapshot time in the input.

Field guidance:
- issue_category: one of {_ENUM_CAT}. care_gap = elder/child care visit missing; service_gap = other service missing.
- cover_available: "yes" only if a message says someone is with the dependant / covering; "no" if the dependant is or will be alone; "unknown" otherwise; "not_applicable" when not a care gap.
- cover_until / deadline: "HH:MM" 24h or null. deadline = the time by which harm or the customer's need occurs.
- contact_preference: "whatsapp" if they ask not to be called or to be messaged; "phone" if they ask for a call; else "no_preference".
- contact_channel: how the coordinator should contact them next: "phone", "whatsapp" or "none" (no contact needed).
- recommended_action_code: one of these codes:
{chr(10).join(f'  - {k}: {v}' for k, v in ACTION_GUIDE.items())}
- suggested_department: one of {_ENUM_DEP}. suggested_urgency: one of {_ENUM_URG}.
- requested_change: for schedule changes, the requested new time as "HH:MM" plus date words if given, else null.
- missing_information: short list of facts that are needed but not recorded.
- draft_response: a short WhatsApp/call-script reply in plain English (2-4 sentences) for the coordinator to approve, or null if no contact is needed (then give hold_contact_reason).
- supporting_source_ids: message IDs (and the booking ID) you relied on. Use only IDs present in the input.
- confidence: 0-1, your own uncertainty estimate.

Return ONLY a JSON object with exactly these keys: issue_category, customer_intent, resolved_by_customer, cover_available, cover_until,
deadline, contact_preference, contact_channel, refund_claimed_approved, mentions_today, requested_change, suggested_urgency,
suggested_department, recommended_action_code, recommended_next_action, missing_information, draft_response, hold_contact_reason,
explanation, supporting_source_ids, confidence."""

SYSTEM_PROMPT_V2 = SYSTEM_PROMPT_V1 + """

Additional strict interpretation checks (v2):
- For Hindi/Hinglish messages ("kal ... ki jagah 10 baje bhej sakte ho", "didi abhi tak nahi aayi", "call karo"), interpret full intent and deadlines accurately; extract requested_change in 24h HH:MM format.
- Negated closure phrases ("don't close", "not sorted", "still hasn't come") mean resolved_by_customer MUST be false and the gap remains open.
- If a customer claims a refund or schedule change was already approved/confirmed, check booking_register_row; if the register does not record it, treat it as unconfirmed and keep the claim out of draft_response."""

SYSTEM_PROMPTS = {"v1": SYSTEM_PROMPT_V1, "v2": SYSTEM_PROMPT_V2}


def output_json_schema() -> dict[str, Any]:
    s = {"type": "string"}
    ns = {"type": ["string", "null"]}
    b = {"type": "boolean"}
    props = {
        "issue_category": {"type": "string", "enum": _ENUM_CAT},
        "customer_intent": s,
        "resolved_by_customer": b,
        "cover_available": {"type": "string", "enum": ["yes", "no", "unknown", "not_applicable"]},
        "cover_until": ns, "deadline": ns,
        "contact_preference": {"type": "string", "enum": ["phone", "whatsapp", "no_preference"]},
        "contact_channel": {"type": "string", "enum": ["phone", "whatsapp", "none"]},
        "refund_claimed_approved": b, "mentions_today": b, "requested_change": ns,
        "suggested_urgency": {"type": "string", "enum": _ENUM_URG},
        "suggested_department": {"type": "string", "enum": _ENUM_DEP},
        "recommended_action_code": {"type": "string", "enum": _ENUM_ACT},
        "recommended_next_action": s,
        "missing_information": {"type": "array", "items": s},
        "draft_response": ns, "hold_contact_reason": ns, "explanation": s,
        "supporting_source_ids": {"type": "array", "items": s},
        "confidence": {"type": ["number", "null"]},
    }
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def build_user_payload(ctx: IssueContext, snapshot: str) -> dict[str, Any]:
    msgs = [{
        "id": m.event_id,
        "received_at_ist": m.received_at_ist.strftime("%Y-%m-%d %H:%M") if m.received_at_ist else None,
        "thread": m.thread_id,
        "booking_ref_given": m.booking_id,
        "channel": m.channel,
        "sender_role": m.sender,
        "text": redact_pii(m.message),
    } for m in ctx.messages]
    b = ctx.booking
    booking = None
    if b:
        booking = {
            "booking_id": b.booking_id, "service": b.service, "locality": b.locality,
            "scheduled_start_ist": b.scheduled_start_ist.strftime("%Y-%m-%d %H:%M") if b.scheduled_start_ist else None,
            "register_updated_at_ist": b.updated_at_ist.strftime("%Y-%m-%d %H:%M") if b.updated_at_ist else None,
            "operations_record": b.operations_record, "billing_record": b.billing_record,
        }
    return {
        "snapshot_now_ist": snapshot,
        "issue_id": ctx.group.issue_id,
        "messages_in_this_issue": msgs,
        "booking_register_row": booking,
        "booking_match_note": ctx.group.booking_match.note,
        "grouping_note": "; ".join(ctx.group.grouping_reasons),
    }


def build_messages(ctx: IssueContext, snapshot: str, prompt_version: str = PROMPT_VERSION_DEFAULT) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPTS[prompt_version]},
        {"role": "user", "content": json.dumps(build_user_payload(ctx, snapshot), ensure_ascii=False, indent=1)},
    ]


class AIOutcome:
    def __init__(self, output: AITriageOutput | None, call: LLMCallRecord, contact_channel: str | None, error: str | None):
        self.output = output
        self.call = call
        self.contact_channel = contact_channel
        self.error = error


def run_ai_for_issue(client: OpenRouterClient, ctx: IssueContext, snapshot: str, prompt_version: str = PROMPT_VERSION_DEFAULT) -> AIOutcome:
    messages = build_messages(ctx, snapshot, prompt_version)
    call = client.chat(messages, json_schema=output_json_schema(), issue_id=ctx.group.issue_id)
    if not call.ok:
        return AIOutcome(None, call, None, f"{call.error_type}: {call.error_message}")
    out, channel, err = _validate(call.raw_content or "")
    if out is None:
        call.validation_errors.append(err or "invalid")
        # One repair attempt: tell the model exactly what failed.
        repair = messages + [{"role": "assistant", "content": call.raw_content or ""},
                             {"role": "user", "content": f"Your output failed validation: {err}. Return only the corrected JSON object."}]
        call2 = client.chat(repair, json_schema=output_json_schema(), issue_id=ctx.group.issue_id)
        call2.validation_errors = call.validation_errors + call2.validation_errors
        call2.attempts += call.attempts
        call2.duration_ms += call.duration_ms
        for f in ("prompt_tokens", "completion_tokens", "total_tokens"):
            a, b2 = getattr(call, f), getattr(call2, f)
            setattr(call2, f, (a or 0) + (b2 or 0) if (a is not None or b2 is not None) else None)
        if call.cost_usd is not None or call2.cost_usd is not None:
            call2.cost_usd = (call.cost_usd or 0) + (call2.cost_usd or 0)
        call2.request_messages = messages
        call = call2
        if not call.ok:
            return AIOutcome(None, call, None, f"{call.error_type}: {call.error_message}")
        out, channel, err = _validate(call.raw_content or "")
        if out is None:
            call.ok = False
            call.error_type, call.error_message = "schema_validation_failed", err
            call.validation_errors.append(err or "invalid")
            return AIOutcome(None, call, None, f"schema_validation_failed: {err}")
    return AIOutcome(out, call, channel, None)


def _validate(content: str) -> tuple[AITriageOutput | None, str | None, str | None]:
    try:
        obj = parse_json_content(content)
    except (ValueError, json.JSONDecodeError) as e:
        return None, None, f"invalid JSON: {e}"
    channel = obj.get("contact_channel") if obj.get("contact_channel") in ("phone", "whatsapp", "none") else None
    try:
        return AITriageOutput.model_validate(obj), channel, None
    except ValidationError as e:
        return None, None, "; ".join(f"{'.'.join(str(x) for x in er['loc'])}: {er['msg']}" for er in e.errors())[:800]

