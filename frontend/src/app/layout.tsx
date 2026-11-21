import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { DatasetProvider } from "@/components/DatasetContext";
import { ThemeProvider } from "@/components/ThemeContext";
import { AppShell } from "@/components/AppShell";

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

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <ThemeProvider>
          <DatasetProvider>
            <AppShell>{children}</AppShell>
          </DatasetProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
