"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowRight, Cpu, PhoneCall, Play, RefreshCw, ShieldAlert } from "lucide-react";
import { useDataset } from "@/components/DatasetContext";
import { useTheme } from "@/components/ThemeContext";
import {
  ChannelBadge,
  DepartmentBadge,
  ErrorBanner,
  LoadingPanel,
  StatCard,
  SuccessBanner,
  UrgencyBadge,
  formatRunStatus,
  formatShortTime,
  formatVariantLabel,
} from "@/components/ui";
import { getOverview, resetDataset, runAiPipeline, runRulesPipeline } from "@/lib/api";
import type { OverviewResponse } from "@/lib/types";

const URGENCY_COLORS: Record<string, string> = {
  critical: "#dc2626",
  high: "#d97706",
  medium: "#2563eb",
  low: "#64748b",
  none: "#10b981",
};

export default function OverviewPage() {
  const { dataset } = useDataset();
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getOverview(dataset);
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load overview");
    } finally {
      setLoading(false);
    }
  }, [dataset]);

  useEffect(() => {
    load();
  }, [load]);

  async function triggerRules(version: "v1" | "v2") {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await runRulesPipeline(dataset, version);
      setNotice(`Completed ${formatVariantLabel(res.variant)} triage run.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rules run failed");
    } finally {
      setBusy(false);
    }
  }

  async function triggerAi() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await runAiPipeline(dataset, "v1");
      if (res.status === "completed") {
        setNotice(`AI-Assisted run completed using OpenRouter model ${res.model}.`);
      } else {
        setNotice(
          `AI run finished (${formatRunStatus(res.status)}): ${res.notes.join(" ")}`
        );
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI run failed");
    } finally {
      setBusy(false);
    }
  }

  async function triggerReset() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await resetDataset(dataset);
      setNotice(`Dataset '${dataset}' reset and re-processed with rules_v2.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <LoadingPanel />;
  if (error && !data) return <ErrorBanner message={error} />;
  if (!data) return null;

  const m = data.metrics;
  const fc = data.first_callback;
  const gridColor = isDark ? "#334155" : "#e2e8f0";
  const axisTick = { fontSize: 12, fill: isDark ? "#cbd5e1" : "#475569" };
  const tooltipCursor = {
    fill: isDark ? "rgba(148, 163, 184, 0.14)" : "rgba(15, 23, 42, 0.06)",
  };
  const tooltipStyle = isDark
    ? {
        backgroundColor: "#0f172a",
        borderColor: "#475569",
        borderRadius: 8,
        boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.5)",
        color: "#f8fafc",
        fontSize: 13,
      }
    : {
        backgroundColor: "#ffffff",
        borderColor: "#cbd5e1",
        borderRadius: 8,
        boxShadow: "0 10px 25px -5px rgba(15, 23, 42, 0.12)",
        color: "#0f172a",
        fontSize: 13,
      };
  const tooltipLabelStyle = {
    color: isDark ? "#f8fafc" : "#0f172a",
    fontWeight: 600,
    marginBottom: 2,
  };
  const tooltipItemStyle = {
    color: isDark ? "#e2e8f0" : "#1e293b",
    fontWeight: 500,
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">Shift Triage Overview</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span title={`Run ID: ${data.run_id}`}>
              Mode: <strong className="text-slate-700 dark:text-slate-200">{formatVariantLabel(data.variant)}</strong>
            </span>
            <span>·</span>
            <span>
              Status: <strong className="text-slate-700 dark:text-slate-200">{formatRunStatus(data.run_status)}</strong>
            </span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => triggerRules("v1")}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-slate-300 bg-white text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800 disabled:opacity-50 cursor-pointer"
          >
            <Play className="w-4 h-4" /> Rules v1 (Baseline)
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => triggerRules("v2")}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400 disabled:opacity-50 cursor-pointer"
          >
            <Play className="w-4 h-4" /> Rules v2 (Improved)
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={triggerAi}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-violet-300 bg-violet-50 text-sm font-medium text-violet-800 hover:bg-violet-100 dark:border-violet-800 dark:bg-violet-950/60 dark:text-violet-300 dark:hover:bg-violet-900/60 disabled:opacity-50 cursor-pointer"
          >
            <Cpu className="w-4 h-4" />
            {data.openrouter_configured ? "Run OpenRouter AI" : "Run AI (Fallback Check)"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={triggerReset}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 bg-white text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${busy ? "animate-spin" : ""}`} /> Reset
          </button>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      {notice && <SuccessBanner message={notice} />}

      {/* First Callback Hero Card */}
      {fc ? (
        <section className="rounded-xl border-2 border-red-200 bg-white dark:border-red-900/80 dark:bg-slate-900 p-5 sm:p-6 shadow-xs space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start sm:items-center gap-3 min-w-0">
              <div className="w-10 h-10 shrink-0 rounded-lg bg-red-600 text-white flex items-center justify-center">
                <PhoneCall className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <div className="text-xs font-bold text-red-700 dark:text-red-400 uppercase tracking-wider">
                  Who Gets the First Callback (#1 in Queue)
                </div>
                <div className="text-lg sm:text-xl font-bold text-slate-900 dark:text-slate-100 break-words">
                  {fc.issue_id} · Booking {fc.booking_id || "Unlinked"} ({fc.source_message_ids.join(", ")})
                </div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <UrgencyBadge urgency={fc.urgency} />
              <DepartmentBadge department={fc.department} />
              <ChannelBadge channel={fc.channel} />
              <Link
                href={`/issues/${fc.issue_id}`}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-red-600 text-white text-sm font-semibold hover:bg-red-700 shrink-0"
              >
                Inspect Evidence <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1 text-sm">
            <div className="rounded-lg bg-red-50/50 border border-red-100 dark:bg-red-950/30 dark:border-red-900/60 p-3.5 space-y-1 min-w-0">
              <div className="font-semibold text-red-900 dark:text-red-300">Why #1 Before Any Other Case</div>
              <div className="text-slate-800 dark:text-slate-200 leading-relaxed break-words">{fc.why_first}</div>
            </div>
            <div className="rounded-lg bg-slate-50 border border-slate-200 dark:bg-slate-800/70 dark:border-slate-700 p-3.5 space-y-1 min-w-0">
              <div className="font-semibold text-slate-900 dark:text-slate-100">Immediate Coordinator Next Action</div>
              <div className="text-slate-800 dark:text-slate-200 leading-relaxed break-words">{fc.next_action}</div>
            </div>
          </div>
        </section>
      ) : (
        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-4 text-sm text-slate-600 dark:text-slate-400">
          No open phone callback pending in the current queue.
        </div>
      )}

      {/* 8 KPI Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
        <StatCard label="Total Messages" value={m.total_messages} sub={`Across ${m.total_bookings} bookings`} />
        <StatCard label="Distinct Issues" value={m.distinct_issues} sub="Grouped deterministically" />
        <StatCard
          label="Urgent Cases"
          value={m.urgent_cases}
          sub={`${m.critical_cases} critical · ${m.high_cases} high`}
          tone={m.critical_cases > 0 ? "danger" : "warning"}
        />
        <StatCard label="Open Issues" value={m.open_issues} sub={`${m.resolved_issues} resolved`} />
        <StatCard
          label="Human Review Cases"
          value={m.human_review_cases}
          sub={`${m.human_reviews_logged} review(s) logged`}
          tone={m.human_review_cases > 0 ? "warning" : "success"}
        />
        <StatCard
          label="Model Execution"
          value={data.mode === "ai" ? formatRunStatus(data.run_status) : "Rules-Only"}
          sub={data.openrouter_configured ? `OpenRouter (${data.model || "ready"})` : "OpenRouter key pending"}
        />
        <StatCard
          label="Data-Quality Findings"
          value={m.data_quality_issues}
          sub={`${m.dq_warnings_errors} warnings/errors`}
        />
        <StatCard label="Resolved Issues" value={m.resolved_issues} sub="Arrival confirmed by family" tone="success" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs min-w-0">
          <h2 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-3">Issues by Urgency Tier</h2>
          <div className="h-64 w-full">
            {mounted && (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.urgency_breakdown} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                  <XAxis dataKey="urgency" tick={axisTick} axisLine={{ stroke: gridColor }} tickLine={{ stroke: gridColor }} />
                  <YAxis allowDecimals={false} tick={axisTick} axisLine={{ stroke: gridColor }} tickLine={{ stroke: gridColor }} />
                  <Tooltip
                    cursor={tooltipCursor}
                    contentStyle={tooltipStyle}
                    labelStyle={tooltipLabelStyle}
                    itemStyle={tooltipItemStyle}
                  />
                  <Bar dataKey="count" name="Issues" fill={isDark ? "#60a5fa" : "#2563eb"} radius={[4, 4, 0, 0]} isAnimationActive={false}>
                    {data.urgency_breakdown.map((entry) => (
                      <Cell key={entry.urgency} fill={URGENCY_COLORS[entry.urgency] || "#475569"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs min-w-0">
          <h2 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-3">Owning Department Distribution</h2>
          <div className="h-64 w-full">
            {mounted && (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.department_breakdown} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                  <XAxis dataKey="department" tick={axisTick} axisLine={{ stroke: gridColor }} tickLine={{ stroke: gridColor }} />
                  <YAxis allowDecimals={false} tick={axisTick} axisLine={{ stroke: gridColor }} tickLine={{ stroke: gridColor }} />
                  <Tooltip
                    cursor={tooltipCursor}
                    contentStyle={tooltipStyle}
                    labelStyle={tooltipLabelStyle}
                    itemStyle={tooltipItemStyle}
                  />
                  <Bar dataKey="count" name="Issues" fill={isDark ? "#38bdf8" : "#0f172a"} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* Run Notes & Recent Runs */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-5 shadow-xs space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-slate-600 dark:text-slate-400 shrink-0" /> Execution Notes &amp; Recent Runs
          </h2>
          <Link href="/queue" className="text-sm font-medium text-slate-700 dark:text-sky-400 underline hover:text-slate-900 dark:hover:text-sky-300">
            Open Full Priority Queue &rarr;
          </Link>
        </div>
        <div className="text-sm text-slate-700 dark:text-slate-300 space-y-1 break-words">
          {data.notes.map((n, i) => (
            <div key={i}>• {n}</div>
          ))}
        </div>
        <div className="overflow-x-auto border border-slate-200 dark:border-slate-800 rounded-lg">
          <table className="w-full min-w-[640px] text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 dark:bg-slate-800/70 dark:border-slate-800 dark:text-slate-400 uppercase">
                <th className="py-2 px-3">Run ID</th>
                <th className="py-2 px-3">Mode</th>
                <th className="py-2 px-3">Variant</th>
                <th className="py-2 px-3">Model</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3">Finished At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {data.recent_runs.map((r) => (
                <tr key={r.run_id}>
                  <td className="py-2 px-3 font-mono whitespace-nowrap">{r.run_id}</td>
                  <td className="py-2 px-3 whitespace-nowrap">{r.mode}</td>
                  <td className="py-2 px-3 whitespace-nowrap">{formatVariantLabel(r.variant)}</td>
                  <td className="py-2 px-3 font-mono whitespace-nowrap">{r.model || "-"}</td>
                  <td className="py-2 px-3 whitespace-nowrap">{formatRunStatus(r.status)}</td>
                  <td className="py-2 px-3 font-mono text-slate-500 dark:text-slate-400 whitespace-nowrap">{formatShortTime(r.finished_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
