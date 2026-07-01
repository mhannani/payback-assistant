"use client";

import Script from "next/script";
import { usePathname } from "next/navigation";

/** Loads the floating chat widget (/widget.js) on every host page from the app shell, so it survives
 * hard reloads and client navigations alike (it lived on the home page only, so /products had no
 * bubble on reload). Skipped on /widget itself — that route IS the iframe the script embeds, and
 * loading the script there would inject a bubble inside the bubble. */
export function WidgetEmbed() {
  const pathname = usePathname();
  if (pathname?.startsWith("/widget")) return null;
  return <Script src="/widget.js" strategy="afterInteractive" />;
}
