import Link from "next/link";
import Script from "next/script";
import { PaybackLogo } from "@/components/PaybackLogo";

/** Die Demo-Startseite. Die schwebende Chat-Blase (von /widget.js geladen) ist der Kern; diese Seite
 * gibt ihr ein Zuhause und verlinkt auf den Produktkatalog. */
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

        <Link
          href="/products"
          className="mt-8 inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover"
        >
          Alle Produkte ansehen
        </Link>

        <p className="mt-10 text-sm text-muted-foreground">
          Tippen Sie auf die Chat-Blase, um zu starten →
        </p>
      </div>

      {/* Das einbettbare Widget — dasselbe Skript, das ein Partner auf seiner Seite einbinden würde. */}
      <Script src="/widget.js" strategy="afterInteractive" />
    </main>
  );
}
