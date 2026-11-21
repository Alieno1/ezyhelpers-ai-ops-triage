"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  FileWarning,
  MessageCircle,
  ShieldCheck,
} from "lucide-react";
import { useDataset } from "@/components/DatasetContext";
import {
  ChannelBadge,
  DepartmentBadge,
  ErrorBanner,
  LoadingPanel,
  SeverityBadge,
  SourceBadge,
  StatusBadge,
  SuccessBanner,
  UrgencyBadge,
  formatShortTime,
} from "@/components/ui";
import { getIssueDetail, submitReview } from "@/lib/api";
import type { DQIssue, IssueResult, Recommendation, ReviewRecord } from "@/lib/types";

const ACTION_CODES = [
  "CARE_GAP_IMMEDIATE",
  "CARE_GAP_COVERED_CHASE_SOURCING",
  "SERVICE_GAP_CHECK_ARRIVAL",
  "CLOSE_CONFIRMED_ARRIVAL",
  "SCHEDULE_CHANGE_SOURCING_CHECK",
  "BILLING_VERIFY_DISPUTED_REFUND",
  "RELAY_APPROVED_REFUND_CHASE_PAYOUT",
  "RELAY_CONFIRMED_REFUND_FACTS",
  "SALES_ENQUIRY_NO_QUOTE",
  "ASK_MINIMUM_BOOKING_IDENTITY",
  "MANUAL_TRIAGE",
];

export default function IssueDetailPage() {
  const params = useParams<{ issueId: string }>();
  const issueId = params?.issueId || "ISS-01";
  const { dataset } = useDataset();

  const [issue, setIssue] = useState<IssueResult | null>(null);
  const [reviews, setReviews] = useState<ReviewRecord[]>([]);
  const [dqRelated, setDqRelated] = useState<DQIssue[]>([]);
  const [runMeta, setRunMeta] = useState<{ run_id: string; mode: string; variant: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showNormalised, setShowNormalised] = useState(false);
  const [recTab, setRecTab] = useState<"final" | "rules" | "ai">("final");

  // Review form state
  const [action, setAction] = useState("approve");
  const [reviewer, setReviewer] = useState("coordinator");
  const [reason, setReason] = useState("");
  const [urgency, setUrgency] = useState("critical");
  const [department, setDepartment] = useState("Duty Ops");
  const [actionCode, setActionCode] = useState("CARE_GAP_IMMEDIATE");
  const [nextAction, setNextAction] = useState("");
  const [draftText, setDraftText] = useState("");
  const [infoRequested, setInfoRequested] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getIssueDetail(issueId, dataset);
      setIssue(res.issue);
      setReviews(res.reviews);
      setDqRelated(res.dq_related);
      setRunMeta({ run_id: res.run_id, mode: res.mode, variant: res.variant });
      const f = res.issue.final;
      setUrgency(f.urgency);
      setDepartment(f.responsible_department);
      setActionCode(f.action_code);
      setNextAction(f.next_action);
      setDraftText(f.draft_response || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load issue details");
    } finally {
      setLoading(false);
    }
  }, [issueId, dataset]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setSaveMsg(null);
    setSaveErr(null);
    try {
      const payload: Record<string, unknown> = {
        action,
        reviewer: reviewer.trim() || "coordinator",
        reason: reason.trim() || null,
      };
      if (action === "change_priority") payload.urgency = urgency;
      if (action === "change_department") payload.department = department;
      if (action === "correct_action") {
        payload.action_code = actionCode;
        payload.next_action = nextAction;
      }
      if (action === "edit_draft") payload.draft_response = draftText;
      if (action === "request_info") payload.info_requested = infoRequested;

      await submitReview(issueId, dataset, payload);
      setSaveMsg(`Saved review action '${action}' and refreshed priority rank.`);
      setReason("");
      await load();
    } catch (err) {
      setSaveErr(err instanceof Error ? err.message : "Failed to submit review");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <LoadingPanel />;
  if (error || !issue) return <ErrorBanner message={error || "Issue not found"} />;

  const f = issue.final;
  const activeRec: Recommendation | null =
    recTab === "final" ? issue.final : recTab === "rules" ? issue.rules : issue.ai_guarded || issue.ai_raw;

  const inputCls =
    "w-full rounded-lg border border-slate-300 bg-white text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start sm:items-center gap-3 min-w-0">
          <Link
            href="/queue"
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800 shrink-0"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Queue
          </Link>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
                #{f.priority_rank} · {issue.issue_id}
              </h1>
              <UrgencyBadge urgency={f.urgency} />
              <DepartmentBadge department={f.responsible_department} />
              <StatusBadge status={f.status} />
              <SourceBadge source={f.source} />
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 break-words">
              Booking: <span className="font-mono font-semibold">{issue.group.booking_id || "Unlinked"}</span> · Messages:{" "}
              <span className="font-mono">{issue.group.source_message_ids.join(", ")}</span>
              {runMeta && <span className="ml-0 sm:ml-2 block sm:inline">· Run {runMeta.run_id}</span>}
            </p>
          </div>
        </div>
        <div className="shrink-0">
          <ChannelBadge channel={f.contact_channel} />
        </div>
      </div>

      {/* Priority Rationale Banner */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4 shadow-xs">
        <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Priority Rationale</div>
        <div className="mt-1 text-sm text-slate-900 dark:text-slate-100 font-medium break-words">{f.priority_reason}</div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left 2 cols: Evidence, Timeline, Recommendations */}
        <div className="lg:col-span-2 space-y-5 min-w-0">
          {/* Message Timeline */}
          <section className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                <MessageCircle className="w-4 h-4 text-slate-600 dark:text-slate-400" />
                Chronological Message Timeline ({issue.messages.length})
              </h2>
              <label className="inline-flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showNormalised}
                  onChange={(e) => setShowNormalised(e.target.checked)}
                />
                Show normalised text
              </label>
            </div>
            <div className="space-y-3">
              {issue.messages.map((m) => (
                <div
                  key={m.event_id}
                  className={`rounded-lg border p-3.5 ${
                    m.is_internal
                      ? "bg-amber-50/40 border-amber-200 dark:bg-amber-950/30 dark:border-amber-800"
                      : "bg-slate-50 border-slate-200 dark:bg-slate-800/60 dark:border-slate-700"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-slate-900 dark:text-slate-100">{m.event_id}</span>
                      <span className="px-1.5 py-0.5 rounded bg-white border border-slate-200 dark:bg-slate-900 dark:border-slate-700 font-medium text-slate-700 dark:text-slate-200">
                        {m.sender || "Unknown"} · {m.channel || "-"}
                      </span>
                      {m.is_internal && (
                        <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/70 dark:text-amber-200 font-medium">
                          Internal Note
                        </span>
                      )}
                    </div>
                    <span className="inline-flex items-center gap-1 font-mono">
                      <Clock className="w-3 h-3" /> {m.received_at_ist || "-"} · Thread {m.thread_id || "-"}
                    </span>
                  </div>
                  <div className="mt-2 text-sm text-slate-900 dark:text-slate-100 leading-relaxed">{m.message}</div>
                  {showNormalised && (
                    <div className="mt-2 pt-2 border-t border-slate-200 dark:border-slate-700 text-xs text-slate-500 dark:text-slate-400 font-mono">
                      Normalised: {m.text_normalised}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="pt-2 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400 space-y-1">
              <div className="font-semibold text-slate-700 dark:text-slate-200">Grouping Logic:</div>
              {issue.group.grouping_reasons.map((r, idx) => (
                <div key={idx}>• {r}</div>
              ))}
            </div>
          </section>

          {/* Booking Register & Missing Info */}
          <section className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs space-y-4">
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">Booking Register Authority & Missing Facts</h2>
            {issue.booking ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs bg-slate-50 rounded-lg border border-slate-200 dark:bg-slate-800/60 dark:border-slate-700 p-3.5">
                <div>
                  <span className="text-slate-500 dark:text-slate-400">Booking ID:</span>{" "}
                  <strong className="font-mono text-slate-900 dark:text-slate-100">{issue.booking.booking_id}</strong>
                </div>
                <div>
                  <span className="text-slate-500 dark:text-slate-400">Service / Locality:</span>{" "}
                  <strong className="text-slate-900 dark:text-slate-100">
                    {issue.booking.service} · {issue.booking.locality}
                  </strong>
                </div>
                <div>
                  <span className="text-slate-500 dark:text-slate-400">Scheduled Start (IST):</span>{" "}
                  <strong className="font-mono text-slate-900 dark:text-slate-100">{issue.booking.scheduled_start_ist || "Closed / None"}</strong>
                </div>
                <div>
                  <span className="text-slate-500 dark:text-slate-400">Register Updated (IST):</span>{" "}
                  <strong className="font-mono text-slate-900 dark:text-slate-100">{issue.booking.updated_at_ist || "-"}</strong>
                </div>
                <div className="sm:col-span-2">
                  <span className="text-slate-500 dark:text-slate-400">Operations Record:</span>{" "}
                  <span className="text-slate-900 dark:text-slate-100 font-medium">{issue.booking.operations_record || "-"}</span>
                </div>
                <div className="sm:col-span-2">
                  <span className="text-slate-500 dark:text-slate-400">Billing Record:</span>{" "}
                  <span className="text-slate-900 dark:text-slate-100 font-medium">{issue.booking.billing_record || "None recorded"}</span>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40 p-3 text-xs text-amber-900 dark:text-amber-200">
                <strong>No Matched Booking:</strong> {issue.group.booking_match.note}
              </div>
            )}

            <div>
              <div className="text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1.5">Missing Information</div>
              {f.missing_information.length === 0 ? (
                <div className="text-xs text-emerald-700 dark:text-emerald-400">No missing information flagged.</div>
              ) : (
                <ul className="list-disc pl-5 text-xs text-slate-700 dark:text-slate-300 space-y-1">
                  {f.missing_information.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              )}
            </div>

            {dqRelated.length > 0 && (
              <div>
                <div className="text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1.5 flex items-center gap-1.5">
                  <FileWarning className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" /> Linked Data-Quality Findings
                </div>
                <div className="space-y-1.5">
                  {dqRelated.map((d, i) => (
                    <div key={i} className="text-xs flex items-start gap-2 bg-slate-50 border border-slate-200 dark:bg-slate-800/60 dark:border-slate-700 rounded p-2">
                      <SeverityBadge severity={d.severity} />
                      <div>
                        <span className="font-mono font-semibold">{d.field}</span>: {d.problem}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* Recommendations Comparison & Draft */}
          <section className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 dark:border-slate-800 pb-3">
              <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">Recommendation & Safe Draft</h2>
              <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-lg text-xs">
                {(["final", "rules", "ai"] as const).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setRecTab(tab)}
                    className={`px-2.5 py-1 rounded-md font-medium capitalize ${
                      recTab === tab
                        ? "bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100 shadow-xs"
                        : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
                    }`}
                  >
                    {tab === "ai" ? `AI (${issue.ai_status})` : tab}
                  </button>
                ))}
              </div>
            </div>

            {activeRec ? (
              <div className="space-y-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <UrgencyBadge urgency={activeRec.urgency} />
                  <DepartmentBadge department={activeRec.responsible_department} />
                  <ChannelBadge channel={activeRec.contact_channel} />
                  <code className="text-xs bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded font-mono text-slate-700 dark:text-slate-200 break-all sm:break-words">
                    {activeRec.action_code}
                  </code>
                </div>
                <div>
                  <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase">Next Action</div>
                  <div className="mt-0.5 text-slate-900 dark:text-slate-100 break-words">{activeRec.next_action}</div>
                </div>
                <div>
                  <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase">Explanation</div>
                  <div className="mt-0.5 text-xs text-slate-700 dark:text-slate-300 break-words">{activeRec.explanation}</div>
                </div>

                {/* Draft Box */}
                <div className="rounded-lg border border-amber-300 bg-amber-50/50 dark:border-amber-800 dark:bg-amber-950/30 p-3.5 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                    <span className="font-bold text-amber-900 dark:text-amber-300 flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4 text-amber-700 dark:text-amber-400 shrink-0" />
                      DRAFT ONLY — NOT SENT AUTOMATICALLY
                    </span>
                    <span className="text-amber-700 dark:text-amber-400">Coordinator approval required</span>
                  </div>
                  {activeRec.draft_response ? (
                    <div className="text-sm text-slate-900 dark:text-slate-100 bg-white dark:bg-slate-900 rounded border border-amber-200 dark:border-amber-800/70 p-3">
                      {activeRec.draft_response}
                    </div>
                  ) : (
                    <div className="text-xs text-slate-700 dark:text-slate-300 italic">
                      Hold contact: {activeRec.hold_contact_reason || "No outgoing reply drafted."}
                    </div>
                  )}
                </div>

                {activeRec.guardrail_events.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1">Guardrail Events</div>
                    <ul className="text-xs space-y-1 text-slate-600 dark:text-slate-300">
                      {activeRec.guardrail_events.map((g, i) => (
                        <li key={i} className="bg-slate-50 border border-slate-200 dark:bg-slate-800/60 dark:border-slate-700 rounded p-2">
                          <strong>{g.rule_id}</strong> ({g.field}): {g.reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div>
                  <div className="text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1">Supporting Source Evidence</div>
                  <div className="space-y-1">
                    {activeRec.evidence.map((ev, idx) => (
                      <div key={idx} className="text-xs text-slate-600 dark:text-slate-300 flex gap-2">
                        <span className="font-mono font-semibold text-slate-800 dark:text-slate-200 shrink-0">[{ev.source_id}]</span>
                        <span>{ev.quote}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60 p-4 text-xs text-slate-600 dark:text-slate-300">
                AI output was not produced for this issue ({issue.ai_error || "AI has not been run yet or API key is pending"}).
                The system cleanly operates on deterministic rules.
              </div>
            )}
          </section>
        </div>

        {/* Right Col: Human Review Form & Audit Trail */}
        <div className="space-y-5">
          <section className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs space-y-4">
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              Coordinator Review Decision
            </h2>
            {f.human_review_reasons.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40 p-3 text-xs text-amber-900 dark:text-amber-200 space-y-1">
                <div className="font-semibold flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5" /> Review Notes
                </div>
                {f.human_review_reasons.map((r, i) => (
                  <div key={i}>• {r}</div>
                ))}
              </div>
            )}

            {saveMsg && <SuccessBanner message={saveMsg} />}
            {saveErr && <ErrorBanner message={saveErr} />}

            <form onSubmit={handleSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 dark:text-slate-200 mb-1">Review Action</label>
                <select value={action} onChange={(e) => setAction(e.target.value)} className={`${inputCls} px-2.5 py-2 text-sm`}>
                  <option value="approve">Approve Recommendation</option>
                  <option value="change_priority">Change Priority / Urgency</option>
                  <option value="change_department">Change Owning Department</option>
                  <option value="correct_action">Correct Next Action</option>
                  <option value="edit_draft">Edit Draft Response</option>
                  <option value="request_info">Request More Information</option>
                  <option value="resolve">Mark Issue Resolved</option>
                  <option value="reopen">Reopen Issue</option>
                </select>
              </div>

              {action === "change_priority" && (
                <div>
                  <label className="block font-semibold text-slate-700 dark:text-slate-200 mb-1">New Urgency</label>
                  <select value={urgency} onChange={(e) => setUrgency(e.target.value)} className={`${inputCls} px-2.5 py-2 text-sm`}>
                    <option value="critical">critical</option>
                    <option value="high">high</option>
                    <option value="medium">medium</option>
                    <option value="low">low</option>
                    <option value="none">none</option>
                  </select>
                </div>
              )}

              {action === "change_department" && (
                <div>
                  <label className="block font-semibold text-slate-700 dark:text-slate-200 mb-1">New Department</label>
                  <select value={department} onChange={(e) => setDepartment(e.target.value)} className={`${inputCls} px-2.5 py-2 text-sm`}>
                    <option value="Duty Ops">Duty Ops</option>
                    <option value="Sourcing">Sourcing</option>
                    <option value="Billing">Billing</option>
                    <option value="Sales">Sales</option>
                  </select>
                </div>
              )}

              {action === "correct_action" && (
                <>
                  <div>
                    <label className="block font-semibold text-slate-700 dark:text-slate-200 mb-1">Action Code</label>
                    <select value={actionCode} onChange={(e) => setActionCode(e.target.value)} className={`${inputCls} px-2.5 py-2 text-sm`}>
                      {ACTION_CODES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block font-semibold text-slate-700 dark:text-slate-200 mb-1">Corrected Next Action</label>
                    <textarea rows={3} value={nextAction} onChange={(e) => setNextAction(e.target.value)} className={`${inputCls} p-2 text-xs`} />
                  </div>
                </>
              )}

              {action === "edit_draft" && (
                <div>
                  <label className="block font-semibold text-slate-700 dark:text-slate-200 mb-1">Draft Response Text</label>
                  <textarea rows={4} value={draftText} onChange={(e) => setDraftText(e.target.value)} className={`${inputCls} p-2 text-xs`} />
                </div>
              )}

              {action === "request_info" && (
                <div>
                  <label className="block font-semibold text-slate-700 dark:text-slate-200 mb-1">Information Needed</label>
                  <input
                    type="text"
                    required
                    value={infoRequested}
                    onChange={(e) => setInfoRequested(e.target.value)}
                    placeholder="e.g. Confirm registered phone number"
                    className={`${inputCls} px-2.5 py-2 text-xs`}
                  />
                </div>
              )}

              <div>
                <label className="block font-semibold text-slate-700 dark:text-slate-200 mb-1">Correction / Review Reason</label>
                <textarea
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Why is this approved or changed?"
                  className={`${inputCls} p-2 text-xs`}
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 dark:text-slate-200 mb-1">Reviewer Name</label>
                <input type="text" value={reviewer} onChange={(e) => setReviewer(e.target.value)} className={`${inputCls} px-2.5 py-1.5 text-xs`} />
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full py-2 px-4 rounded-lg bg-slate-900 text-white text-sm font-medium hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400 disabled:opacity-50"
              >
                {submitting ? "Saving..." : "Submit Coordinator Decision"}
              </button>
            </form>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs space-y-3">
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">Human Review Audit Trail ({reviews.length})</h2>
            {reviews.length === 0 ? (
              <div className="text-xs text-slate-500 dark:text-slate-400">No coordinator edits logged for this issue yet.</div>
            ) : (
              <div className="space-y-2.5">
                {reviews.map((r) => (
                  <div key={r.review_id} className="rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60 p-3 text-xs space-y-1">
                    <div className="flex justify-between font-semibold text-slate-900 dark:text-slate-100">
                      <span>{r.action}</span>
                      <span className="text-slate-500 dark:text-slate-400 font-normal">{r.reviewer}</span>
                    </div>
                    {r.reason && <div className="text-slate-700 dark:text-slate-300 break-words">Reason: {r.reason}</div>}
                    <div className="text-[11px] text-slate-400 dark:text-slate-500 font-mono">{formatShortTime(r.created_at)}</div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
