"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  CheckSquare,
  Clock,
  Database,
  Download,
  FlaskConical,
  LayoutDashboard,
  ListOrdered,
  Moon,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { useDataset } from "@/components/DatasetContext";
import { useTheme } from "@/components/ThemeContext";
import { getModelStatus } from "@/lib/api";
import type { DatasetName, ModelStatusResponse } from "@/lib/types";

const NAV_ITEMS = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/queue", label: "Priority Queue", icon: ListOrdered },
  { href: "/review", label: "Human Review", icon: CheckSquare },
  { href: "/evaluation", label: "Evaluation", icon: FlaskConical },
  { href: "/data-quality", label: "Data Quality", icon: Database },
  { href: "/exports", label: "Exports & Model", icon: Download },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { dataset, setDataset } = useDataset();
  const { theme, toggleTheme } = useTheme();
  const [modelStatus, setModelStatus] = useState<ModelStatusResponse | null>(null);

  useEffect(() => {
    getModelStatus()
      .then(setModelStatus)
      .catch(() => {});
  }, []);

  return (
    <div className="min-h-screen flex bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-slate-200 dark:bg-slate-900 dark:border-slate-800 hidden md:flex flex-col shrink-0">
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-slate-900 text-white dark:bg-sky-500 dark:text-slate-950 flex items-center justify-center font-bold text-sm">
              EH
            </div>
            <div>
              <div className="font-bold text-sm text-slate-900 dark:text-slate-100 leading-tight">EzyHelpers</div>
              <div className="text-[11px] text-slate-500 dark:text-slate-400">AI Duty Desk Triage</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? "bg-slate-900 text-white dark:bg-sky-500 dark:text-slate-950"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
                }`}
              >
                <Icon className="w-4 h-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-200 dark:border-slate-800 space-y-2.5 text-xs">
          <div className="rounded-lg bg-slate-50 border border-slate-200 dark:bg-slate-800/70 dark:border-slate-700 p-2.5">
            <div className="flex items-center gap-1.5 font-semibold text-slate-700 dark:text-slate-200">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              Draft-Only Guardrail Active
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400 leading-snug">
              Outgoing replies remain drafts. No automatic WhatsApp, refund, or ETA promises.
            </div>
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500">
            Bengaluru Shift Snapshot · 23 Nov 2026
          </div>
        </div>
      </aside>

      {/* Main Column */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="bg-white border-b border-slate-200 dark:bg-slate-900 dark:border-slate-800 px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200 text-xs font-medium">
              <Clock className="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" />
              Mon 23 Nov 2026 · 09:00 IST
            </div>
            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-slate-500 dark:text-slate-400 font-medium">Dataset:</span>
              <select
                aria-label="Select dataset"
                value={dataset}
                onChange={(e) => setDataset(e.target.value as DatasetName)}
                className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-sky-500"
              >
                <option value="supplied">Supplied Shift Inbox (12 msgs / 6 bookings)</option>
                <option value="harder">Harder Synthetic Set (6 msgs / 4 bookings)</option>
              </select>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label="Toggle color theme"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 cursor-pointer"
            >
              {theme === "dark" ? (
                <>
                  <Sun className="w-3.5 h-3.5 text-amber-400" /> Light
                </>
              ) : (
                <>
                  <Moon className="w-3.5 h-3.5 text-slate-600" /> Dark
                </>
              )}
            </button>
            {modelStatus && (
              <Link
                href="/exports"
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border font-medium ${
                  modelStatus.api_key_configured
                    ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800"
                    : "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800"
                }`}
              >
                <Activity className="w-3.5 h-3.5" />
                {modelStatus.api_key_configured
                  ? `OpenRouter Ready (${modelStatus.model})`
                  : `Rules-Only Fallback (OpenRouter Key Pending)`}
              </Link>
            )}
          </div>
        </header>

        {/* Mobile Nav */}
        <nav className="md:hidden bg-white border-b border-slate-200 dark:bg-slate-900 dark:border-slate-800 px-3 py-2 flex gap-1.5 overflow-x-auto">
          {NAV_ITEMS.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`px-2.5 py-1 rounded-md text-xs font-medium whitespace-nowrap ${
                  active
                    ? "bg-slate-900 text-white dark:bg-sky-500 dark:text-slate-950"
                    : "text-slate-600 bg-slate-100 dark:text-slate-300 dark:bg-slate-800"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <main className="flex-1 p-4 sm:p-6 max-w-7xl w-full mx-auto">{children}</main>
      </div>
    </div>
  );
}
