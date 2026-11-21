"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, ClipboardCheck } from "lucide-react";
import { useDataset } from "@/components/DatasetContext";
import {
  ChannelBadge,
  DepartmentBadge,
  ErrorBanner,
  LoadingPanel,
  SourceBadge,
  StatusBadge,
  SuccessBanner,
  UrgencyBadge,
  formatShortTime,
} from "@/components/ui";
import { getIssues, getReviews, submitReview } from "@/lib/api";
import type { IssueResult, ReviewRecord } from "@/lib/types";

export default function HumanReviewPage() {
  const { dataset } = useDataset();
  const [issues, setIssues] = useState<IssueResult[]>([]);
  const [reviews, setReviews] = useState<ReviewRecord[]>([]);
  const [showAll, setShowAll] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [issRes, revRes] = await Promise.all([
        getIssues(dataset, showAll ? undefined : { human_review_required: "true" }),
        getReviews(dataset),
      ]);
      setIssues(issRes.issues);
      setReviews(revRes.reviews);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load human review workbench");
    } finally {
      setLoading(false);
    }
  }, [dataset, showAll]);

  useEffect(() => {
    load();
  }, [load]);

  async function quickApprove(issueId: string) {
    setBanner(null);
    try {
      await submitReview(issueId, dataset, {
        action: "approve",
        reviewer: "coordinator",
        reason: "Evidence and register facts verified in workbench.",
      });
      setBanner(`${issueId} approved and cleared from pending review.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approve failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">Human Review Workbench</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Verify source evidence, approve drafts, override priorities, and inspect all recorded human corrections.
          </p>
        </div>
        <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 bg-white border border-slate-300 dark:text-slate-200 dark:bg-slate-900 dark:border-slate-700 rounded-lg px-3 py-1.5 cursor-pointer shrink-0">
          <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
          Include already-cleared issues
        </label>
      </div>

      {banner && <SuccessBanner message={banner} />}
      {error && <ErrorBanner message={error} />}

      {loading ? (
        <LoadingPanel />
      ) : (
        <>
          <section className="space-y-3">
            <h2 className="text-sm font-bold text-slate-800 dark:text-slate-200 flex items-center gap-2">
              <ClipboardCheck className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
              {showAll ? `All Issues (${issues.length})` : `Flagged for Human Review (${issues.length})`}
            </h2>
            {issues.length === 0 ? (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/40 p-6 text-sm text-emerald-800 dark:text-emerald-200">
                All issues have been reviewed and cleared. Toggle &ldquo;Include already-cleared issues&rdquo; to make further edits.
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3">
                {issues.map((iss) => {
                  const f = iss.final;
                  return (
                    <div key={iss.issue_id} className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4 shadow-xs space-y-2.5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2 flex-wrap min-w-0">
                          <span className="font-bold text-slate-900 dark:text-slate-100 tabular-nums">#{f.priority_rank}</span>
                          <Link href={`/issues/${iss.issue_id}`} className="font-bold text-slate-900 dark:text-slate-100 hover:underline">
                            {iss.issue_id}
                          </Link>
                          <span className="font-mono text-xs text-slate-500 dark:text-slate-400">{iss.group.booking_id || "Unlinked"}</span>
                          <UrgencyBadge urgency={f.urgency} />
                          <DepartmentBadge department={f.responsible_department} />
                          <ChannelBadge channel={f.contact_channel} />
                          <StatusBadge status={f.status} />
                          <SourceBadge source={f.source} />
                        </div>
                        <div className="flex flex-wrap items-center gap-2 shrink-0">
                          {f.human_review_required && (
                            <button
                              type="button"
                              onClick={() => quickApprove(iss.issue_id)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-700 cursor-pointer"
                            >
                              <CheckCircle2 className="w-3.5 h-3.5" /> Quick Approve
                            </button>
                          )}
                          <Link
                            href={`/issues/${iss.issue_id}`}
                            className="px-2.5 py-1 rounded-lg bg-slate-900 text-white text-xs font-medium hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
                          >
                            Edit / Override
                          </Link>
                        </div>
                      </div>
                      <div className="text-xs text-slate-800 dark:text-slate-200 break-words">{f.next_action}</div>
                      {f.human_review_reasons.length > 0 && (
                        <div className="text-xs text-amber-800 bg-amber-50 dark:text-amber-200 dark:bg-amber-950/40 dark:border-amber-800 rounded px-2.5 py-1.5 border border-amber-200 break-words">
                          {f.human_review_reasons.join(" · ")}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-xs overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/70">
              <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">Recorded Human Corrections &amp; Approvals ({reviews.length})</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 uppercase">
                    <th className="py-2.5 px-4">ID</th>
                    <th className="py-2.5 px-4">Issue</th>
                    <th className="py-2.5 px-4">Action</th>
                    <th className="py-2.5 px-4">Reviewer</th>
                    <th className="py-2.5 px-4">Reason</th>
                    <th className="py-2.5 px-4">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {reviews.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-slate-500 dark:text-slate-400">
                        No human reviews logged for the current run yet.
                      </td>
                    </tr>
                  ) : (
                    reviews.map((r) => (
                      <tr key={r.review_id}>
                        <td className="py-2.5 px-4 font-mono whitespace-nowrap">#{r.review_id}</td>
                        <td className="py-2.5 px-4 font-semibold whitespace-nowrap">
                          <Link href={`/issues/${r.issue_id}`} className="hover:underline">
                            {r.issue_id}
                          </Link>
                        </td>
                        <td className="py-2.5 px-4 font-mono whitespace-nowrap">{r.action}</td>
                        <td className="py-2.5 px-4 whitespace-nowrap">{r.reviewer}</td>
                        <td className="py-2.5 px-4">{r.reason || "-"}</td>
                        <td className="py-2.5 px-4 font-mono text-slate-500 dark:text-slate-400 whitespace-nowrap">{formatShortTime(r.created_at)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
