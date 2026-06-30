"use client";

import { CaretDownIcon, CheckIcon, MicrophoneIcon } from "@phosphor-icons/react";
import { useEffect, useRef } from "react";
import { useAudioDevices } from "@/hooks/useAudioDevices";
import { cn } from "@/lib/utils";

/** A small mic-picker popover (chevron → list of microphones + a live level meter). The chosen
 * device is threaded into dictation's getUserMedia, so the selection is live, not decorative.
 * A lightweight popover (click-outside to close) — no component-library dependency. */
export function MicPicker({
  open,
  onOpenChange,
  selectedDeviceId,
  onSelectDevice,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  selectedDeviceId: string | undefined;
  onSelectDevice: (deviceId: string | undefined) => void;
}) {
  const { devices, level, refresh, hasPermission } = useAudioDevices({ enabled: open, selectedDeviceId });
  const ref = useRef<HTMLDivElement>(null);

  // Populate labels on first open (browsers hide them until permission is granted once).
  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  // Click-outside closes the popover.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onOpenChange(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open, onOpenChange]);

  const rows = [{ deviceId: "", label: "Default" }, ...devices.filter((d) => d.deviceId !== "default" && d.deviceId !== "")];

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        aria-label="Choose microphone"
        className="flex h-6 w-5 items-center justify-center rounded text-muted-foreground hover:text-primary"
      >
        <CaretDownIcon className="h-3.5 w-3.5" weight="bold" />
      </button>

      {open && (
        // Anchored to the RIGHT edge + opening upward, so it never overflows the panel's right side.
        <div className="absolute bottom-9 right-0 z-30 w-60 rounded-xl border border-border bg-card p-3 shadow-xl">
          <div className="flex items-center gap-2.5">
            <MicrophoneIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
            <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted" role="meter">
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-primary transition-[width] duration-75 ease-out"
                style={{ width: `${Math.round(level * 100)}%` }}
              />
            </div>
          </div>

          <div className="mt-3 flex flex-col gap-0.5">
            {rows.map((device) => {
              const isSelected = (selectedDeviceId ?? "") === device.deviceId;
              return (
                <button
                  key={device.deviceId || "default"}
                  type="button"
                  onClick={() => {
                    onSelectDevice(device.deviceId || undefined);
                    onOpenChange(false);
                  }}
                  className={cn(
                    "flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted/60",
                    isSelected ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  <span className="truncate">{device.label}</span>
                  {isSelected && <CheckIcon className="h-3.5 w-3.5 shrink-0 text-primary" weight="bold" />}
                </button>
              );
            })}
            {!hasPermission && (
              <p className="mt-1 px-2 text-[11px] text-muted-foreground/80">
                Mikrofonzugriff erlauben, um Gerätenamen zu sehen.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
