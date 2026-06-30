"use client";

import { CaretLeftIcon, XIcon } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { PaybackLogo } from "@/components/PaybackLogo";
import type { Msg } from "@/lib/types";
import { ChatBubble } from "./ChatBubble";
import { EmojiPicker } from "./EmojiPicker";
import { InputBox, type InputBoxHandle, type InputBoxProps } from "./InputBox";
import { TypingIndicator } from "./TypingIndicator";

interface ConversationScreenProps extends InputBoxProps {
  messages: Msg[];
  pending: boolean;
  suggestions?: string[];
  onSuggestion?: (text: string) => void;
  /** Optional — when present, a back arrow returns to a prior screen. Omitted = no home to go back to. */
  onBack?: () => void;
  onClose: () => void;
}

/** The chat view — a rounded header (back · avatar · name · Online · close) over a scrolling message
 * list and the composer. Matches Empfio's conversation screen; message state lives in the parent. */
export function ConversationScreen({
  messages,
  pending,
  suggestions = [],
  onSuggestion,
  onBack,
  onClose,
  ...input
}: ConversationScreenProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputBoxRef = useRef<InputBoxHandle>(null);
  const [emojiOpen, setEmojiOpen] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

  const empty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      {/* Header — filled PAYBACK-blue (like Empfio's), with the logo in a white tile (blue domino). */}
      <header className="flex items-center gap-2 bg-primary px-3 py-3 text-primary-foreground">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            aria-label="Zurück"
            className="flex h-8 w-8 items-center justify-center rounded-full text-primary-foreground/90 hover:bg-white/15"
          >
            <CaretLeftIcon size={18} weight="bold" />
          </button>
        )}
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white">
          <PaybackLogo className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold leading-tight">PAYBACK Assistant</p>
          <p className="flex items-center gap-1.5 text-xs text-primary-foreground/70">
            <span className="h-2 w-2 rounded-full bg-green-400" />
            Online
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Schließen"
          className="flex h-8 w-8 items-center justify-center rounded-full text-primary-foreground/90 hover:bg-white/15"
        >
          <XIcon size={18} weight="bold" />
        </button>
      </header>

      {/* Messages */}
      <div className="payback-scroll flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {empty && (
          <div className="flex flex-col gap-3">
            <div className="flex justify-start">
              <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-accent px-4 py-2.5 text-sm text-foreground">
                Hallo! Fragen Sie nach einem Produkt — ich durchsuche dm, EDEKA &amp; Amazon für Sie.
              </div>
            </div>
            {suggestions.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => onSuggestion?.(s)}
                    className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary hover:text-primary"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((msg) => (
          <ChatBubble key={msg.id} msg={msg} />
        ))}
        {pending && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Composer — relative so the emoji picker floats above it (full-width via left-0 right-0),
          fixed-height, without pushing the composer up. Matches Empfio's mount. No top border. */}
      <div className="relative shrink-0 p-3">
        {emojiOpen && (
          <div className="absolute bottom-full left-0 right-0 z-10">
            <EmojiPicker
              open
              onPick={(emoji) => inputBoxRef.current?.insertEmoji(emoji)}
            />
          </div>
        )}
        <InputBox
          ref={inputBoxRef}
          {...input}
          emojiOpen={emojiOpen}
          onToggleEmoji={() => setEmojiOpen((o) => !o)}
        />
      </div>
    </div>
  );
}
