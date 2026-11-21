"""Orchestration: rules-only baseline and AI-assisted workflow over the same issue contexts."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.modules import business_rules as br
from app.modules.ai_triage import PROMPT_VERSION_DEFAULT, run_ai_for_issue
from app.modules.drafting import template_draft
from app.modules.evidence import find_unsupported_promises, validate_source_ids
from app.modules.grouping import group_messages
from app.modules.llm_client import OpenRouterClient
from app.modules.priority import rank
from app.modules.rules_classifier import rules_signals
from app.schemas import (
    AITriageOutput, Channel, EvidenceItem, GuardrailEvent, IngestResult, IssueContext, IssueResult, IssueStatus,
    Recommendation, RunResult, Signals, Urgency,
)

log = logging.getLogger("triage.pipeline")


def parse_snapshot(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def build_contexts(ingest: IngestResult) -> list[IssueContext]:
    return group_messages(ingest.messages, ingest.bookings)


def source_evidence(ctx: IssueContext) -> list[EvidenceItem]:
    ev = [EvidenceItem(source_id=m.event_id, kind="message", quote=m.message) for m in ctx.messages]
    if ctx.booking:
        b = ctx.booking
        ev.append(EvidenceItem(source_id=b.booking_id, kind="booking",
                               quote=f"{b.service}, {b.locality}; ops: {b.operations_record or '-'}; billing: {b.billing_record or '-'}"))
    return ev


def recommend(ctx: IssueContext, signals: Signals, source: str) -> Recommendation:
    """Deterministic decision from an interpretation (rules or AI)."""
    s, events = br.enforce_signal_constraints(ctx, signals)
    facts = ctx.booking.facts if ctx.booking else None
    action = br.decide_action(s.issue_category, s, facts)
    ch = br.decide_channel(action, s)
    draft, hold = template_draft(action, ch, s, ctx)
    return Recommendation(
        issue_category=s.issue_category, customer_intent=s.customer_intent, status=br.status_for(action), urgency=Urgency.MEDIUM,
        responsible_department=br.DEPARTMENT_BY_CATEGORY[s.issue_category], supporting_departments=br.supporting_departments(action),
        action_code=action, next_action=br.next_action_text(action, ch, s, ctx), contact_channel=ch,
        missing_information=br.missing_information(action, s, ctx), draft_response=draft, hold_contact_reason=hold,
        explanation=f"Rules: category {s.issue_category.value} -> action {action.value} (rules {', '.join(br.RULE_BY_CATEGORY.get(s.issue_category, []))}).",
        evidence=source_evidence(ctx) + br.rule_evidence(s.issue_category),
        human_review_reasons=br.review_reasons(action, s, ctx),
        guardrail_events=[GuardrailEvent(rule_id=r, field=f, original=o, enforced=e, reason=why) for r, f, o, e, why in events],
        source=source, signals=s,  # type: ignore[arg-type]
    )


def _finalise_review_flag(rec: Recommendation) -> Recommendation:
    rec.human_review_required = bool(rec.human_review_reasons)
    return rec


def run_rules(ingest: IngestResult, snapshot: str, version: str = "v1", dataset: str = "supplied") -> RunResult:
    started = datetime.now(timezone.utc).isoformat()
    now = parse_snapshot(snapshot)
    ctxs = build_contexts(ingest)
    pairs = []
    for ctx in ctxs:
        rec = _finalise_review_flag(recommend(ctx, rules_signals(ctx, version), "rules"))
        pairs.append((rec, ctx))
    rank(pairs, now)
    issues = [IssueResult(issue_id=ctx.group.issue_id, group=ctx.group, messages=ctx.messages, booking=ctx.booking, rules=rec,
                          final=rec.model_copy(deep=True)) for rec, ctx in pairs]
    issues.sort(key=lambda i: i.final.priority_rank or 99)
    return RunResult(run_id=f"rules_{version}-{uuid.uuid4().hex[:6]}", dataset=dataset, mode="rules", variant=f"rules_{version}",
                     started_at=started, finished_at=datetime.now(timezone.utc).isoformat(), status="completed", issues=issues,
                     notes=["Deterministic keyword rules; no model used."])


def ai_raw_recommendation(out: AITriageOutput, channel: str | None, ctx: IssueContext) -> Recommendation:
    valid, _ = validate_source_ids(out.supporting_source_ids, ctx)
    quotes = {m.event_id: m.message for m in ctx.messages}
    return Recommendation(
        issue_category=out.issue_category, customer_intent=out.customer_intent,
        status=IssueStatus.RESOLVED if out.resolved_by_customer else IssueStatus.OPEN, urgency=out.suggested_urgency,
        responsible_department=out.suggested_department, action_code=out.recommended_action_code, next_action=out.recommended_next_action,
        contact_channel=Channel(channel) if channel else Channel.WHATSAPP, missing_information=out.missing_information,
        draft_response=out.draft_response, hold_contact_reason=out.hold_contact_reason, explanation=out.explanation,
        evidence=[EvidenceItem(source_id=i, kind="message" if i in quotes else "booking", quote=quotes.get(i, "booking register row"))
                  for i in valid],
        source="ai_raw", confidence=out.confidence, signals=signals_from_ai(out),
    )


def signals_from_ai(out: AITriageOutput) -> Signals:
    return Signals(issue_category=out.issue_category, customer_intent=out.customer_intent, resolved_by_customer=out.resolved_by_customer,
                   cover_available=out.cover_available, cover_until=out.cover_until, deadline=out.deadline,
                   contact_preference=out.contact_preference, refund_claimed_approved=out.refund_claimed_approved,
                   mentions_today=out.mentions_today, requested_change=out.requested_change, source="ai")


def guard_ai(out: AITriageOutput, raw: Recommendation, ctx: IssueContext, rules_rec: Recommendation) -> Recommendation:
    """Apply deterministic business rules + evidence checks to the AI interpretation."""
    rec = recommend(ctx, signals_from_ai(out), "ai_guarded")
    ev = list(rec.guardrail_events)
    if raw.action_code != rec.action_code:
        ev.append(GuardrailEvent(rule_id="ACTION_MAP", field="action_code", original=raw.action_code.value, enforced=rec.action_code.value,
                                 reason="Action is derived in code from the category and register facts."))
    if raw.responsible_department != rec.responsible_department:
        ev.append(GuardrailEvent(rule_id="R1/R5/R7", field="responsible_department", original=raw.responsible_department.value,
                                 enforced=rec.responsible_department.value, reason="Department ownership is fixed by the business rules."))
    if raw.contact_channel != rec.contact_channel:
        ev.append(GuardrailEvent(rule_id="R3", field="contact_channel", original=raw.contact_channel.value, enforced=rec.contact_channel.value,
                                 reason="Channel derived from contact preference and action."))
    # Draft: keep the AI wording only if it is for the same action and passes the promise checks.
    if rec.action_code in (br.ActionCode.CLOSE_CONFIRMED_ARRIVAL, br.ActionCode.MANUAL_TRIAGE):
        if out.draft_response:
            ev.append(GuardrailEvent(rule_id="R9", field="draft_response", original=out.draft_response, enforced=None,
                                     reason="No outgoing message for this action; hold reason shown instead."))
    elif not out.draft_response:
        ev.append(GuardrailEvent(rule_id="R11", field="draft_response", original=None, enforced="template",
                                 reason="Model gave no draft; safe template used."))
    elif raw.action_code != rec.action_code:
        ev.append(GuardrailEvent(rule_id="ACTION_MAP", field="draft_response", original=out.draft_response, enforced="template",
                                 reason="AI draft was written for a different action; safe template used."))
    else:
        findings = find_unsupported_promises(out.draft_response, ctx, rec.contact_channel, rec.signals.contact_preference if rec.signals else None)
        findings = [f for f in findings if f.kind != "contact_preference"]
        if findings:
            for f in findings:
                ev.append(GuardrailEvent(rule_id="PROMISE", field="draft_response", original=f.text, enforced="template",
                                         reason=f"{f.kind}: {f.reason}"))
        else:
            rec.draft_response = out.draft_response
            rec.hold_contact_reason = None
    valid, invalid = validate_source_ids(out.supporting_source_ids, ctx)
    if invalid:
        ev.append(GuardrailEvent(rule_id="EVIDENCE", field="supporting_source_ids", original=invalid, enforced=valid,
                                 reason="IDs not present in this issue were removed."))
    known = {x.lower() for x in rec.missing_information}
    rec.missing_information += [f"(AI) {x}" for x in out.missing_information if x and x.lower() not in known]
    rec.explanation = out.explanation
    rec.confidence = out.confidence
    rec.guardrail_events = ev
    if any(e.field in ("issue_category", "action_code", "responsible_department", "contact_channel") for e in ev):
        rec.human_review_reasons.append("AI suggestion was overridden by a business rule; check the guardrail log")
    if any(e.rule_id == "PROMISE" for e in ev):
        rec.human_review_reasons.append("AI draft contained an unsupported promise and was replaced")
    if rules_rec.action_code != rec.action_code:
        rec.human_review_reasons.append(f"Rules baseline disagrees (rules: {rules_rec.action_code.value})")
    return _finalise_review_flag(rec)


def run_ai(ingest: IngestResult, snapshot: str, client: OpenRouterClient, prompt_version: str = PROMPT_VERSION_DEFAULT,
           dataset: str = "supplied", rules_version: str = "v1") -> RunResult:
    started = datetime.now(timezone.utc).isoformat()
    now = parse_snapshot(snapshot)
    ctxs = build_contexts(ingest)
    calls = []
    results: list[IssueResult] = []
    failures = 0
    for ctx in ctxs:
        rules_rec = _finalise_review_flag(recommend(ctx, rules_signals(ctx, rules_version), "rules"))
        outcome = run_ai_for_issue(client, ctx, snapshot, prompt_version)
        calls.append(outcome.call)
        if outcome.output is None:
            failures += 1
            final = rules_rec.model_copy(deep=True)
            final.source = "rules_fallback"
            final.human_review_reasons = final.human_review_reasons + [f"AI unavailable ({outcome.error}); rules-only recommendation"]
            final.human_review_required = True
            results.append(IssueResult(issue_id=ctx.group.issue_id, group=ctx.group, messages=ctx.messages, booking=ctx.booking,
                                       rules=rules_rec, ai_status="failed", ai_error=outcome.error, ai_call_id=outcome.call.call_id,
                                       final=final))
            continue
        raw = ai_raw_recommendation(outcome.output, outcome.contact_channel, ctx)
        guarded = guard_ai(outcome.output, raw, ctx, rules_rec)
        results.append(IssueResult(issue_id=ctx.group.issue_id, group=ctx.group, messages=ctx.messages, booking=ctx.booking,
                                   rules=rules_rec, ai_raw=raw, ai_guarded=guarded, ai_status="ok", ai_call_id=outcome.call.call_id,
                                   final=guarded.model_copy(deep=True)))
    by_id = {c.group.issue_id: c for c in ctxs}
    rank([(r.rules, by_id[r.issue_id]) for r in results], now)
    guarded_pairs = [(r.ai_guarded, by_id[r.issue_id]) for r in results if r.ai_guarded]
    if guarded_pairs:
        rank(guarded_pairs, now)
    rank([(r.final, by_id[r.issue_id]) for r in results], now)
    results.sort(key=lambda r: r.final.priority_rank or 99)
    status = "completed" if failures == 0 else ("failed" if failures == len(results) else "completed_with_fallback")
    notes = [f"Prompt {prompt_version}; model {client.model}; {len(results) - failures}/{len(results)} issues processed by AI."]
    if failures:
        notes.append(f"{failures} issue(s) fell back to rules-only. The coordinator is shown which ones.")
    if client.simulated:
        notes.append("SIMULATED transport (test only) - not a real model execution.")
    return RunResult(run_id=f"ai_prompt_{prompt_version}-{uuid.uuid4().hex[:6]}", dataset=dataset, mode="ai",
                     variant=f"ai_prompt_{prompt_version}", started_at=started, finished_at=datetime.now(timezone.utc).isoformat(),
                     status=status, model=client.model, notes=notes, issues=results, llm_calls=calls)

