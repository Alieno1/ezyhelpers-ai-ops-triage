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
      <div className="px-4 min-h-[68px] py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-2">
        <Link href="/" onClick={onNavigate} className="flex items-center gap-3 min-w-0">
          <Image
            src="/ezyhelpers-logo.png"
            alt="EzyHelpers logo"
            width={56}
            height={39}
            className="h-10 w-auto object-contain shrink-0"
            priority
          />
          <div className="min-w-0">
            <div className="font-bold text-lg text-slate-900 dark:text-slate-100 leading-tight tracking-tight truncate">EzyHelpers</div>
            <div className="text-xs font-medium text-slate-600 dark:text-slate-300 mt-0.5 truncate">AI Duty Desk Triage</div>
          </div>
        </Link>
        {showClose && (
          <button
            type="button"
            onClick={onNavigate}
            aria-label="Close navigation menu"
            className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      <nav className="flex-1 p-3.5 space-y-1.5">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? "bg-slate-900 text-white dark:bg-sky-500 dark:text-slate-950"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
              }`}
            >
              <Icon className="w-5 h-5 shrink-0" />
              <span className="truncate">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-slate-200 dark:border-slate-800 space-y-3 text-xs">
        <div className="rounded-lg bg-slate-50 border border-slate-200 dark:bg-slate-800/70 dark:border-slate-700 p-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200 whitespace-nowrap">
            <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
            Draft-Only Guardrail Active
          </div>
          <div className="mt-1.5 text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
            Outgoing replies remain drafts. No automatic WhatsApp, refund, or ETA promises.
          </div>
        </div>
        <div className="text-xs font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap">
          Shift Snapshot · 23 Nov 2026
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
      <aside className="hidden lg:flex lg:sticky lg:top-0 lg:h-screen w-64 bg-white border-r border-slate-200 dark:bg-slate-900 dark:border-slate-800 flex-col shrink-0 overflow-y-auto">
        <SidebarContent pathname={pathname} />
      </aside>

      {/* Mobile / Tablet Slide-Over Drawer */}
      {mobileMenuOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-xs lg:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
          <aside className="fixed inset-y-0 left-0 z-50 w-72 bg-white border-r border-slate-200 dark:bg-slate-900 dark:border-slate-800 flex flex-col overflow-y-auto lg:hidden shadow-xl">
            <SidebarContent pathname={pathname} onNavigate={() => setMobileMenuOpen(false)} showClose />
          </aside>
        </>
      )}

      {/* Main Column */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Sticky Header aligned with page max-w-[1480px] container */}
        <header className="sticky top-0 z-30 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xs border-b border-slate-200 dark:border-slate-800">
          <div className="max-w-[1480px] w-full mx-auto px-4 sm:px-6 min-h-[68px] py-2.5 flex flex-wrap items-center justify-between gap-2.5">
            <div className="flex items-center gap-2 sm:gap-2.5 flex-wrap min-w-0 w-full sm:w-auto">
              <button
                type="button"
                onClick={() => setMobileMenuOpen(true)}
                aria-label="Open navigation menu"
                className="lg:hidden inline-flex items-center justify-center p-2.5 rounded-lg border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 cursor-pointer shrink-0"
              >
                <Menu className="w-5 h-5" />
              </button>
              <Link
                href="/"
                aria-label="EzyHelpers Home"
                className="lg:hidden flex items-center gap-2 shrink-0"
              >
                <Image
                  src="/ezyhelpers-logo.png"
                  alt="EzyHelpers logo"
                  width={44}
                  height={31}
                  className="h-8 w-auto object-contain shrink-0"
                  priority
                />
                <span className="font-bold text-base text-slate-900 dark:text-slate-100">EzyHelpers</span>
              </Link>
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200 text-xs sm:text-sm font-medium whitespace-nowrap">
                <Clock className="w-4 h-4 text-slate-500 dark:text-slate-400 shrink-0" />
                Mon 23 Nov 2026 · 09:00 IST
              </div>
              <div className="flex items-center gap-1.5 text-xs sm:text-sm min-w-0 w-full sm:w-auto">
                <span className="text-slate-500 dark:text-slate-400 font-medium hidden sm:inline">Dataset:</span>
                <select
                  aria-label="Select dataset"
                  value={dataset}
                  onChange={(e) => setDataset(e.target.value as DatasetName)}
                  className="w-full sm:w-auto max-w-full min-w-0 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs sm:text-sm font-medium text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-900 dark:focus:ring-sky-500"
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
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 bg-white text-xs sm:text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 cursor-pointer shrink-0"
              >
                {theme === "dark" ? (
                  <>
                    <Sun className="w-4 h-4 text-amber-400" /> Light
                  </>
                ) : (
                  <>
                    <Moon className="w-4 h-4 text-slate-600" /> Dark
                  </>
                )}
              </button>
              {modelStatus && (
                <Link
                  href="/exports"
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs sm:text-sm border font-medium max-w-full truncate ${
                    modelStatus.api_key_configured
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800"
                      : "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800"
                  }`}
                >
                  <Activity className="w-4 h-4 shrink-0" />
                  {modelStatus.api_key_configured ? (
                    <span className="truncate">
                      OpenRouter Ready<span className="hidden xl:inline"> ({modelStatus.model})</span>
                    </span>
                  ) : (
                    <span className="truncate">
                      Rules-Only<span className="hidden xl:inline"> Fallback (OpenRouter Key Pending)</span>
                    </span>
                  )}
                </Link>
              )}
            </div>
          </div>
        </header>

        <main className="flex-1 w-full max-w-[1480px] mx-auto px-4 sm:px-6 py-6 min-w-0">
          {children}
        </main>
      </div>
    </div>
  );
}
