import type { ReactNode } from "react";
import type { Metadata } from "next";
import { Inter } from "next/font/google";

import "./globals.css";

import { Navigation } from "@/components/layout/navigation";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "AutoApply",
  description: "Pipeline dashboard for AutoApply agents and application tracking.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
          <header className="flex flex-col gap-4">
            <div className="panel overflow-hidden">
              <div className="flex flex-col gap-4 p-6 md:flex-row md:items-end md:justify-between">
                <div className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.28em] text-sky-700 dark:text-sky-300">
                    AutoApply Control Room
                  </p>
                  <h1 className="text-3xl font-semibold tracking-tight text-slate-950 dark:text-white">
                    Track the pipeline, review edge cases, and watch agents move.
                  </h1>
                </div>
                <div className="max-w-sm text-sm text-slate-600 dark:text-slate-300">
                  A lightweight Next.js shell for the FastAPI, RabbitMQ, Redis, and
                  Gmail-driven automation flow.
                </div>
              </div>
            </div>
            <Navigation />
          </header>
          <main className="pb-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
