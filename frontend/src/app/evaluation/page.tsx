"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CheckCircle2, FlaskConical, RefreshCw, XCircle } from "lucide-react";
import { useDataset } from "@/components/DatasetContext";
import { useTheme } from "@/components/ThemeContext";
import { ErrorBanner, LoadingPanel } from "@/components/ui";
import { getLatestEvaluation, getModelStatus, runEvaluation } from "@/lib/api";
import type { EvaluationReport } from "@/lib/types";

export default function EvaluationPage() {
  const { dataset } = useDataset();
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    getModelStatus()
      .then((m) => setKeyConfigured(m.api_key_configured))
      .catch(() => { });
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getLatestEvaluation(dataset);
      setReport(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load evaluation");
    } finally {
      setLoading(false);
    }
  }, [dataset]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRun(includeAi: boolean) {
    setRunning(true);
    setError(null);
    try {
      const res = await runEvaluation(dataset, includeAi);
      setReport(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Evaluation failed");
    } finally {
      setRunning(false);
    }
  }

  if (loading) return <LoadingPanel />;
  if (error || !report) return <ErrorBanner message={error || "No evaluation found"} />;

  const evalMethods = report.methods.filter((m) => m.status === "evaluated");
  const chartData = evalMethods.map((m) => ({
    name: m.variant,
    "Correct Actions": m.correct_next_actions,
    "Dept Correct": m.department_correct,
    "Missing Info OK": m.missing_info_complete,
    "Unsupported Promises": m.unsupported_promises,
  }));

  const gridColor = isDark ? "#334155" : "#e2e8f0";
  const axisTick = { fontSize: 11, fill: isDark ? "#94a3b8" : "#475569" };
  const tooltipStyle = isDark
    ? { backgroundColor: "#0f172a", borderColor: "#334155", color: "#f1f5f9", fontSize: 12 }
    : { backgroundColor: "#ffffff", borderColor: "#e2e8f0", color: "#0f172a", fontSize: 12 };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">Rules vs AI Evaluation</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 break-words">
            Scored against frozen <code className="font-mono">{report.expected_file}</code> ({report.total_cases} cases).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={running}
            onClick={() => handleRun(false)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 text-white text-xs font-medium hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400 disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${running ? "animate-spin" : ""}`} />
            Rerun Rules Comparison
          </button>
          <button
            type="button"
            disabled={running || !keyConfigured}
            title={keyConfigured ? "Evaluate live OpenRouter model" : "Set OPENROUTER_API_KEY in backend/.env to run live AI evaluation"}
            onClick={() => handleRun(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800 disabled:opacity-50 cursor-pointer"
          >
            <FlaskConical className="w-3.5 h-3.5" />
            {keyConfigured ? "Evaluate Live AI" : "Live AI (Key Pending)"}
          </button>
        </div>
      </div>

      {/* Method Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {report.methods.map((m) => (
          <div key={m.variant} className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4 shadow-xs space-y-2.5 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-xs font-mono text-slate-500 dark:text-slate-400 break-words">{m.variant}</div>
                <div className="text-sm font-bold text-slate-900 dark:text-slate-100 break-words">{m.label}</div>
              </div>
              <span
                className={`px-2 py-0.5 rounded text-[11px] font-semibold uppercase shrink-0 ${m.status === "evaluated"
                  ? "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/70 dark:text-emerald-300 dark:border-emerald-800"
                  : "bg-amber-50 text-amber-800 border border-amber-200 dark:bg-amber-950/70 dark:text-amber-300 dark:border-amber-800"
                  }`}
              >
                {m.status === "pending_credentials" ? "Pending Key" : m.status === "not_run" ? "Ready to Run" : m.status}
              </span>
            </div>

            {m.status === "evaluated" ? (
              <div className="grid grid-cols-2 gap-2 pt-1 text-xs">
                <div className="bg-slate-50 rounded p-2 border border-slate-100 dark:bg-slate-800/70 dark:border-slate-700">
                  <div className="text-slate-500 dark:text-slate-400">Next Actions</div>
                  <div className="text-lg font-bold text-slate-900 dark:text-slate-100 tabular-nums">
                    {m.correct_next_actions}/{m.total_cases}
                  </div>
                </div>
                <div className="bg-slate-50 rounded p-2 border border-slate-100 dark:bg-slate-800/70 dark:border-slate-700">
                  <div className="text-slate-500 dark:text-slate-400">Unsupported Promises</div>
                  <div className={`text-lg font-bold tabular-nums ${m.unsupported_promises === 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}`}>
                    {m.unsupported_promises}
                  </div>
                </div>
                <div>Dept Routing: <strong>{m.department_correct}/{m.total_cases}</strong></div>
                <div>Grouping: <strong>{m.grouping_correct}/{m.total_cases}</strong></div>
                <div>Missing Info: <strong>{m.missing_info_complete}/{m.total_cases}</strong></div>
                <div>
                  1st Callback:{" "}
                  <strong>{m.first_callback_correct === null ? "-" : m.first_callback_correct ? "Match" : "Mismatch"}</strong>
                </div>
                {m.mode === "ai" && (
                  <div className="col-span-2 pt-1.5 border-t border-slate-100 dark:border-slate-800 text-[11px] text-slate-500 dark:text-slate-400 flex flex-wrap gap-x-2 gap-y-0.5">
                    <span>Tokens: <strong>{m.token_usage_total ?? "-"}</strong></span>
                    <span>Latency: <strong>{m.duration_ms_total ? `${(m.duration_ms_total / 1000).toFixed(1)}s` : "-"}</strong></span>
                    <span>Cost: <strong>{m.actual_cost_usd !== null ? `$${m.actual_cost_usd.toFixed(6)}` : "n/a"}</strong></span>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-amber-900 bg-amber-50 border border-amber-200 dark:text-amber-200 dark:bg-amber-950/40 dark:border-amber-800 rounded p-2.5 leading-relaxed">
                {m.note}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Before / After Improvement & Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs space-y-3 min-w-0">
          <div className="text-xs font-semibold text-indigo-700 dark:text-sky-400 uppercase tracking-wider">
            Single Targeted Improvement &amp; Rerun
          </div>
          <div className="text-lg font-bold text-slate-900 dark:text-slate-100">
            {report.improvement_summary.before_variant}: {report.improvement_summary.before_correct}/{report.improvement_summary.total}{" "}
            &rarr; {report.improvement_summary.after_variant}: {report.improvement_summary.after_correct}/{report.improvement_summary.total}{" "}
            <span className="text-emerald-700 dark:text-emerald-400">(+{report.improvement_summary.delta_correct})</span>
          </div>
          <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">{report.improvement_summary.change_description}</p>
          {report.disagreements_and_failures.length > 0 && (
            <div className="space-y-1.5 pt-2">
              <div className="text-xs font-semibold text-slate-700 dark:text-slate-200">Recorded Failures / Disagreements:</div>
              {report.disagreements_and_failures.map((d, idx) => (
                <div key={idx} className="text-xs rounded bg-rose-50 border border-rose-200 dark:bg-rose-950/40 dark:border-rose-900 p-2.5 text-rose-900 dark:text-rose-200 break-words">
                  <strong>[{d.variant}] {d.source_message_ids.join(", ")} ({d.booking_id || "Unlinked"}):</strong>{" "}
                  Expected <code className="break-words">{d.expected}</code>, got <code className="break-words">{d.actual}</code>.
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs min-w-0">
          <div className="text-sm font-bold text-slate-900 dark:text-slate-100 mb-3">Before vs After Metric Comparison</div>
          <div className="h-56 w-full">
            {mounted && (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                  <XAxis dataKey="name" tick={axisTick} />
                  <YAxis allowDecimals={false} tick={axisTick} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend wrapperStyle={{ fontSize: 11, color: isDark ? "#cbd5e1" : "#334155" }} />
                  <Bar dataKey="Correct Actions" fill={isDark ? "#38bdf8" : "#0f172a"} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Missing Info OK" fill="#0284c7" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Unsupported Promises" fill="#dc2626" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* Case-by-case matrix */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-xs overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/70 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">Case-by-Case Expected vs Actual Matrix</h2>
          <span className="text-xs text-slate-500 dark:text-slate-400">Human Corrections Logged: {report.human_corrections_count}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/70 text-slate-600 dark:text-slate-400 uppercase">
                <th className="py-2.5 px-4">Source IDs</th>
                <th className="py-2.5 px-4">Booking</th>
                <th className="py-2.5 px-4">Expected Action</th>
                {evalMethods.map((m) => (
                  <th key={m.variant} className="py-2.5 px-4">
                    {m.variant}
                  </th>
                ))}
                <th className="py-2.5 px-4">Rationale</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {report.case_comparisons.map((row) => (
                <tr key={row.source_message_ids.join(",")} className="align-top">
                  <td className="py-2.5 px-4 font-mono font-semibold">{row.source_message_ids.join(", ")}</td>
                  <td className="py-2.5 px-4 font-mono">{row.booking_id || "-"}</td>
                  <td className="py-2.5 px-4">
                    <div className="font-mono font-semibold text-slate-900 dark:text-slate-100">{row.expected_action_code}</div>
                    <div className="text-slate-500 dark:text-slate-400">
                      {row.expected_department} · {row.expected_channel} · {row.expected_urgency}
                    </div>
                  </td>
                  {evalMethods.map((m) => {
                    const oc = row.outcomes[m.variant];
                    if (!oc) return <td key={m.variant} className="py-2.5 px-4">-</td>;
                    return (
                      <td key={m.variant} className="py-2.5 px-4">
                        <div className="flex items-center gap-1 font-mono">
                          {oc.action_correct ? (
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
                          ) : (
                            <XCircle className="w-3.5 h-3.5 text-red-600 dark:text-red-400 shrink-0" />
                          )}
                          <span>{oc.action_code}</span>
                        </div>
                        <div className="text-slate-500 dark:text-slate-400 mt-0.5">
                          {oc.contact_channel} · promises: {oc.unsupported_promises.length}
                        </div>
                      </td>
                    );
                  })}
                  <td className="py-2.5 px-4 text-slate-600 dark:text-slate-300 max-w-xs">{row.rationale}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Limitations */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4 text-xs text-slate-600 dark:text-slate-400 space-y-1">
        <div className="font-semibold text-slate-800 dark:text-slate-200">Evaluation Methodology Notes & Limitations</div>
        {report.limitations.map((l, i) => (
          <div key={i}>• {l}</div>
        ))}
      </div>
    </div>
  );
}
