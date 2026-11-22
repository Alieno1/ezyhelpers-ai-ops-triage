"use client";

import React from "react";
import { AlertCircle, CheckCircle2, Info, MessageSquare, Phone, ShieldAlert } from "lucide-react";
import type { Channel, IssueStatus, Urgency } from "@/lib/types";

export function UrgencyBadge({ urgency }: { urgency: Urgency | string }) {
  const styles: Record<string, string> = {
    critical: "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/70 dark:text-red-300 dark:border-red-800 font-semibold",
    high: "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/70 dark:text-amber-300 dark:border-amber-800 font-semibold",
    medium: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/70 dark:text-blue-300 dark:border-blue-800 font-medium",
    low: "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700 font-medium",
    none: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/70 dark:text-emerald-300 dark:border-emerald-800 font-medium",
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs border uppercase tracking-wide ${styles[urgency] || styles.low}`}>
      {urgency}
    </span>
  );
}

export function StatusBadge({ status }: { status: IssueStatus | string }) {
  const styles: Record<string, string> = {
    open: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/70 dark:text-sky-300 dark:border-sky-800",
    awaiting_info: "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/70 dark:text-amber-300 dark:border-amber-800",
    resolved: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/70 dark:text-emerald-300 dark:border-emerald-800",
  };
  const label = status === "awaiting_info" ? "Awaiting Info" : status;
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-md text-xs border capitalize font-medium ${styles[status] || styles.open}`}>
      {label}
    </span>
  );
}

export function DepartmentBadge({ department }: { department: string }) {
  const styles: Record<string, string> = {
    "Duty Ops": "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950/70 dark:text-indigo-300 dark:border-indigo-800",
    Billing: "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/70 dark:text-purple-300 dark:border-purple-800",
    Sales: "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-950/70 dark:text-teal-300 dark:border-teal-800",
    Sourcing: "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950/70 dark:text-orange-300 dark:border-orange-800",
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-md text-xs border font-medium ${styles[department] || "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700"}`}>
      {department}
    </span>
  );
}

export function ChannelBadge({ channel }: { channel: Channel | string }) {
  if (channel === "phone") {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-xs bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950/70 dark:text-rose-300 dark:border-rose-800 font-medium">
        <Phone className="w-3.5 h-3.5" /> Call
      </span>
    );
  }
  if (channel === "whatsapp") {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/70 dark:text-emerald-300 dark:border-emerald-800 font-medium">
        <MessageSquare className="w-3.5 h-3.5" /> WhatsApp
      </span>
    );
  }
  return <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs bg-slate-100 text-slate-500 border border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700">Hold / None</span>;
}

export function SourceBadge({ source }: { source: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    rules: { label: "Rules", cls: "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700" },
    ai_guarded: { label: "AI (Guarded)", cls: "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950/70 dark:text-violet-300 dark:border-violet-800" },
    ai_raw: { label: "AI (Raw)", cls: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200 dark:bg-fuchsia-950/70 dark:text-fuchsia-300 dark:border-fuchsia-800" },
    rules_fallback: { label: "Rules Fallback", cls: "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/70 dark:text-amber-300 dark:border-amber-800" },
    human: { label: "Human Verified", cls: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/70 dark:text-emerald-300 dark:border-emerald-800" },
  };
  const info = map[source] || { label: source, cls: "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700" };
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs border font-medium ${info.cls}`}>{info.label}</span>;
}

export function SeverityBadge({ severity }: { severity: "info" | "warning" | "error" }) {
  if (severity === "error") {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs bg-red-50 text-red-700 border border-red-200 dark:bg-red-950/70 dark:text-red-300 dark:border-red-800 font-semibold">
        <ShieldAlert className="w-3.5 h-3.5" /> Error
      </span>
    );
  }
  if (severity === "warning") {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs bg-amber-50 text-amber-800 border border-amber-200 dark:bg-amber-950/70 dark:text-amber-300 dark:border-amber-800 font-medium">
        <AlertCircle className="w-3.5 h-3.5" /> Warning
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-xs bg-slate-100 text-slate-600 border border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700">
      <Info className="w-3.5 h-3.5" /> Info
    </span>
  );
}

export function formatRunStatus(status: string): string {
  const map: Record<string, string> = {
    completed: "Completed",
    completed_with_fallback: "AI + Fallback",
    failed: "Fallback Active",
  };
  if (map[status]) return map[status];
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatVariantLabel(variant: string): string {
  const map: Record<string, string> = {
    rules_v1: "Rules v1 (Baseline)",
    rules_v2: "Rules v2 (Improved)",
    ai_prompt_v1: "AI-Assisted (Prompt v1)",
    ai_prompt_v2: "AI-Assisted (Prompt v2)",
    ai_guarded: "AI-Assisted (Guarded)",
  };
  if (map[variant]) return map[variant];
  return variant.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatShortTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const formatted = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Asia/Kolkata",
    hour12: false,
  }).format(d);
  return `${formatted} IST`;
}

export function formatLogError(errorType: string | null, errorMessage: string | null): string {
  if (!errorType && !errorMessage) return "-";
  let clean = (errorMessage || "").trim();
  if (clean.startsWith("{")) {
    try {
      const parsed = JSON.parse(clean) as { error?: { message?: string }; message?: string };
      clean = parsed?.error?.message || parsed?.message || clean;
    } catch {
      const m = clean.match(/"message"\s*:\s*"([^"]+)"/);
      if (m?.[1]) clean = m[1];
    }
  }
  const combined = errorType ? (clean ? `${errorType}: ${clean}` : errorType) : clean;
  return combined.length > 160 ? `${combined.slice(0, 157)}...` : combined;
}

export function StatCard({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: string | number;
  sub?: string;
  tone?: "default" | "danger" | "warning" | "success";
}) {
  const border =
    tone === "danger"
      ? "border-red-200 bg-red-50/40 dark:border-red-900 dark:bg-red-950/30"
      : tone === "warning"
      ? "border-amber-200 bg-amber-50/40 dark:border-amber-900 dark:bg-amber-950/30"
      : tone === "success"
      ? "border-emerald-200 bg-emerald-50/40 dark:border-emerald-900 dark:bg-emerald-950/30"
      : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900";
  const isLong = typeof value === "string" && value.length > 10;
  return (
    <div className={`rounded-xl border p-5 shadow-xs min-w-0 overflow-hidden flex flex-col justify-between h-full ${border}`}>
      <div>
        <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider truncate">
          {label}
        </div>
        <div
          className={`mt-2 font-bold text-slate-900 dark:text-slate-100 tabular-nums leading-tight break-words ${
            isLong ? "text-xl sm:text-2xl" : "text-2xl sm:text-3xl"
          }`}
        >
          {value}
        </div>
      </div>
      {sub && <div className="mt-2 text-xs text-slate-600 dark:text-slate-300 leading-snug break-words">{sub}</div>}
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200 flex items-start gap-2.5">
      <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
      <div>
        <div className="font-semibold">Backend Error</div>
        <div className="mt-0.5">{message}</div>
      </div>
    </div>
  );
}

export function SuccessBanner({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-200 flex items-start gap-2.5">
      <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
      <div>{message}</div>
    </div>
  );
}

export function LoadingPanel({ label = "Loading live shift data..." }: { label?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-10 text-center text-sm text-slate-500 dark:text-slate-400">
      <div className="inline-block w-5 h-5 border-2 border-slate-300 border-t-slate-800 dark:border-slate-700 dark:border-t-sky-400 rounded-full animate-spin mb-2" />
      <div>{label}</div>
    </div>
  );
}
