"use client";

/**
 * Recording inner content — swapped in for the composer's textarea + actions row while the mic is
 * live, INSIDE the same outer envelope the composer normally renders. The envelope (border, rounded,
 * padding) lives on the composer; this owns only the inner content, so the composer height does not
 * change when recording starts.
 *
 * Ported faithfully from Empfio's voice-recording/recording-inline.tsx — the only change is local
 * imports + inline strings (no injected i18n ``copy``).
 *
 *   - Interim transcript at the top (muted italic → foreground once the user speaks).
 *   - Live RMS waveform in the actions row.
 *   - Cancel (×) — abort, discard the transcript.
 *   - Done (✓) — commit; the transcript stays in the composer draft. NO auto-submit.
 */

import { CheckIcon as Check, XIcon as Close } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { LiveWaveform } from "./LiveWaveform";
import { TranscriptView } from "./TranscriptView";

interface RecordingInlineProps {
  /** Live interim transcript streamed from the backend's Deepgram proxy. */
  interim: string;
  /** Live MediaStream from the recorder, forwarded into LiveWaveform (null while permission pending). */
  stream: MediaStream | null;
  /** Discard the active recording — closes the WS without flushing, restores the pre-recording draft. */
  onCancel: () => void;
  /** Commit the recording — flushes the WS and leaves the final transcript in the composer. */
  onDone: () => void;
  className?: string;
}

export function RecordingInline({ interim, stream, onCancel, onDone, className }: RecordingInlineProps) {
  return (
    <div className={cn("flex flex-col", className)} role="region" aria-label="Voice dictation">
      {/* Fixed-height, auto-scrolling transcript window — accumulating interims never reflow it.
          compact (h-11) matches the idle textarea's resting height, so the swap is height-stable. */}
      <TranscriptView text={interim} placeholder="Höre zu…" compact />

      {/* Actions row — same shape (justify-between, pt-2) as the idle actions row, so the swap is
          geometrically invisible. */}
      <div className="flex items-center justify-between gap-2 pt-2">
        <div className="flex h-8 flex-1 items-center" aria-hidden="true">
          <LiveWaveform stream={stream} />
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onCancel}
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-md transition-colors",
              "bg-muted text-muted-foreground hover:bg-muted/70 hover:text-foreground",
            )}
            aria-label="Abbrechen"
          >
            <Close className="h-4 w-4" weight="bold" />
          </button>

          <button
            type="button"
            onClick={onDone}
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-md transition-colors",
              "bg-primary text-primary-foreground hover:bg-primary/90",
            )}
            aria-label="Fertig"
          >
            <Check className="h-4 w-4" weight="bold" />
          </button>
        </div>
      </div>
    </div>
  );
}
