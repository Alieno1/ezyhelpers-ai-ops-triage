"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
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
  Menu,
  Moon,
  ShieldCheck,
  Sun,
  X,
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

function SidebarContent({
  pathname,
  onNavigate,
  showClose = false,
}: {
  pathname: string;
  onNavigate?: () => void;
  showClose?: boolean;
}) {
  return (
    <>
      <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-2">
        <Link href="/" onClick={onNavigate} className="flex items-center gap-2.5 min-w-0">
          <div className="w-9 h-9 rounded-lg bg-white border border-slate-200 dark:border-slate-700 p-1 flex items-center justify-center shrink-0 shadow-2xs">
            <Image
              src="/ezyhelpers-logo.png"
              alt="EzyHelpers logo"
              width={36}
              height={36}
              className="w-full h-full object-contain"
              priority
            />
          </div>
          <div className="min-w-0">
            <div className="font-bold text-sm text-slate-900 dark:text-slate-100 leading-tight truncate">EzyHelpers</div>
            <div className="text-[11px] text-slate-500 dark:text-slate-400 truncate">AI Duty Desk Triage</div>
          </div>
        </Link>
        {showClose && (
          <button
            type="button"
            onClick={onNavigate}
            aria-label="Close navigation menu"
            className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? "bg-slate-900 text-white dark:bg-sky-500 dark:text-slate-950"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span className="truncate">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-slate-200 dark:border-slate-800 space-y-2.5 text-xs">
        <div className="rounded-lg bg-slate-50 border border-slate-200 dark:bg-slate-800/70 dark:border-slate-700 p-2.5">
          <div className="flex items-center gap-1.5 font-semibold text-slate-700 dark:text-slate-200">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
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
    </>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { dataset, setDataset } = useDataset();
  const { theme, toggleTheme } = useTheme();
  const [modelStatus, setModelStatus] = useState<ModelStatusResponse | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    getModelStatus()
      .then(setModelStatus)
      .catch(() => {});
  }, []);

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  return (
    <div className="min-h-screen flex bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      {/* Sticky Desktop Sidebar */}
      <aside className="hidden lg:flex lg:sticky lg:top-0 lg:h-screen w-60 bg-white border-r border-slate-200 dark:bg-slate-900 dark:border-slate-800 flex-col shrink-0 overflow-y-auto">
        <SidebarContent pathname={pathname} />
      </aside>

      {/* Mobile / Tablet Slide-Over Drawer */}
      {mobileMenuOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-xs lg:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
          <aside className="fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-slate-200 dark:bg-slate-900 dark:border-slate-800 flex flex-col overflow-y-auto lg:hidden shadow-xl">
            <SidebarContent pathname={pathname} onNavigate={() => setMobileMenuOpen(false)} showClose />
          </aside>
        </>
      )}

      {/* Main Column */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Sticky Header aligned with page max-w-7xl container */}
        <header className="sticky top-0 z-30 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xs border-b border-slate-200 dark:border-slate-800">
          <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-2.5 flex flex-wrap items-center justify-between gap-2.5">
            <div className="flex items-center gap-2.5 flex-wrap min-w-0">
              <button
                type="button"
                onClick={() => setMobileMenuOpen(true)}
                aria-label="Open navigation menu"
                className="lg:hidden inline-flex items-center justify-center p-1.5 rounded-lg border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 cursor-pointer shrink-0"
              >
                <Menu className="w-4 h-4" />
              </button>
              <Link
                href="/"
                aria-label="EzyHelpers Home"
                className="lg:hidden w-8 h-8 rounded-lg bg-white border border-slate-200 dark:border-slate-700 p-1 flex items-center justify-center shrink-0"
              >
                <Image
                  src="/ezyhelpers-logo.png"
                  alt="EzyHelpers logo"
                  width={32}
                  height={32}
                  className="w-full h-full object-contain"
                  priority
                />
              </Link>
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200 text-xs font-medium whitespace-nowrap">
                <Clock className="w-3.5 h-3.5 text-slate-500 dark:text-slate-400 shrink-0" />
                Mon 23 Nov 2026 · 09:00 IST
              </div>
              <div className="flex items-center gap-1.5 text-xs min-w-0 max-w-full">
                <span className="text-slate-500 dark:text-slate-400 font-medium hidden sm:inline">Dataset:</span>
                <select
                  aria-label="Select dataset"
                  value={dataset}
                  onChange={(e) => setDataset(e.target.value as DatasetName)}
                  className="max-w-full min-w-0 rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-sky-500"
                >
                  <option value="supplied">Supplied Shift Inbox (12 msgs / 6 bookings)</option>
                  <option value="harder">Harder Synthetic Set (6 msgs / 4 bookings)</option>
                </select>
              </div>
            </div>

            <div className="flex items-center gap-2 flex-wrap min-w-0">
              <button
                type="button"
                onClick={toggleTheme}
                aria-label="Toggle color theme"
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 cursor-pointer shrink-0"
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
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border font-medium max-w-full truncate ${
                    modelStatus.api_key_configured
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800"
                      : "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800"
                  }`}
                >
                  <Activity className="w-3.5 h-3.5 shrink-0" />
                  {modelStatus.api_key_configured ? (
                    <span className="truncate">
                      OpenRouter Ready<span className="hidden sm:inline"> ({modelStatus.model})</span>
                    </span>
                  ) : (
                    <span className="truncate">
                      Rules-Only<span className="hidden sm:inline"> Fallback (OpenRouter Key Pending)</span>
                    </span>
                  )}
                </Link>
              )}
            </div>
          </div>
        </header>

        <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 sm:py-6 min-w-0">
          {children}
        </main>
      </div>
    </div>
  );
}
