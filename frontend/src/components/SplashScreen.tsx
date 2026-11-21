"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";

type SplashPhase = "active" | "exiting" | "done";

const SPLASH_STORAGE_KEY = "eh_splash_seen";

export function SplashScreen({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<SplashPhase>("active");

  useEffect(() => {
    let forcePreview = false;
    try {
      const params = new URLSearchParams(window.location.search);
      forcePreview = params.get("splash") === "1";
    } catch {
      forcePreview = false;
    }

    let alreadySeen = false;
    try {
      alreadySeen = window.sessionStorage.getItem(SPLASH_STORAGE_KEY) === "1";
    } catch {
      alreadySeen = false;
    }

    if (alreadySeen && !forcePreview) {
      document.documentElement.dataset.splash = "skip";
      setPhase("done");
      return;
    }

    if (forcePreview) {
      delete document.documentElement.dataset.splash;
    }

    try {
      window.sessionStorage.setItem(SPLASH_STORAGE_KEY, "1");
    } catch {
      // Ignore storage access errors in restricted browsing modes
    }

    const prefersReduced =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const holdMs = prefersReduced ? 450 : 1850;
    const exitMs = prefersReduced ? 220 : 520;

    let doneTimer: number | undefined;
    const exitTimer = window.setTimeout(() => {
      setPhase("exiting");
      doneTimer = window.setTimeout(() => {
        document.documentElement.dataset.splash = "skip";
        setPhase("done");
      }, exitMs);
    }, holdMs);

    return () => {
      window.clearTimeout(exitTimer);
      if (doneTimer !== undefined) {
        window.clearTimeout(doneTimer);
      }
    };
  }, []);

  const appWrapperClass =
    phase === "done"
      ? ""
      : phase === "exiting"
        ? "transition-all duration-500 ease-out opacity-100 scale-100"
        : "opacity-95 scale-[0.985] transition-all duration-500 ease-out";

  return (
    <>
      <div className={appWrapperClass}>{children}</div>

      {phase !== "done" && (
        <div
          aria-hidden={phase === "exiting"}
          className={`eh-splash-root fixed inset-0 z-[100] flex flex-col items-center justify-center overflow-hidden bg-[#f7f9fc] px-6 select-none transition-all duration-500 ease-out ${
            phase === "exiting"
              ? "opacity-0 scale-[1.035] pointer-events-none"
              : "opacity-100 scale-100"
          }`}
        >
          {/* Clean off-white + soft blue SaaS ambient backdrop */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(64% 52% at 50% 42%, rgba(56, 189, 248, 0.14) 0%, rgba(37, 99, 235, 0.06) 44%, rgba(247, 249, 252, 0) 76%)",
            }}
          />

          <div className="relative z-10 flex flex-col items-center text-center">
            {/* Official EzyHelpers logo with scale/fade entrance, subtle glow, and blue light-sweep */}
            <div className="eh-splash-logo-wrap relative w-44 sm:w-56 md:w-60">
              <div
                aria-hidden="true"
                className="eh-splash-glow pointer-events-none absolute -inset-6 rounded-full blur-2xl"
                style={{
                  background:
                    "radial-gradient(circle, rgba(56, 189, 248, 0.34) 0%, rgba(37, 99, 235, 0.16) 52%, transparent 74%)",
                }}
              />

              <div className="relative">
                <Image
                  src="/ezyhelpers-splash-logo.png"
                  alt="EzyHelpers"
                  width={816}
                  height={796}
                  priority
                  unoptimized
                  className="relative z-10 w-full h-auto block drop-shadow-[0_12px_28px_rgba(37,99,235,0.12)]"
                />
                {/* Diagonal blue gradient light-sweep masked to exact logo silhouette */}
                <div
                  aria-hidden="true"
                  className="eh-splash-sweep pointer-events-none absolute inset-0 z-20 overflow-hidden"
                />
              </div>
            </div>

            {/* Circular loading indicator + status text */}
            <div className="eh-splash-status mt-8 flex flex-col items-center gap-3.5">
              <div role="status" aria-label="Preparing your workspace" className="relative w-9 h-9">
                <svg viewBox="0 0 40 40" className="eh-spinner-svg w-9 h-9" fill="none">
                  <defs>
                    <linearGradient id="ehSplashSpinnerGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#38bdf8" />
                      <stop offset="55%" stopColor="#2563eb" />
                      <stop offset="100%" stopColor="#0284c7" />
                    </linearGradient>
                  </defs>
                  <circle
                    cx="20"
                    cy="20"
                    r="16"
                    stroke="rgba(37, 99, 235, 0.14)"
                    strokeWidth="3"
                  />
                  <circle
                    cx="20"
                    cy="20"
                    r="16"
                    stroke="url(#ehSplashSpinnerGrad)"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeDasharray="62 95"
                    className="eh-spinner-arc"
                  />
                </svg>
              </div>
              <p className="text-sm font-medium tracking-wide text-slate-600">
                Preparing your workspace...
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
