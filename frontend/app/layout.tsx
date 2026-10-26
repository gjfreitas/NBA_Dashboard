import type { Metadata } from "next";
import Link from "next/link";
import Script from "next/script";
import { Big_Shoulders, Instrument_Sans, JetBrains_Mono } from "next/font/google";
import { Suspense } from "react";
import { AlertWatcher } from "@/components/AlertWatcher";
import { GlobalSearch } from "@/components/GlobalSearch";
import { MainNav, MainNavFallback } from "@/components/MainNav";
import { ScoreTicker } from "@/components/ScoreTicker";
import { Spotlight } from "@/components/Spotlight";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Wordmark } from "@/components/Wordmark";
import "./globals.css";

// Arena-signage condensed for headings and scores, a warm humanist sans for reading, a mono for small labels.
const display = Big_Shoulders({ variable: "--f-display", subsets: ["latin"], weight: "variable", adjustFontFallback: false, fallback: ["Impact", "Arial Narrow", "sans-serif"] });
const body = Instrument_Sans({ variable: "--f-body", subsets: ["latin"] });
const label = JetBrains_Mono({ variable: "--f-label", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "NBA Live",
  description: "Live NBA scores, play-by-play, box scores, previews and player props",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning className={`${display.variable} ${body.variable} ${label.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        {/* sets the saved theme before the first paint, so a dark choice never flashes white */}
        <Script id="theme-init" strategy="beforeInteractive" dangerouslySetInnerHTML={{ __html: "try{var t=localStorage.getItem('theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t)}catch(e){}" }} />
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-accent focus:px-3 focus:py-2 focus:text-on-accent">Skip to content</a>
        <header className="relative z-30 border-b border-line bg-surface">
          <ScoreTicker />
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 px-4">
            <div className="flex items-center gap-4">
              <Wordmark />
              <GlobalSearch />
              <ThemeToggle />
            </div>
            <Suspense fallback={<MainNavFallback />}>
              <MainNav />
            </Suspense>
          </div>
        </header>
        <AlertWatcher />
        <Spotlight />
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 pb-24 pt-5 sm:pb-8">{children}</main>
        <footer className="border-t border-line px-4 py-5 pb-24 text-center sm:pb-5">
          <p className="label text-muted">Unofficial fan project · not affiliated with or endorsed by the NBA</p>
          <p className="mt-1 text-xs text-muted"><Link href="/status" className="underline hover:text-fg">Data status</Link></p>
        </footer>
      </body>
    </html>
  );
}
