"use client";

import { ArrowUpIcon, MicrophoneIcon, SmileyIcon } from "@phosphor-icons/react";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { MicPicker } from "./voice/MicPicker";
import { RecordingInline } from "./voice/RecordingInline";

/** Imperative handle so the parent's emoji picker can insert at the cursor (Empfio's pattern). */
export interface InputBoxHandle {
  insertEmoji: (emoji: string) => void;
}

export interface InputBoxProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
  micEnabled?: boolean;
  recording?: boolean;
  onMicToggle?: () => void;
  selectedDeviceId?: string;
  onSelectDevice?: (deviceId: string | undefined) => void;
  /** Recording takeover (Empfio's RecordingInline): the live stream + interim transcript + commit/cancel. */
  recordingStream?: MediaStream | null;
  interim?: string;
  onDictationDone?: () => void;
  onDictationCancel?: () => void;
  /** Emoji picker open-state (the picker itself renders inline above the composer, in the parent). */
  emojiOpen?: boolean;
  onToggleEmoji?: () => void;
}

/** The composer — Empfio's PromptInput shape: a bordered rounded box with the textarea on top and an
 * actions row beneath (emoji far-left; mic + send on the right). While dictating, the inner content
 * swaps to RecordingInline (waveform + × + ✓) inside the SAME envelope, so the height never jumps.
 * Enter sends; Shift+Enter newlines. */
export const InputBox = forwardRef<InputBoxHandle, InputBoxProps>(function InputBox(
  {
    value,
    onChange,
    onSend,
    disabled,
    placeholder = "Nachricht eingeben…",
    micEnabled,
    recording,
    onMicToggle,
    selectedDeviceId,
    onSelectDevice,
    recordingStream,
    interim,
    onDictationDone,
    onDictationCancel,
    emojiOpen,
    onToggleEmoji,
  }: InputBoxProps,
  ref,
) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  // Insert an emoji at the cursor (or replace the selection), then keep focus + caret after it.
  useImperativeHandle(ref, () => ({
    insertEmoji: (emoji: string) => {
      const el = textareaRef.current;
      const start = el?.selectionStart ?? value.length;
      const end = el?.selectionEnd ?? value.length;
      const next = value.slice(0, start) + emoji + value.slice(end);
      onChange(next);
      requestAnimationFrame(() => {
        if (!el) return;
        el.focus();
        const caret = start + emoji.length;
        el.setSelectionRange(caret, caret);
      });
    },
  }));

  // Auto-grow from the fixed resting height up to a cap. The RESTING height (h-11 = 44px, Empfio's
  // compact surface) MATCHES TranscriptView's fixed h-11, so swapping to the recording takeover never
  // changes the composer's height — Empfio's "geometry-stable swap" contract.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(Math.max(el.scrollHeight, 44), 120)}px`;
  }, [value]);

  const canSend = value.trim().length > 0 && !disabled;
  const actionBtn = "flex h-8 w-8 items-center justify-center rounded-md transition-colors";

  return (
    <div className="rounded-xl border-2 border-border bg-card px-3 py-2 focus-within:border-primary">
      {recording ? (
        // The recording takeover replaces the textarea + actions inside the same envelope.
        <RecordingInline
          interim={interim ?? ""}
          stream={recordingStream ?? null}
          onCancel={() => onDictationCancel?.()}
          onDone={() => onDictationDone?.()}
        />
      ) : (
        <>
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (canSend) onSend();
              }
            }}
            rows={1}
            placeholder={placeholder}
            disabled={disabled}
            // h-11 resting height matches TranscriptView's fixed h-11, so the recording swap is
            // height-stable (no growth). Auto-grows up to max-h-[120px] for multi-line drafts.
            className="payback-scroll h-11 max-h-[120px] w-full resize-none bg-transparent py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
          />

          <div className="flex items-center justify-between pt-1">
            {/* Left: emoji toggle (the picker renders inline above the composer, in the parent). */}
            <button
              type="button"
              onClick={onToggleEmoji}
              aria-label="Emoji"
              className={cn(actionBtn, emojiOpen ? "bg-muted text-primary" : "text-muted-foreground hover:bg-muted")}
            >
              <SmileyIcon size={18} />
            </button>

            {/* Right: mic (+ device picker) and send. */}
            <div className="flex items-center gap-1">
              {micEnabled && (
                <div className="flex items-center">
                  <button
                    type="button"
                    onClick={onMicToggle}
                    aria-label="Diktat starten"
                    className={cn(actionBtn, "text-muted-foreground hover:bg-muted")}
                  >
                    <MicrophoneIcon size={18} />
                  </button>
                  {onSelectDevice && (
                    <MicPicker
                      open={pickerOpen}
                      onOpenChange={setPickerOpen}
                      selectedDeviceId={selectedDeviceId}
                      onSelectDevice={onSelectDevice}
                    />
                  )}
                </div>
              )}

              <button
                type="button"
                onClick={() => canSend && onSend()}
                disabled={!canSend}
                aria-label="Senden"
                className={cn(actionBtn, canSend ? "bg-primary text-primary-foreground hover:bg-primary-hover" : "bg-muted text-muted-foreground")}
              >
                <ArrowUpIcon size={16} weight="bold" />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
});
