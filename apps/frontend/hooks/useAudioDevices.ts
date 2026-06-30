"use client";

/**
 * Enumerate audio input devices + provide a live RMS level meter for
 * the device picker popover.
 *
 * Browser quirks this handles:
 *
 *   - ``enumerateDevices()`` returns empty labels until the page has
 *     held a microphone permission at least once. We force one
 *     ``getUserMedia({audio:true})`` call on ``refresh()`` so the
 *     subsequent list has human-readable names.
 *   - The level meter runs only while the popover is mounted
 *     (``enabled === true``). When the popover closes, we tear down
 *     the AudioContext + MediaStream so the mic indicator goes off
 *     and we don't drain battery.
 *   - ``deviceId === "default"`` is the browser's system-default
 *     pick; we keep it as the first entry so the picker has a "let
 *     the OS choose" option even when multiple physical mics exist.
 *
 * The chosen ``deviceId`` is routed end-to-end: the dictation hook threads
 * it into ``getUserMedia({audio:{deviceId:{exact}}})`` and voice mode passes
 * it to LiveKit's ``setMicrophoneEnabled({deviceId})`` — so MediaRecorder /
 * LiveKit capture from the picked device, not the system default.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface AudioDevice {
  /** ``MediaDeviceInfo.deviceId``. ``"default"`` for the OS default. */
  deviceId: string;
  /** Human-readable label — empty string when permission has never
   *  been granted; the popover falls back to "Microphone 1, 2, …" in
   *  that case. */
  label: string;
}

interface UseAudioDevicesParams {
  /** Mount/unmount the level-meter stream. ``true`` only when the
   *  popover is open so the mic indicator goes away when it closes. */
  enabled: boolean;
  /** The currently chosen ``deviceId`` (or ``undefined`` for default).
   *  When this changes the meter retargets to the new device. */
  selectedDeviceId?: string;
}

interface UseAudioDevices {
  /** Available ``audioinput`` devices. Empty until first ``refresh()``. */
  devices: AudioDevice[];
  /** RMS volume in [0, 1]. Updated ~30× / second while enabled. */
  level: number;
  /** Re-enumerate devices. Triggers a one-time permission prompt if
   *  the page has never held mic permission, so labels populate. */
  refresh: () => Promise<void>;
  /** True when the page has held mic permission this session. The
   *  picker uses this to decide whether to show real labels or the
   *  "Microphone 1, 2, …" fallbacks. */
  hasPermission: boolean;
}

export function useAudioDevices({
  enabled,
  selectedDeviceId,
}: UseAudioDevicesParams): UseAudioDevices {
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [level, setLevel] = useState(0);
  const [hasPermission, setHasPermission] = useState(false);

  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);

  // Re-enumerate. Browsers reveal labels only after permission has
  // been granted at least once on this origin, so we trigger a
  // throwaway getUserMedia before listing.
  const refresh = useCallback(async () => {
    try {
      // Throwaway capture — release immediately. Labels populate.
      const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
      probe.getTracks().forEach((t) => t.stop());
      setHasPermission(true);
    } catch {
      // Permission denied. We still call enumerateDevices so the
      // picker can show fallback ``Microphone 1, 2…`` labels.
      setHasPermission(false);
    }
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      const inputs = all
        .filter((d) => d.kind === "audioinput")
        .map((d, i) => ({
          deviceId: d.deviceId || `audio-input-${i}`,
          label: d.label || `Microphone ${i + 1}`,
        }));
      setDevices(inputs);
    } catch {
      // enumerateDevices() fails closed in some embedded webviews;
      // leave devices empty rather than throw.
      setDevices([]);
    }
  }, []);

  // Mount / tear down the level-meter pipeline. We rebuild on
  // selectedDeviceId change so the meter follows the picker.
  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;

    (async () => {
      try {
        const constraints: MediaStreamConstraints = {
          audio: selectedDeviceId
            ? { deviceId: { exact: selectedDeviceId } }
            : true,
        };
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        const Ctx =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext: typeof AudioContext })
            .webkitAudioContext;
        const ctx = new Ctx();
        const src = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        analyser.smoothingTimeConstant = 0.6;
        src.connect(analyser);

        streamRef.current = stream;
        ctxRef.current = ctx;
        analyserRef.current = analyser;

        const buf = new Uint8Array(analyser.fftSize);
        const tick = () => {
          if (!analyserRef.current) return;
          analyserRef.current.getByteTimeDomainData(buf);
          // Compute RMS centred on 128 (silence sample). Normalise
          // to [0, 1] by dividing by 128. Multiplied by 1.6 because
          // typical conversational speech only reaches ~0.4 RMS on
          // this scale; the boost gives the meter a usable range
          // without it looking pinned at the bottom for normal voices.
          let sum = 0;
          for (let i = 0; i < buf.length; i++) {
            const v = (buf[i] - 128) / 128;
            sum += v * v;
          }
          const rms = Math.sqrt(sum / buf.length);
          setLevel(Math.min(1, rms * 1.6));
          rafRef.current = requestAnimationFrame(tick);
        };
        rafRef.current = requestAnimationFrame(tick);
      } catch {
        // Permission denied or device gone — leave level at 0.
        setLevel(0);
      }
    })();

    return () => {
      cancelled = true;
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      analyserRef.current?.disconnect();
      analyserRef.current = null;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      // Closing the context is async; fire-and-forget.
      ctxRef.current?.close().catch(() => {});
      ctxRef.current = null;
      setLevel(0);
    };
  }, [enabled, selectedDeviceId]);

  return { devices, level, refresh, hasPermission };
}
