"use client";

import React, { useCallback, useEffect, useState } from "react";
import { RotateCcw, Upload } from "lucide-react";
import { useDataset } from "@/components/DatasetContext";
import { ErrorBanner, LoadingPanel, SeverityBadge, StatCard, SuccessBanner, formatShortTime } from "@/components/ui";
import { getQualityReport, resetDataset, uploadCsv } from "@/lib/api";
import type { DQIssue } from "@/lib/types";

export default function DataQualityPage() {
  const { dataset } = useDataset();
  const [data, setData] = useState<{
    dataset: string;
    updated_at: string;
    files: Record<string, { rows: number; bytes: number }>;
    summary: { total: number; error: number; warning: number; info: number; human_review_required: number };
    issues: DQIssue[];
  } | null>(null);
  const [severityFilter, setSeverityFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getQualityReport(dataset);
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data quality report");
    } finally {
      setLoading(false);
    }
  }, [dataset]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleUpload(kind: "bookings" | "inbox", file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const res = await uploadCsv(kind, dataset, file);
      setMsg(`Imported ${res.filename}: ${res.bookings_count} bookings, ${res.messages_count} messages, ${res.dq_issues_count} DQ findings.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "CSV import failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleReset() {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      await resetDataset(dataset);
      setMsg(`Reset '${dataset}' dataset back to the original supplied CSV files.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  }

  const filtered = data
    ? data.issues.filter((i) => !severityFilter || i.severity === severityFilter)
    : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">CSV Ingestion & Data Quality Report</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Preserves every original cell untouched while flagging UTF-8 BOM, missing values, duplicates, and reconciliation gaps.
          </p>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={handleReset}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-slate-300 bg-white text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800 disabled:opacity-50 cursor-pointer"
        >
          <RotateCcw className="w-4 h-4" /> Reset to Source CSVs
        </button>
      </div>

      {msg && <SuccessBanner message={msg} />}
      {error && <ErrorBanner message={error} />}

      {/* Upload cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <label className="rounded-xl border border-dashed border-slate-300 bg-white hover:border-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-slate-500 p-4 cursor-pointer flex flex-wrap sm:flex-nowrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-base font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <Upload className="w-4 h-4 text-slate-600 dark:text-slate-400 shrink-0" /> Upload booking_register.csv
            </div>
            <div className="text-sm text-slate-500 dark:text-slate-400 mt-0.5 break-words">
              Current rows: {data?.files["booking_register.csv"]?.rows ?? "-"} · Max 256 KB · UTF-8 / BOM supported
            </div>
          </div>
          <input
            type="file"
            accept=".csv"
            disabled={busy}
            className="hidden"
            onChange={(e) => handleUpload("bookings", e.target.files?.[0])}
          />
          <span className="px-3.5 py-2 rounded-lg bg-slate-900 text-white dark:bg-sky-500 dark:text-slate-950 text-sm font-medium shrink-0">Choose CSV</span>
        </label>

        <label className="rounded-xl border border-dashed border-slate-300 bg-white hover:border-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-slate-500 p-4 cursor-pointer flex flex-wrap sm:flex-nowrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-base font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <Upload className="w-4 h-4 text-slate-600 dark:text-slate-400 shrink-0" /> Upload shift_inbox.csv
            </div>
            <div className="text-sm text-slate-500 dark:text-slate-400 mt-0.5 break-words">
              Current rows: {data?.files["shift_inbox.csv"]?.rows ?? "-"} · Max 256 KB · Re-runs deterministic triage
            </div>
          </div>
          <input
            type="file"
            accept=".csv"
            disabled={busy}
            className="hidden"
            onChange={(e) => handleUpload("inbox", e.target.files?.[0])}
          />
          <span className="px-3.5 py-2 rounded-lg bg-slate-900 text-white dark:bg-sky-500 dark:text-slate-950 text-sm font-medium shrink-0">Choose CSV</span>
        </label>
      </div>

      {loading || !data ? (
        <LoadingPanel />
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <StatCard label="Total Findings" value={data.summary.total} />
            <StatCard label="Errors" value={data.summary.error} tone={data.summary.error > 0 ? "danger" : "default"} />
            <StatCard label="Warnings" value={data.summary.warning} tone={data.summary.warning > 0 ? "warning" : "default"} />
            <StatCard label="Info Notes" value={data.summary.info} />
            <StatCard label="Needs Review" value={data.summary.human_review_required} tone="warning" />
          </div>

          <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-xs overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/70 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">Data-Quality Findings ({filtered.length})</h2>
                {data.updated_at && (
                  <div className="text-xs text-slate-500 dark:text-slate-400 font-mono mt-0.5" title={data.updated_at}>
                    Last updated: {formatShortTime(data.updated_at)}
                  </div>
                )}
              </div>
              <select
                aria-label="Filter severity"
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                className="rounded-lg border border-slate-300 px-3.5 py-2 text-sm bg-white text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              >
                <option value="">All Severities</option>
                <option value="error">Error</option>
                <option value="warning">Warning</option>
                <option value="info">Info</option>
              </select>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[780px] text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 uppercase">
                    <th className="py-2.5 px-4">File</th>
                    <th className="py-2.5 px-4">Record / Field</th>
                    <th className="py-2.5 px-4">Type</th>
                    <th className="py-2.5 px-4">Severity</th>
                    <th className="py-2.5 px-4">Original &rarr; Normalised</th>
                    <th className="py-2.5 px-4">Problem & Action</th>
                    <th className="py-2.5 px-4">Review</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {filtered.map((d, idx) => (
                    <tr key={idx} className="align-top">
                      <td className="py-2.5 px-4 font-mono text-slate-600 dark:text-slate-400">{d.source_file}</td>
                      <td className="py-2.5 px-4">
                        <div className="font-mono font-semibold text-slate-900 dark:text-slate-100">{d.record_id}</div>
                        <div className="font-mono text-slate-500 dark:text-slate-400">{d.field}</div>
                      </td>
                      <td className="py-2.5 px-4 font-mono">{d.issue_type}</td>
                      <td className="py-2.5 px-4">
                        <SeverityBadge severity={d.severity} />
                      </td>
                      <td className="py-2.5 px-4 font-mono max-w-[180px] break-words">
                        <div>{d.original_value ?? <span className="text-slate-400 dark:text-slate-500">null</span>}</div>
                        {d.normalised_value && <div className="text-emerald-700 dark:text-emerald-400">&rarr; {d.normalised_value}</div>}
                      </td>
                      <td className="py-2.5 px-4 max-w-md">
                        <div className="text-slate-900 dark:text-slate-100">{d.problem}</div>
                        <div className="text-slate-600 dark:text-slate-300 mt-0.5">Action: {d.recommended_action}</div>
                      </td>
                      <td className="py-2.5 px-4">{d.human_review_required ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
