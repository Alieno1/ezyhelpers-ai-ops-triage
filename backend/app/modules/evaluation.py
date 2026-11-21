"""Objective evaluation against the frozen expected-action reference sets.

Compares rules_v1 (baseline), rules_v2 (single targeted Hinglish improvement), and AI (when
real OpenRouter credentials are available — never simulated or fabricated).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.ai_triage import build_user_payload
from app.modules.evidence import find_unsupported_promises
from app.modules.grouping import group_messages
from app.modules.llm_client import OpenRouterClient
from app.modules.priority import first_callback
from app.pipeline import parse_snapshot, run_ai, run_rules
from app.schemas import URGENCY_ORDER, IngestResult, IssueContext, IssueResult, IssueStatus, Recommendation, RunResult


class MethodMetrics(BaseModel):
    variant: str
    label: str
    mode: Literal["rules", "ai"]
    status: Literal["evaluated", "pending_credentials", "failed"] = "evaluated"
    note: str = ""
    model: str | None = None
    total_cases: int = 0
    correct_next_actions: int = 0
    unsupported_promises: int = 0
    department_correct: int = 0
    urgency_correct: int = 0
    status_correct: int = 0
    missing_info_complete: int = 0
    grouping_correct: int = 0
    first_callback_correct: bool | None = None
    first_callback_actual: list[str] = Field(default_factory=list)
    other_errors: list[str] = Field(default_factory=list)
    token_usage_total: int | None = None
    actual_cost_usd: float | None = None
    duration_ms_total: int | None = None


class MethodCaseOutcome(BaseModel):
    matched_issue_id: str | None = None
    action_code: str | None = None
    contact_channel: str | None = None
    department: str | None = None
    urgency: str | None = None
    status: str | None = None
    action_correct: bool = False
    department_correct: bool = False
    urgency_correct: bool = False
    status_correct: bool = False
    missing_info_ok: bool = False
    grouping_ok: bool = False
    unsupported_promises: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CaseComparisonRow(BaseModel):
    source_message_ids: list[str]
    booking_id: str | None
    expected_category: str
    expected_action_code: str
    expected_channel: str
    expected_department: str
    expected_urgency: str
    expected_status: str
    must_flag_missing: list[str] = Field(default_factory=list)
    rationale: str
    outcomes: dict[str, MethodCaseOutcome] = Field(default_factory=dict)


class DisagreementItem(BaseModel):
    source_message_ids: list[str]
    booking_id: str | None
    variant: str
    kind: str
    expected: str
    actual: str
    explanation: str


class ImprovementSummary(BaseModel):
    before_variant: str
    after_variant: str
    before_correct: int
    after_correct: int
    total: int
    delta_correct: int
    before_unsupported_promises: int
    after_unsupported_promises: int
    change_description: str


class EvaluationReport(BaseModel):
    eval_id: str
    dataset: str
    snapshot_time_ist: str
    evaluated_at: str
    expected_file: str
    total_cases: int
    expected_first_callback: list[str] = Field(default_factory=list)
    human_corrections_count: int = 0
    methods: list[MethodMetrics]
    case_comparisons: list[CaseComparisonRow]
    disagreements_and_failures: list[DisagreementItem]
    improvement_summary: ImprovementSummary
    sample_llm_requests: list[dict[str, Any]] = Field(default_factory=list)
    sample_llm_calls: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def load_expected(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _status_matches(actual: IssueStatus, expected: str) -> bool:
    if expected == "open":
        return actual in (IssueStatus.OPEN, IssueStatus.AWAITING_INFO)
    return actual.value == expected


def _missing_info_matches(actual_list: list[str], required_keys: list[str], synonyms: dict[str, list[str]]) -> tuple[bool, list[str]]:
    joined = " ".join(actual_list).lower()
    missing_keys = []
    for key in required_keys:
        syns = synonyms.get(key, [key])
        if not any(s.lower() in joined for s in syns):
            missing_keys.append(key)
    return len(missing_keys) == 0, missing_keys


def _match_issue(expected_ids: list[str], issues: list[IssueResult]) -> tuple[IssueResult | None, bool, str | None]:
    exp_set = set(expected_ids)
    for iss in issues:
        if set(iss.group.source_message_ids) == exp_set:
            return iss, True, None
    overlapping = [iss for iss in issues if set(iss.group.source_message_ids) & exp_set]
    if not overlapping:
        return None, False, f"Expected group {expected_ids} not found in any issue"
    got_desc = ", ".join(f"{i.issue_id}:{i.group.source_message_ids}" for i in overlapping)
    return overlapping[0], False, f"Grouping mismatch: expected {expected_ids}, got {got_desc}"


def evaluate_run(run: RunResult, expected: dict[str, Any], variant_label: str, label: str,
                 use_field: Literal["final", "rules", "ai_raw", "ai_guarded"] = "final") -> tuple[MethodMetrics, dict[str, MethodCaseOutcome], list[DisagreementItem]]:
    cases = expected["cases"]
    synonyms = expected.get("missing_info_synonyms", {})
    exp_first = expected.get("expected_first_callback", [])

    metrics = MethodMetrics(
        variant=variant_label, label=label, mode=run.mode,
        status="evaluated", model=run.model, total_cases=len(cases),
    )
    outcomes: dict[str, MethodCaseOutcome] = {}
    disagreements: list[DisagreementItem] = []

    if run.mode == "ai" and run.llm_calls:
        tokens = [c.total_tokens for c in run.llm_calls if c.total_tokens is not None]
        costs = [c.cost_usd for c in run.llm_calls if c.cost_usd is not None]
        metrics.token_usage_total = sum(tokens) if tokens else None
        metrics.actual_cost_usd = sum(costs) if costs else None
        metrics.duration_ms_total = sum(c.duration_ms for c in run.llm_calls)
        failed_calls = [c for c in run.llm_calls if not c.ok]
        if failed_calls:
            metrics.other_errors.append(f"{len(failed_calls)}/{len(run.llm_calls)} LLM calls failed and fell back to rules-only.")

    if len(run.issues) != len(cases):
        metrics.other_errors.append(f"Expected {len(cases)} grouped issues, produced {len(run.issues)}.")

    for c in cases:
        key = ",".join(c["source_message_ids"])
        iss, group_ok, group_err = _match_issue(c["source_message_ids"], run.issues)
        if iss is None:
            out = MethodCaseOutcome(grouping_ok=False, notes=[group_err or "Missing issue"])
            outcomes[key] = out
            metrics.other_errors.append(group_err or f"Missing {key}")
            disagreements.append(DisagreementItem(
                source_message_ids=c["source_message_ids"], booking_id=c["booking_id"], variant=variant_label,
                kind="grouping", expected=str(c["source_message_ids"]), actual="missing", explanation=group_err or "Missing",
            ))
            continue

        raw_or_ai: Recommendation | None = getattr(iss, use_field)
        if raw_or_ai is None and use_field in ("ai_raw", "ai_guarded"):
            err_note = f"AI failed ({iss.ai_error or 'unavailable'}); rules fallback not credited as AI accuracy"
            outcomes[key] = MethodCaseOutcome(
                matched_issue_id=iss.issue_id,
                grouping_ok=group_ok,
                notes=[err_note],
            )
            metrics.other_errors.append(f"{key}: {err_note}")
            disagreements.append(DisagreementItem(
                source_message_ids=c["source_message_ids"],
                booking_id=c["booking_id"],
                variant=variant_label,
                kind="ai_failure",
                expected=f"{c['action_code']} ({c['contact_channel']})",
                actual="ai_failed_fallback_to_rules",
                explanation=err_note,
            ))
            if group_ok:
                metrics.grouping_correct += 1
            continue

        rec: Recommendation = raw_or_ai or iss.final
        ctx = IssueContext(group=iss.group, messages=iss.messages, booking=iss.booking)
        pref = rec.signals.contact_preference if rec.signals else None
        findings = find_unsupported_promises(rec.draft_response, ctx, rec.contact_channel, pref)
        # Also verify no guess-linked booking IDs in draft when booking_id is None
        promise_strs_extra: list[str] = []
        if c["booking_id"] is None and iss.group.booking_match.possible_candidates and rec.draft_response:
            for cand in iss.group.booking_match.possible_candidates:
                if cand in rec.draft_response:
                    promise_strs_extra.append(f"unverified_booking_link: mentions {cand} without confirmation")
                    break

        promise_strs = [f"{f.kind}: {f.reason} ('{f.text}')" for f in findings] + promise_strs_extra
        action_ok = (rec.action_code.value == c["action_code"]) and (rec.contact_channel.value == c["contact_channel"])
        dept_ok = rec.responsible_department.value == c["responsible_department"]
        urg_ok = rec.urgency.value == c["urgency"]
        status_ok = _status_matches(rec.status, c["status"])
        miss_ok, missed_keys = _missing_info_matches(rec.missing_information, c.get("must_flag_missing", []), synonyms)

        notes: list[str] = []
        if not group_ok and group_err:
            notes.append(group_err)
            metrics.other_errors.append(group_err)
            disagreements.append(DisagreementItem(
                source_message_ids=c["source_message_ids"], booking_id=c["booking_id"], variant=variant_label,
                kind="grouping", expected=str(c["source_message_ids"]), actual=str(iss.group.source_message_ids),
                explanation=group_err,
            ))
        if not action_ok:
            msg = f"Expected {c['action_code']} via {c['contact_channel']}, got {rec.action_code.value} via {rec.contact_channel.value}"
            notes.append(msg)
            metrics.other_errors.append(f"{key}: {msg}")
            disagreements.append(DisagreementItem(
                source_message_ids=c["source_message_ids"], booking_id=c["booking_id"], variant=variant_label,
                kind="next_action", expected=f"{c['action_code']} ({c['contact_channel']})",
                actual=f"{rec.action_code.value} ({rec.contact_channel.value})",
                explanation=f"{msg}. Reason: {rec.explanation}",
            ))
        if not dept_ok:
            msg = f"Department expected {c['responsible_department']}, got {rec.responsible_department.value}"
            notes.append(msg)
            metrics.other_errors.append(f"{key}: {msg}")
        if not urg_ok:
            msg = f"Urgency expected {c['urgency']}, got {rec.urgency.value}"
            notes.append(msg)
            metrics.other_errors.append(f"{key}: {msg}")
        if not status_ok:
            msg = f"Status expected {c['status']}, got {rec.status.value}"
            notes.append(msg)
            metrics.other_errors.append(f"{key}: {msg}")
        if not miss_ok:
            msg = f"Missing info omitted required topics: {missed_keys}"
            notes.append(msg)
            metrics.other_errors.append(f"{key}: {msg}")
        if promise_strs:
            notes.extend(promise_strs)
            disagreements.append(DisagreementItem(
                source_message_ids=c["source_message_ids"], booking_id=c["booking_id"], variant=variant_label,
                kind="unsupported_promise", expected="No unsupported promises", actual="; ".join(promise_strs),
                explanation="Draft response or contact channel breached a booking-register or contact-preference guardrail.",
            ))

        if action_ok:
            metrics.correct_next_actions += 1
        if dept_ok:
            metrics.department_correct += 1
        if urg_ok:
            metrics.urgency_correct += 1
        if status_ok:
            metrics.status_correct += 1
        if miss_ok:
            metrics.missing_info_complete += 1
        if group_ok:
            metrics.grouping_correct += 1
        if promise_strs:
            metrics.unsupported_promises += 1

        outcomes[key] = MethodCaseOutcome(
            matched_issue_id=iss.issue_id, action_code=rec.action_code.value, contact_channel=rec.contact_channel.value,
            department=rec.responsible_department.value, urgency=rec.urgency.value, status=rec.status.value,
            action_correct=action_ok, department_correct=dept_ok, urgency_correct=urg_ok, status_correct=status_ok,
            missing_info_ok=miss_ok, grouping_ok=group_ok, unsupported_promises=promise_strs, notes=notes,
        )

    if use_field in ("ai_raw", "ai_guarded"):
        pairs = [
            (getattr(iss, use_field), IssueContext(group=iss.group, messages=iss.messages, booking=iss.booking))
            for iss in run.issues
            if getattr(iss, use_field) is not None
        ]
    else:
        pairs = [(getattr(iss, use_field) or iss.final, IssueContext(group=iss.group, messages=iss.messages, booking=iss.booking)) for iss in run.issues]
    if use_field == "ai_raw":
        pairs.sort(key=lambda pair: (
            URGENCY_ORDER[pair[0].urgency],
            min((m.received_at_ist for m in pair[1].messages if m.received_at_ist), default=datetime.max),
        ))
    fc = first_callback(pairs) if pairs else None
    fc_ids = fc[1].group.source_message_ids if fc else []
    metrics.first_callback_actual = fc_ids
    if exp_first:
        metrics.first_callback_correct = set(fc_ids) == set(exp_first)
        if not metrics.first_callback_correct:
            metrics.other_errors.append(f"First callback expected {exp_first}, got {fc_ids}")

    return metrics, outcomes, disagreements


def run_full_evaluation_with_run(
    ingest: IngestResult,
    snapshot: str,
    dataset: str,
    expected_path: Path,
    client: OpenRouterClient | None = None,
    include_ai: bool = False,
    human_corrections_count: int = 0,
    ai_prompt_version: str = "v1",
) -> tuple[EvaluationReport, RunResult | None]:
    expected = load_expected(expected_path)
    cases = expected["cases"]

    r1 = run_rules(ingest, snapshot, version="v1", dataset=dataset)
    r2 = run_rules(ingest, snapshot, version="v2", dataset=dataset)
    m1, out1, dis1 = evaluate_run(r1, expected, "rules_v1", "Rules Baseline (v1 - English Keywords)")
    m2, out2, dis2 = evaluate_run(r2, expected, "rules_v2", "Rules Improved (v2 - Targeted Hinglish Phrases)")

    methods = [m1, m2]
    all_outcomes = {"rules_v1": out1, "rules_v2": out2}
    all_disagreements = dis1 + dis2
    ai_run: RunResult | None = None
    sample_llm_calls: list[dict[str, Any]] = []

    if include_ai and client and client.api_key and not client.simulated:
        ai_run = run_ai(ingest, snapshot, client, prompt_version=ai_prompt_version, dataset=dataset, rules_version="v2")
        m_ai_raw, out_ai_raw, dis_ai_raw = evaluate_run(
            ai_run, expected, f"ai_{ai_prompt_version}_raw", f"AI Raw ({client.model}, prompt {ai_prompt_version})", use_field="ai_raw"
        )
        m_ai_guarded, out_ai_guarded, dis_ai_guarded = evaluate_run(
            ai_run, expected, f"ai_{ai_prompt_version}_guarded", f"AI Guarded ({client.model}, prompt {ai_prompt_version})", use_field="ai_guarded"
        )
        if ai_run.status == "failed":
            m_ai_raw.status = "failed"
            m_ai_guarded.status = "failed"
        methods.extend([m_ai_raw, m_ai_guarded])
        all_outcomes[m_ai_raw.variant] = out_ai_raw
        all_outcomes[m_ai_guarded.variant] = out_ai_guarded
        all_disagreements.extend(dis_ai_raw + dis_ai_guarded)
        sample_llm_calls = [
            {
                "call_id": c.call_id,
                "issue_id": c.issue_id,
                "ok": c.ok,
                "model_requested": c.model_requested,
                "model_used": c.model_used,
                "provider_upstream": c.provider_upstream,
                "duration_ms": c.duration_ms,
                "attempts": c.attempts,
                "prompt_tokens": c.prompt_tokens,
                "completion_tokens": c.completion_tokens,
                "total_tokens": c.total_tokens,
                "cost_usd": c.cost_usd,
                "raw_content": c.raw_content,
                "error_type": c.error_type,
                "error_message": c.error_message,
            }
            for c in ai_run.llm_calls
        ]
    else:
        model_name = client.model if client else "google/gemini-2.5-flash"
        methods.append(MethodMetrics(
            variant=f"ai_{ai_prompt_version}_live",
            label=f"AI-Assisted OpenRouter ({model_name})",
            mode="ai",
            status="pending_credentials",
            model=model_name,
            total_cases=len(cases),
            note=("OPENROUTER_API_KEY is not configured in the backend environment. "
                  "Live OpenRouter execution is marked pending — no simulated or fabricated model output is included."),
        ))

    rows: list[CaseComparisonRow] = []
    for c in cases:
        key = ",".join(c["source_message_ids"])
        per_method = {v: om[key] for v, om in all_outcomes.items() if key in om}
        rows.append(CaseComparisonRow(
            source_message_ids=c["source_message_ids"],
            booking_id=c["booking_id"],
            expected_category=c["issue_category"],
            expected_action_code=c["action_code"],
            expected_channel=c["contact_channel"],
            expected_department=c["responsible_department"],
            expected_urgency=c["urgency"],
            expected_status=c["status"],
            must_flag_missing=c.get("must_flag_missing", []),
            rationale=c["rationale"],
            outcomes=per_method,
        ))

    ctxs = group_messages(ingest.messages, ingest.bookings)
    sample_requests = [build_user_payload(ctx, snapshot) for ctx in ctxs[:4]]

    report = EvaluationReport(
        eval_id=f"eval_{dataset}-{uuid.uuid4().hex[:6]}",
        dataset=dataset,
        snapshot_time_ist=snapshot,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        expected_file=expected_path.name,
        total_cases=len(cases),
        expected_first_callback=expected.get("expected_first_callback", []),
        human_corrections_count=human_corrections_count,
        methods=methods,
        case_comparisons=rows,
        disagreements_and_failures=all_disagreements,
        improvement_summary=ImprovementSummary(
            before_variant="rules_v1",
            after_variant="rules_v2",
            before_correct=m1.correct_next_actions,
            after_correct=m2.correct_next_actions,
            total=len(cases),
            delta_correct=m2.correct_next_actions - m1.correct_next_actions,
            before_unsupported_promises=m1.unsupported_promises,
            after_unsupported_promises=m2.unsupported_promises,
            change_description=(
                "Added targeted Hinglish schedule-change, arrival-gap, and call-request patterns plus requested_change "
                "time extraction in rules_v2 after observing rules_v1 fall back to MANUAL_TRIAGE on Hinglish messages "
                "(M04 on supplied shift; H01 on harder synthetic set)."
            ),
        ),
        sample_llm_requests=sample_requests,
        sample_llm_calls=sample_llm_calls,
        limitations=[
            "Supplied shift dataset has only n=8 distinct issues (12 messages); results are illustrative, not statistically significant.",
            "Harder test cases are synthetic examples authored specifically to stress Hinglish, negation, conflicting claims and channel constraints.",
            "Live OpenRouter evaluation requires a valid OPENROUTER_API_KEY; mocked/unit-tested OpenRouter calls are strictly isolated in pytest and never reported as real evaluations.",
        ],
    )
    return report, ai_run


def run_full_evaluation(
    ingest: IngestResult,
    snapshot: str,
    dataset: str,
    expected_path: Path,
    client: OpenRouterClient | None = None,
    include_ai: bool = False,
    human_corrections_count: int = 0,
    ai_prompt_version: str = "v1",
) -> EvaluationReport:
    report, _ = run_full_evaluation_with_run(
        ingest=ingest,
        snapshot=snapshot,
        dataset=dataset,
        expected_path=expected_path,
        client=client,
        include_ai=include_ai,
        human_corrections_count=human_corrections_count,
        ai_prompt_version=ai_prompt_version,
    )
    return report
