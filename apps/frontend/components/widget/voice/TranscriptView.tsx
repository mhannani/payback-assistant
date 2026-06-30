"use client";

/**
 * Fixed-height, auto-scrolling transcript window for the live voice
 * surfaces (dictation + voice mode).
 *
 * WHY this exists: streaming STT interims accumulate text continuously,
 * so a naturally-sized line (e.g. ``line-clamp-3`` over a ``min-h`` floor)
 * steps 1 → 2 → 3 lines as words arrive and then collapses back on each
 * final — every step changes the surface height, which reflows the
 * composer and reads as flicker/jump. This view instead reserves a
 * CONSTANT height and scrolls its content, so the box never changes size
 * regardless of how much text streams in. Latest words stay visible
 * because it auto-scrolls to the bottom whenever the text grows.
 *
 * The placeholder (pre-speech "Listening…" etc.) renders in the same
 * fixed box, so the swap from placeholder → live text is also height-
 * stable.
 */

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

interface TranscriptViewProps {
  /** Live transcript text; empty string shows the placeholder. */
  text: string;
  /** Shown (muted/italic) before any text has streamed in. */
  placeholder: string;
  /** Tight layout for active-conversation surfaces — matches the
   *  composer's ``compact`` prop. Mirrors the idle textarea's min-height
   *  so the resting footprint is identical, but as a FIXED height (not a
   *  floor) so growth can't reflow it. */
  compact?: boolean;
  className?: string;
}

export function TranscriptView({
  text,
  placeholder,
  compact = false,
  className,
}: TranscriptViewProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Keep the newest words visible as the transcript grows — scroll to the
  // bottom on every text change. Cheap (a single scrollTop write) and never
  // changes layout, so it can't cause the flicker it's replacing.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [text]);

  return (
    <div
      ref={scrollRef}
      // FIXED height (h-*, not min-h-*) so the box is identical whether the
      // transcript is empty, one line, or overflowing — overflow scrolls
      // instead of growing. ``h-11``/``h-14`` match the idle textarea's
      // ``min-h-11``/``min-h-14`` resting footprint.
      className={cn(
        "w-full overflow-y-auto px-3",
        compact ? "h-11 py-2" : "h-14 py-2.5",
        // Hide the scrollbar — the auto-scroll keeps the tail in view, and a
        // visible bar on a 2-3 line box is visual noise.
        "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        className,
      )}
      aria-live="polite"
    >
      <p
        className={cn(
          "text-base md:text-sm",
          text ? "text-foreground" : "italic text-muted-foreground",
        )}
      >
        {text || placeholder}
      </p>
    </div>
  );
}
