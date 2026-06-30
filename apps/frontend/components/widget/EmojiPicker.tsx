"use client";

import data from "@emoji-mart/data";
import Picker from "@emoji-mart/react";
import type { CSSProperties } from "react";

/** Emoji picker — Empfio's EmojiPickerPanel shape: NOT a floating popover but an inline block that
 * sits above the composer in the flex column, with a FIXED height so it never covers the chat. The
 * brand accent (PAYBACK blue) is passed via the `--rgb-accent` CSS var emoji-mart reads. */
export function EmojiPicker({
  open,
  onPick,
  height = 260,
}: {
  open: boolean;
  onPick: (emoji: string) => void;
  height?: number;
}) {
  if (!open) return null;

  return (
    // `[&_em-emoji-picker]:w-full` forces emoji-mart's web-component host to fill the panel width —
    // dynamicWidth then derives the column count from the real width (so it spans the whole widget,
    // not a fixed ~256px block). The web component also needs an explicit height to fill the panel.
    <div
      className="w-full shrink-0 overflow-hidden border-t border-border [&_em-emoji-picker]:!h-full [&_em-emoji-picker]:w-full [&_em-emoji-picker]:min-h-0"
      style={{ "--rgb-accent": "0, 70, 170", height, maxHeight: height } as CSSProperties} // PAYBACK blue
    >
      <Picker
        data={data}
        onEmojiSelect={(e: { native: string }) => onPick(e.native)}
        theme="light"
        previewPosition="none"
        skinTonePosition="search"
        set="native"
        emojiSize={22}
        emojiButtonSize={32}
        dynamicWidth
        maxFrequentRows={2}
      />
    </div>
  );
}
