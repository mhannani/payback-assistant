import Link from "next/link";
import { PaybackLogo } from "@/components/PaybackLogo";

/** Die Demo-Startseite. Die schwebende Chat-Blase (aus /widget.js, im App-Shell geladen) ist der
 * Kern; diese Seite gibt ihr ein Zuhause und verlinkt auf den Produktkatalog. */
export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-background px-6">
      <div className="flex w-full max-w-xl flex-col items-center text-center">
        <PaybackLogo className="h-12 w-auto" />

        <h1 className="mt-8 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
          Produkte bei dm, EDEKA &amp; Amazon finden
        </h1>
        <p className="mt-4 max-w-md text-base text-muted-foreground">
          Einfach fragen — auf Deutsch oder Englisch. Der PAYBACK-Assistent durchsucht alle
          Partner-Kataloge auf einmal und empfiehlt die beste Wahl.
        </p>

        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/products"
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover"
          >
            Alle Produkte ansehen
          </Link>
          {/* Self-hosted Langfuse dashboard — every Assistent-Antwort ist dort als Trace sichtbar.
              Hardcoded wie die übrigen Demo-URLs (Single-Tenant-Demo, vgl. widget.js). */}
          <a
            href="https://langfuse.payback.mhannani.me"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-border px-5 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
          >
            Live-Traces ansehen
          </a>
        </div>

        <p className="mt-10 text-sm text-muted-foreground">
          Tippen Sie auf die Chat-Blase, um zu starten →
        </p>
      </div>
    </main>
  );
}
