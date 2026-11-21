"use client";

import React, { useEffect, useState } from "react";
import { Activity, BookOpen, Download, FileSpreadsheet, FileText } from "lucide-react";
import { useDataset } from "@/components/DatasetContext";
import { ErrorBanner, LoadingPanel } from "@/components/ui";
import { exportUrl, getModelStatus } from "@/lib/api";
import type { ModelStatusResponse } from "@/lib/types";

export default function ExportsAndModelPage() {
  const { dataset } = useDataset();
  const [status, setStatus] = useState<ModelStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getModelStatus()
      .then(setStatus)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load model status"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">Operational Exports, OpenRouter Status & Handover</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Download spreadsheets and issue reports generated directly from backend state, inspect LLM telemetry, and review the coordinator SOP.
        </p>
      </div>

      {/* Exports Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs space-y-3">
          <div className="flex items-center gap-2 font-bold text-slate-900 dark:text-slate-100 text-sm">
            <FileSpreadsheet className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            Priority Queue ({dataset})
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Ranked issues with source IDs, departments, next actions, missing info, drafts, and human corrections.
          </p>
          <div className="flex gap-2">
            <a
              href={exportUrl("queue", "csv", dataset)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 text-white text-xs font-medium hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
            >
              <Download className="w-3.5 h-3.5" /> CSV
            </a>
            <a
              href={exportUrl("queue", "xlsx", dataset)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              <Download className="w-3.5 h-3.5" /> XLSX Workbook
            </a>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs space-y-3">
          <div className="flex items-center gap-2 font-bold text-slate-900 dark:text-slate-100 text-sm">
            <FileSpreadsheet className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            Evaluation Results
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Rules v1 vs Rules v2 before-and-after comparison, failure logs, and harder synthetic benchmark.
          </p>
          <div className="flex gap-2">
            <a
              href={exportUrl("evaluation", "csv", dataset)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 text-white text-xs font-medium hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
            >
              <Download className="w-3.5 h-3.5" /> CSV
            </a>
            <a
              href={exportUrl("evaluation", "xlsx", dataset)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              <Download className="w-3.5 h-3.5" /> XLSX Workbook
            </a>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs space-y-3">
          <div className="flex items-center gap-2 font-bold text-slate-900 dark:text-slate-100 text-sm">
            <FileText className="w-4 h-4 text-sky-600 dark:text-sky-400" />
            Issue Evidence Report
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Full shift triage narrative with message timelines, missing facts, and draft replies.
          </p>
          <div className="flex gap-2">
            <a
              href={exportUrl("issues-report", "md", dataset)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 text-white text-xs font-medium hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
            >
              <Download className="w-3.5 h-3.5" /> Markdown
            </a>
            <a
              href={exportUrl("issues-report", "json", dataset)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              <Download className="w-3.5 h-3.5" /> JSON
            </a>
          </div>
        </div>
      </div>

      {/* OpenRouter Status */}
      {error && <ErrorBanner message={error} />}
      {loading || !status ? (
        <LoadingPanel />
      ) : (
        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <Activity className="w-4 h-4 text-slate-700 dark:text-slate-300" /> OpenRouter Provider Configuration
            </h2>
            <span
              className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                status.api_key_configured
                  ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/70 dark:text-emerald-300 dark:border-emerald-800"
                  : "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/70 dark:text-amber-300 dark:border-amber-800"
              }`}
            >
              {status.api_key_configured ? "API Key Configured (Backend Only)" : "API Key Not Set — Rules Fallback Active"}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs bg-slate-50 rounded-lg border border-slate-200 dark:bg-slate-800/70 dark:border-slate-700 p-3.5">
            <div>
              <div className="text-slate-500 dark:text-slate-400">Provider / Model</div>
              <div className="font-mono font-semibold text-slate-900 dark:text-slate-100 mt-0.5">{status.model}</div>
            </div>
            <div>
              <div className="text-slate-500 dark:text-slate-400">Base URL</div>
              <div className="font-mono text-slate-800 dark:text-slate-200 mt-0.5 truncate">{status.base_url}</div>
            </div>
            <div>
              <div className="text-slate-500 dark:text-slate-400">Timeout / Retries</div>
              <div className="font-mono text-slate-800 dark:text-slate-200 mt-0.5">
                {status.timeout_seconds}s / {status.max_retries} retries
              </div>
            </div>
            <div>
              <div className="text-slate-500 dark:text-slate-400">Pricing Assumption (1M tok)</div>
              <div className="font-mono text-slate-800 dark:text-slate-200 mt-0.5">
                {status.pricing_assumptions_usd_per_1m.input !== null
                  ? `$${status.pricing_assumptions_usd_per_1m.input} in / $${status.pricing_assumptions_usd_per_1m.output} out`
                  : "Unset"}
              </div>
            </div>
          </div>

          <div>
            <div className="text-xs font-bold text-slate-700 dark:text-slate-200 mb-2">
              Recorded LLM Execution Log ({status.recent_calls.length} recent calls)
            </div>
            <div className="overflow-x-auto border border-slate-200 dark:border-slate-800 rounded-lg">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 dark:bg-slate-800/70 dark:border-slate-800 text-slate-500 dark:text-slate-400 uppercase">
                    <th className="py-2 px-3">Call ID</th>
                    <th className="py-2 px-3">Issue</th>
                    <th className="py-2 px-3">Status</th>
                    <th className="py-2 px-3">Model</th>
                    <th className="py-2 px-3">Tokens</th>
                    <th className="py-2 px-3">Cost (USD)</th>
                    <th className="py-2 px-3">Duration</th>
                    <th className="py-2 px-3">Error / Note</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {status.recent_calls.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-5 text-center text-slate-500 dark:text-slate-400">
                        No OpenRouter execution attempts logged yet. Click &ldquo;Run OpenRouter AI&rdquo; on Overview to test live execution or verify graceful fallback.
                      </td>
                    </tr>
                  ) : (
                    status.recent_calls.map((c) => (
                      <tr key={c.call_id}>
                        <td className="py-2 px-3 font-mono">{c.call_id}</td>
                        <td className="py-2 px-3 font-mono">{c.issue_id || "-"}</td>
                        <td className="py-2 px-3">
                          <span className={c.ok ? "text-emerald-700 dark:text-emerald-400 font-semibold" : "text-red-700 dark:text-red-400 font-semibold"}>
                            {c.ok ? "OK" : "FAILED"}
                          </span>
                        </td>
                        <td className="py-2 px-3 font-mono">{c.model_used || c.model_requested}</td>
                        <td className="py-2 px-3 font-mono">{c.total_tokens ?? "-"}</td>
                        <td className="py-2 px-3 font-mono">{c.cost_usd !== null ? `$${c.cost_usd.toFixed(6)}` : "-"}</td>
                        <td className="py-2 px-3 font-mono">{c.duration_ms}ms</td>
                        <td className="py-2 px-3 text-slate-600 dark:text-slate-300">{c.error_type ? `${c.error_type}: ${c.error_message}` : "-"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Coordinator Handover Card */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs space-y-2.5">
        <div className="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-slate-100">
          <BookOpen className="w-4 h-4 text-slate-700 dark:text-slate-300" />
          Coordinator Quick-Start SOP (124 words)
        </div>
        <div className="text-sm text-slate-700 dark:text-slate-200 leading-relaxed bg-slate-50 rounded-lg border border-slate-200 dark:bg-slate-800/70 dark:border-slate-700 p-4">
          Open <strong>Priority Queue</strong> at 09:00 and take rank <strong>#1</strong> first — uncovered elder or child care gaps outrank everything else. Before dialling, open the issue and check two panels: the <strong>Message Timeline</strong> (for preferences like &ldquo;WhatsApp, don&rsquo;t call&rdquo;) and the <strong>Booking Register</strong> (sole authority on arrivals, substitutes, refund approvals, and payout dates). Never promise an ETA, substitute, refund approval, or quote missing from the register.
          <br /><br />
          If priority, owner, or next action looks wrong, submit a decision in <strong>Coordinator Review</strong> (<code>change_priority</code>, <code>change_department</code>, <code>correct_action</code>, or <code>edit_draft</code>) with a brief reason so the queue re-ranks immediately. Drafts are never auto-sent — copy an approved draft manually or hold contact. Escalate uncertain booking identities via <strong>Request More Information</strong> and close verified arrivals via <strong>Resolve</strong>.
        </div>
      </div>
    </div>
  );
}
