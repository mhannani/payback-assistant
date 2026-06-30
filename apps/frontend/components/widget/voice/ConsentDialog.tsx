"use client";

import { MicrophoneIcon } from "@phosphor-icons/react";

/** A one-time microphone-consent gate shown before the first dictation.
 *
 * The widget visitor is anonymous, so consent is a session-local acknowledgment (GDPR Art. 13 /
 * §201 StGB) rather than a server record — the dialog renders once, and the grant lives in the
 * panel's state for the session. The browser's own getUserMedia prompt is the second, OS-level gate. */
export function ConsentDialog({ onGrant, onCancel }: { onGrant: () => void; onCancel: () => void }) {
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-foreground/30 p-4">
      <div className="w-full max-w-xs rounded-2xl bg-card p-5 text-center shadow-xl">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-accent">
          <MicrophoneIcon className="h-6 w-6 text-primary" />
        </div>
        <h2 className="mt-3 text-sm font-semibold text-foreground">Mikrofon verwenden?</h2>
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
          Wir wandeln Ihre Sprache in Text um, der ins Nachrichtenfeld geschrieben wird. Audio wird nur
          während des Sprechens verarbeitet und nicht gespeichert.
        </p>
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 rounded-lg border border-border px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted"
          >
            Jetzt nicht
          </button>
          <button
            type="button"
            onClick={onGrant}
            className="flex-1 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover"
          >
            Erlauben
          </button>
        </div>
      </div>
    </div>
  );
}
