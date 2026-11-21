"""CSV, XLSX and Markdown exports for operational queues, evaluation comparisons and issue reports."""
from __future__ import annotations

import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.modules.evaluation import EvaluationReport
from app.schemas import IngestResult, ReviewRecord, RunResult


def _auto_fit(ws) -> None:
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val = str(cell.value or "")
            max_line = max((len(line) for line in val.splitlines()), default=0)
            max_len = max(max_len, min(max_line, 60))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)


def _style_header(ws, fill_hex: str = "1E3A5F") -> None:
    fill = PatternFill("solid", fgColor=fill_hex)
    font = Font(bold=True, color="FFFFFF", size=10)
    for cell in ws[1]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"


def queue_to_csv_bytes(run: RunResult) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "priority_rank", "issue_id", "booking_id", "source_message_ids", "thread_ids",
        "issue_category", "urgency", "status", "responsible_department", "supporting_departments",
        "action_code", "contact_channel", "next_action", "missing_information",
        "draft_response", "hold_contact_reason", "human_review_required", "source", "priority_reason",
    ])
    for iss in run.issues:
        f = iss.final
        writer.writerow([
            f.priority_rank, iss.issue_id, iss.group.booking_id or "-",
            ",".join(iss.group.source_message_ids), ",".join(iss.group.thread_ids),
            f.issue_category.value, f.urgency.value, f.status.value,
            f.responsible_department.value, ",".join(d.value for d in f.supporting_departments),
            f.action_code.value, f.contact_channel.value, f.next_action,
            " | ".join(f.missing_information), f.draft_response or "",
            f.hold_contact_reason or "", f.human_review_required, f.source, f.priority_reason,
        ])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def queue_to_xlsx_bytes(run: RunResult, ingest: IngestResult, reviews: list[ReviewRecord]) -> bytes:
    wb = Workbook()
    ws_sum = wb.active
    ws_sum.title = "Summary"
    ws_sum.append(["Metric", "Value"])
    ws_sum.append(["Run ID", run.run_id])
    ws_sum.append(["Dataset", run.dataset])
    ws_sum.append(["Mode / Variant", f"{run.mode} / {run.variant}"])
    ws_sum.append(["Model", run.model or "None (Rules-Only)"])
    ws_sum.append(["Run Status", run.status])
    ws_sum.append(["Total Messages", len(ingest.messages)])
    ws_sum.append(["Distinct Issues", len(run.issues)])
    ws_sum.append(["Open / Awaiting Info Issues", sum(1 for i in run.issues if i.final.status.value != "resolved")])
    ws_sum.append(["Resolved Issues", sum(1 for i in run.issues if i.final.status.value == "resolved")])
    ws_sum.append(["Human Review Required", sum(1 for i in run.issues if i.final.human_review_required)])
    ws_sum.append(["Data Quality Findings", len(ingest.dq_issues)])
    ws_sum.append(["Human Corrections Logged", len(reviews)])
    _style_header(ws_sum)
    _auto_fit(ws_sum)

    ws_q = wb.create_sheet("Priority Queue")
    ws_q.append([
        "Rank", "Issue ID", "Booking ID", "Source IDs", "Category", "Urgency", "Status",
        "Owner Dept", "Supporting Depts", "Action Code", "Channel", "Next Action",
        "Missing Information", "Draft Response / Hold Reason", "Human Review", "Source", "Priority Rationale",
    ])
    for iss in run.issues:
        f = iss.final
        ws_q.append([
            f.priority_rank, iss.issue_id, iss.group.booking_id or "-",
            ", ".join(iss.group.source_message_ids), f.issue_category.value,
            f.urgency.value.upper(), f.status.value, f.responsible_department.value,
            ", ".join(d.value for d in f.supporting_departments), f.action_code.value,
            f.contact_channel.value, f.next_action, "; ".join(f.missing_information) or "-",
            f.draft_response or f"[HOLD] {f.hold_contact_reason or ''}",
            "Yes" if f.human_review_required else "No", f.source, f.priority_reason,
        ])
    _style_header(ws_q)
    for row in ws_q.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    _auto_fit(ws_q)

    ws_m = wb.create_sheet("Message Timeline")
    ws_m.append(["Event ID", "Issue ID", "Received IST", "Thread", "Booking Ref", "Channel", "Sender", "Original Message", "Normalised Text"])
    msg_to_issue = {mid: iss.issue_id for iss in run.issues for mid in iss.group.source_message_ids}
    for m in ingest.messages:
        ws_m.append([
            m.event_id, msg_to_issue.get(m.event_id, "-"),
            m.received_at_ist.strftime("%Y-%m-%d %H:%M") if m.received_at_ist else "-",
            m.thread_id or "-", m.booking_id or "-", m.channel or "-", m.sender or "-",
            m.message, m.text_normalised,
        ])
    _style_header(ws_m)
    _auto_fit(ws_m)

    ws_dq = wb.create_sheet("Data Quality")
    ws_dq.append(["Source File", "Record ID", "Field", "Issue Type", "Severity", "Original Value", "Normalised Value", "Problem", "Recommended Action", "Human Review"])
    for d in ingest.dq_issues:
        ws_dq.append([
            d.source_file, d.record_id, d.field, d.issue_type, d.severity.upper(),
            d.original_value or "", d.normalised_value or "", d.problem, d.recommended_action,
            "Yes" if d.human_review_required else "No",
        ])
    _style_header(ws_dq)
    _auto_fit(ws_dq)

    ws_r = wb.create_sheet("Human Reviews")
    ws_r.append(["Review ID", "Created At", "Issue ID", "Action", "Reviewer", "Reason", "Before Snapshot"])
    for r in reviews:
        ws_r.append([r.review_id, r.created_at, r.issue_id, r.action, r.reviewer, r.reason or "", str(r.before)])
    _style_header(ws_r)
    _auto_fit(ws_r)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def evaluation_to_csv_bytes(report: EvaluationReport) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "dataset", "variant", "label", "mode", "status", "model", "total_cases",
        "correct_next_actions", "unsupported_promises", "department_correct",
        "urgency_correct", "status_correct", "missing_info_complete", "grouping_correct",
        "first_callback_correct", "first_callback_actual", "note",
    ])
    for m in report.methods:
        writer.writerow([
            report.dataset, m.variant, m.label, m.mode, m.status, m.model or "",
            m.total_cases, m.correct_next_actions, m.unsupported_promises,
            m.department_correct, m.urgency_correct, m.status_correct,
            m.missing_info_complete, m.grouping_correct, m.first_callback_correct,
            ",".join(m.first_callback_actual), m.note,
        ])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def evaluation_to_xlsx_bytes(supplied: EvaluationReport, harder: EvaluationReport | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary Comparison"
    ws.append([
        "Dataset", "Variant", "Status", "Model", "Correct Next Actions", "Total Cases",
        "Unsupported Promises", "Dept Correct", "Urgency Correct", "Status Correct",
        "Missing Info Complete", "Grouping Correct", "First Callback OK", "Note",
    ])
    for rep in [r for r in (supplied, harder) if r is not None]:
        for m in rep.methods:
            ws.append([
                rep.dataset, m.variant, m.status, m.model or "-",
                f"{m.correct_next_actions}/{m.total_cases}" if m.status == "evaluated" else "Pending",
                m.total_cases,
                m.unsupported_promises if m.status == "evaluated" else "-",
                m.department_correct if m.status == "evaluated" else "-",
                m.urgency_correct if m.status == "evaluated" else "-",
                m.status_correct if m.status == "evaluated" else "-",
                m.missing_info_complete if m.status == "evaluated" else "-",
                m.grouping_correct if m.status == "evaluated" else "-",
                str(m.first_callback_correct) if m.first_callback_correct is not None else "-",
                m.note,
            ])
    _style_header(ws)
    _auto_fit(ws)

    def _add_cases_sheet(title: str, rep: EvaluationReport) -> None:
        ws_c = wb.create_sheet(title)
        variants = [m.variant for m in rep.methods if m.status == "evaluated"]
        header = ["Source IDs", "Booking", "Expected Category", "Expected Action", "Expected Channel", "Expected Dept", "Expected Urgency"]
        for v in variants:
            header += [f"{v} Action", f"{v} Channel", f"{v} Match", f"{v} Promises"]
        ws_c.append(header)
        for row in rep.case_comparisons:
            vals = [
                ", ".join(row.source_message_ids), row.booking_id or "-", row.expected_category,
                row.expected_action_code, row.expected_channel, row.expected_department, row.expected_urgency,
            ]
            for v in variants:
                oc = row.outcomes.get(v)
                if oc:
                    vals += [oc.action_code or "-", oc.contact_channel or "-", "PASS" if oc.action_correct else "FAIL", "; ".join(oc.unsupported_promises) or "0"]
                else:
                    vals += ["-", "-", "-", "-"]
            ws_c.append(vals)
        _style_header(ws_c)
        _auto_fit(ws_c)

    _add_cases_sheet("Supplied Cases", supplied)
    if harder:
        _add_cases_sheet("Harder Synthetic Cases", harder)

    ws_d = wb.create_sheet("Failures & Improvement")
    ws_d.append(["Dataset", "Source IDs", "Booking", "Variant", "Kind", "Expected", "Actual", "Explanation"])
    for rep in [r for r in (supplied, harder) if r is not None]:
        for d in rep.disagreements_and_failures:
            ws_d.append([rep.dataset, ", ".join(d.source_message_ids), d.booking_id or "-", d.variant, d.kind, d.expected, d.actual, d.explanation])
        imp = rep.improvement_summary
        ws_d.append([
            rep.dataset, "ALL", "-", f"{imp.before_variant} -> {imp.after_variant}", "improvement",
            f"{imp.before_correct}/{imp.total}", f"{imp.after_correct}/{imp.total} (+{imp.delta_correct})",
            imp.change_description,
        ])
    _style_header(ws_d)
    _auto_fit(ws_d)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def issues_report_markdown(run: RunResult, ingest: IngestResult, reviews: list[ReviewRecord]) -> str:
    lines = [
        f"# EzyHelpers Shift Triage Report ({run.dataset})",
        "",
        f"- **Run ID:** `{run.run_id}`",
        f"- **Mode / Variant:** `{run.mode}` / `{run.variant}`",
        f"- **Model:** `{run.model or 'None (Rules-Only)'}`",
        f"- **Run Status:** `{run.status}`",
        f"- **Messages Ingested:** {len(ingest.messages)} | **Distinct Issues:** {len(run.issues)} | **DQ Issues:** {len(ingest.dq_issues)} | **Human Reviews:** {len(reviews)}",
        "",
        "## Prioritised Queue",
        "",
        "| Rank | Issue | Booking | Source IDs | Urgency | Dept | Channel | Action | Status |",
        "|---:|---|---|---|---|---|---|---|---|",
    ]
    for iss in run.issues:
        f = iss.final
        lines.append(
            f"| {f.priority_rank} | {iss.issue_id} | {iss.group.booking_id or '-'} | "
            f"{', '.join(iss.group.source_message_ids)} | {f.urgency.value} | {f.responsible_department.value} | "
            f"{f.contact_channel.value} | `{f.action_code.value}` | {f.status.value} |"
        )
    lines.append("")
    lines.append("## Issue Details & Drafts (Drafts Only — Never Auto-Sent)")
    for iss in run.issues:
        f = iss.final
        lines += [
            "",
            f"### #{f.priority_rank} {iss.issue_id} ({iss.group.booking_id or 'Unlinked'}) — {f.urgency.value.upper()}",
            f"- **Source Messages:** {', '.join(iss.group.source_message_ids)}",
            f"- **Owner:** {f.responsible_department.value} | **Channel:** {f.contact_channel.value} | **Source:** `{f.source}`",
            f"- **Priority Reason:** {f.priority_reason}",
            f"- **Next Action:** {f.next_action}",
            f"- **Missing Info:** {'; '.join(f.missing_information) if f.missing_information else 'None'}",
            f"- **Draft / Hold:** {f.draft_response or '[HOLD] ' + (f.hold_contact_reason or '')}",
        ]
    return "\n".join(lines) + "\n"

