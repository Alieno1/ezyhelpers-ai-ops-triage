"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowUpDown, Filter, Search } from "lucide-react";
import { useDataset } from "@/components/DatasetContext";
import {
  ChannelBadge,
  DepartmentBadge,
  ErrorBanner,
  LoadingPanel,
  SourceBadge,
  StatusBadge,
  UrgencyBadge,
  formatVariantLabel,
} from "@/components/ui";
import { getIssues } from "@/lib/api";
import type { IssueResult } from "@/lib/types";

export default function QueuePage() {
  const { dataset } = useDataset();
  const [issues, setIssues] = useState<IssueResult[]>([]);
  const [meta, setMeta] = useState<{ run_id: string; mode: string; variant: string; total: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [urgency, setUrgency] = useState("");
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState("");
  const [reviewOnly, setReviewOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<"priority_rank" | "urgency" | "issue_id" | "department">("priority_rank");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getIssues(dataset, {
        urgency: urgency || undefined,
        department: department || undefined,
        status: status || undefined,
        human_review_required: reviewOnly ? "true" : undefined,
        search: search.trim() || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
      });
      setIssues(res.issues);
      setMeta({ run_id: res.run_id, mode: res.mode, variant: res.variant, total: res.total });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load priority queue");
    } finally {
      setLoading(false);
    }
  }, [dataset, urgency, department, status, reviewOnly, search, sortBy, sortDir]);

  useEffect(() => {
    load();
  }, [load]);

  const activeFilterCount = useMemo(
    () => [urgency, department, status, reviewOnly ? "1" : "", search.trim()].filter(Boolean).length,
    [urgency, department, status, reviewOnly, search]
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">Actionable Priority Queue</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 break-words">
            One row per distinct issue, ranked by deterministic care-gap rules and customer deadlines.
            {meta && (
              <span
                title={`Run ID: ${meta.run_id}`}
                className="ml-0 sm:ml-2 block sm:inline text-xs text-slate-400 dark:text-slate-500 mt-0.5 sm:mt-0"
              >
                · Mode: <strong className="font-medium text-slate-600 dark:text-slate-300">{formatVariantLabel(meta.variant)}</strong>
              </span>
            )}
          </p>
        </div>
        <Link
          href="/exports"
          className="px-3.5 py-2 rounded-lg border border-slate-300 bg-white text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800 shrink-0"
        >
          Export CSV / XLSX
        </Link>
      </div>

      {/* Filters */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4 shadow-xs space-y-3">
        <div className="flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
          <div className="flex items-center gap-1.5 font-semibold text-slate-700 dark:text-slate-200">
            <Filter className="w-4 h-4" /> Filter &amp; Sort Queue
          </div>
          {activeFilterCount > 0 && (
            <button
              type="button"
              onClick={() => {
                setUrgency("");
                setDepartment("");
                setStatus("");
                setReviewOnly(false);
                setSearch("");
              }}
              className="text-slate-600 dark:text-slate-300 underline hover:text-slate-900 dark:hover:text-white cursor-pointer"
            >
              Clear {activeFilterCount} filter(s)
            </button>
          )}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-2.5">
          <div className="lg:col-span-2 relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search ID, booking, M01, text..."
              className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 bg-white text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-sky-500"
            />
          </div>
          <select
            aria-label="Filter urgency"
            value={urgency}
            onChange={(e) => setUrgency(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm bg-white text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          >
            <option value="">All Urgencies</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="none">None (Resolved)</option>
          </select>
          <select
            aria-label="Filter department"
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm bg-white text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          >
            <option value="">All Departments</option>
            <option value="Duty Ops">Duty Ops</option>
            <option value="Billing">Billing</option>
            <option value="Sales">Sales</option>
            <option value="Sourcing">Sourcing</option>
          </select>
          <select
            aria-label="Filter status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm bg-white text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          >
            <option value="">All Statuses</option>
            <option value="open">Open</option>
            <option value="awaiting_info">Awaiting Info</option>
            <option value="resolved">Resolved</option>
          </select>
          <div className="flex items-center gap-1.5">
            <select
              aria-label="Sort by"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
              className="flex-1 min-w-0 rounded-lg border border-slate-300 px-2.5 py-2 text-sm bg-white text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              <option value="priority_rank">Sort: Rank</option>
              <option value="urgency">Sort: Urgency</option>
              <option value="department">Sort: Dept</option>
              <option value="issue_id">Sort: Issue ID</option>
            </select>
            <button
              type="button"
              onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
              title={`Toggle sort (${sortDir})`}
              className="p-2.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700 cursor-pointer shrink-0"
            >
              <ArrowUpDown className="w-4 h-4 text-slate-600 dark:text-slate-300" />
            </button>
          </div>
        </div>
        <label className="inline-flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={reviewOnly}
            onChange={(e) => setReviewOnly(e.target.checked)}
            className="rounded border-slate-300 dark:border-slate-600"
          />
          Show only issues flagged for Human Review
        </label>
      </div>

      {error && <ErrorBanner message={error} />}
      {loading ? (
        <LoadingPanel />
      ) : (
        <>
          {/* Mobile / Tablet Card View */}
          <div className="md:hidden space-y-3">
            {issues.length === 0 ? (
              <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-6 text-center text-sm text-slate-500 dark:text-slate-400">
                No issues match the current filters.
              </div>
            ) : (
              issues.map((iss) => {
                const f = iss.final;
                return (
                  <div
                    key={iss.issue_id}
                    className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4 shadow-xs space-y-2.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-slate-900 dark:text-slate-100 tabular-nums">#{f.priority_rank ?? "-"}</span>
                          <Link href={`/issues/${iss.issue_id}`} className="font-bold text-slate-900 dark:text-slate-100 hover:underline">
                            {iss.issue_id}
                          </Link>
                          <span className="font-mono text-xs text-slate-500 dark:text-slate-400">
                            {iss.group.booking_id || "Unlinked"}
                            {iss.booking?.locality ? ` · ${iss.booking.locality}` : ""}
                          </span>
                        </div>
                      </div>
                      <Link
                        href={`/issues/${iss.issue_id}`}
                        className="inline-flex items-center px-3 py-1.5 rounded-lg bg-slate-900 text-white text-sm font-medium hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400 shrink-0"
                      >
                        Review
                      </Link>
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5">
                      <UrgencyBadge urgency={f.urgency} />
                      <DepartmentBadge department={f.responsible_department} />
                      <ChannelBadge channel={f.contact_channel} />
                      <StatusBadge status={f.status} />
                      <SourceBadge source={f.source} />
                    </div>

                    {f.deadline && (
                      <div className="text-xs text-rose-700 dark:text-rose-400 font-medium">
                        Deadline: {f.deadline}
                      </div>
                    )}

                    <div className="text-sm text-slate-800 dark:text-slate-200 leading-relaxed">{f.next_action}</div>

                    {f.missing_information.length > 0 && (
                      <div className="text-xs text-amber-800 dark:text-amber-300">
                        Missing: {f.missing_information[0]}
                        {f.missing_information.length > 1 ? ` (+${f.missing_information.length - 1})` : ""}
                      </div>
                    )}

                    <div className="flex flex-wrap items-center justify-between gap-2 pt-1.5 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
                      <div className="flex flex-wrap items-center gap-1">
                        {iss.group.source_message_ids.map((mid) => (
                          <span
                            key={mid}
                            className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 dark:bg-slate-800 dark:border-slate-700 font-mono text-slate-700 dark:text-slate-200"
                          >
                            {mid}
                          </span>
                        ))}
                        <span>· Threads: {iss.group.thread_ids.join(", ") || "-"}</span>
                      </div>
                      {f.human_review_required && (
                        <span className="font-medium text-amber-700 dark:text-amber-300">Human Review Flagged</span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Desktop Table View */}
          <div className="hidden md:block rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-xs overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-600 dark:bg-slate-800/70 dark:border-slate-800 dark:text-slate-400 uppercase tracking-wider">
                    <th className="py-3 px-3">#</th>
                    <th className="py-3 px-3">Issue / Booking</th>
                    <th className="py-3 px-3">Urgency</th>
                    <th className="py-3 px-3">Department</th>
                    <th className="py-3 px-3">Next Action &amp; Channel</th>
                    <th className="py-3 px-3">Source IDs</th>
                    <th className="py-3 px-3">Status &amp; Source</th>
                    <th className="py-3 px-3 text-right">Inspect</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {issues.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-8 text-center text-slate-500 dark:text-slate-400">
                        No issues match the current filters.
                      </td>
                    </tr>
                  ) : (
                    issues.map((iss) => {
                      const f = iss.final;
                      return (
                        <tr key={iss.issue_id} className="hover:bg-slate-50/70 dark:hover:bg-slate-800/50 align-top">
                          <td className="py-3.5 px-3 font-bold text-slate-900 dark:text-slate-100 tabular-nums">
                            {f.priority_rank ?? "-"}
                          </td>
                          <td className="py-3.5 px-3">
                            <Link
                              href={`/issues/${iss.issue_id}`}
                              className="font-semibold text-slate-900 dark:text-slate-100 hover:underline whitespace-nowrap"
                            >
                              {iss.issue_id}
                            </Link>
                            <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 font-mono">
                              {iss.group.booking_id || "Unlinked"}
                              {iss.booking?.locality ? ` · ${iss.booking.locality}` : ""}
                            </div>
                          </td>
                          <td className="py-3.5 px-3 whitespace-nowrap">
                            <UrgencyBadge urgency={f.urgency} />
                            {f.deadline && (
                              <div className="text-xs text-rose-700 dark:text-rose-400 font-medium mt-1">
                                Deadline: {f.deadline}
                              </div>
                            )}
                          </td>
                          <td className="py-3.5 px-3 whitespace-nowrap">
                            <DepartmentBadge department={f.responsible_department} />
                            {f.supporting_departments.length > 0 && (
                              <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                + {f.supporting_departments.join(", ")}
                              </div>
                            )}
                          </td>
                          <td className="py-3.5 px-3 max-w-sm min-w-[260px]">
                            <div className="flex flex-wrap items-center gap-1.5 mb-1">
                              <ChannelBadge channel={f.contact_channel} />
                              <code className="text-xs text-slate-500 dark:text-slate-400 font-mono break-all">{f.action_code}</code>
                            </div>
                            <div className="text-slate-800 dark:text-slate-200 text-sm leading-relaxed">{f.next_action}</div>
                            {f.missing_information.length > 0 && (
                              <div className="mt-1 text-xs text-amber-800 dark:text-amber-300">
                                Missing: {f.missing_information[0]}
                                {f.missing_information.length > 1 ? ` (+${f.missing_information.length - 1})` : ""}
                              </div>
                            )}
                          </td>
                          <td className="py-3.5 px-3 whitespace-nowrap">
                            <div className="flex flex-wrap gap-1">
                              {iss.group.source_message_ids.map((mid) => (
                                <span
                                  key={mid}
                                  className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 dark:bg-slate-800 dark:border-slate-700 font-mono text-xs text-slate-700 dark:text-slate-200"
                                >
                                  {mid}
                                </span>
                              ))}
                            </div>
                            <div className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                              Threads: {iss.group.thread_ids.join(", ") || "-"}
                            </div>
                          </td>
                          <td className="py-3.5 px-3 whitespace-nowrap space-y-1">
                            <div>
                              <StatusBadge status={f.status} />
                            </div>
                            <div>
                              <SourceBadge source={f.source} />
                            </div>
                            {f.human_review_required && (
                              <div className="text-xs font-medium text-amber-700 dark:text-amber-300">Human Review Flagged</div>
                            )}
                          </td>
                          <td className="py-3.5 px-3 text-right whitespace-nowrap">
                            <Link
                              href={`/issues/${iss.issue_id}`}
                              className="inline-flex items-center px-3 py-1.5 rounded-lg bg-slate-900 text-white text-sm font-medium hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
                            >
                              Review
                            </Link>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
