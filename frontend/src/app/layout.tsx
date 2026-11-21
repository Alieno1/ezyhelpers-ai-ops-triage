import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { DatasetProvider } from "@/components/DatasetContext";
import { ThemeProvider } from "@/components/ThemeContext";
import { AppShell } from "@/components/AppShell";
import { SplashScreen } from "@/components/SplashScreen";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "EzyHelpers Operations Triage Desk",
  description: "Evidence-backed AI & deterministic operations triage workbench for EzyHelpers Bengaluru.",
};

const SPLASH_PREPAINT_SCRIPT = `(function(){try{if(sessionStorage.getItem('eh_splash_seen')==='1'&&!/[?&]splash=1(?:&|$)/.test(location.search)){document.documentElement.dataset.splash='skip';}}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: SPLASH_PREPAINT_SCRIPT }} />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <ThemeProvider>
          <DatasetProvider>
            <SplashScreen>
              <AppShell>{children}</AppShell>
            </SplashScreen>
          </DatasetProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
