"use client";

/**
 * Live, smoothly scrolling RMS waveform for the recording card.
 *
 * Reads amplitude from an ``AnalyserNode`` attached to the SAME ``MediaStream``
 * the recorder is capturing (no second ``getUserMedia`` — that would open a
 * second OS mic indicator).
 *
 * Two cooperating tickers produce the visual:
 *
 *   1. **Sample ticker** — every ``SAMPLE_INTERVAL_MS``: read one RMS
 *      amplitude, rotate the history buffer (oldest sample falls off the left,
 *      new sample appended on the right). Discrete, low-frequency event.
 *
 *   2. **Scroll ticker** — every ``requestAnimationFrame``: write a
 *      ``translateX`` on the bar group based on the elapsed fraction of the
 *      current sample interval. The group drifts continuously from ``0`` to
 *      ``-SLOT_PX``; when a new sample lands, translateX resets to ``0`` AND
 *      the buffer rotates in the same frame, so there's no visual jump.
 *
 * The bar count is computed from the parent's actual pixel width via
 * ``ResizeObserver`` so individual bars stay at their natural 2 px width
 * regardless of composer width — no stretching, no "zoomed" look. Matches
 * claude.ai exactly: ~2 px bars, 2 px gaps, roughly one bar every 4 px.
 *
 * Silence is rendered as **circular dots**, not stubby rectangles. Each bar's
 * ``rx`` is set to half its width at the silence floor — the rect collapses to
 * a small disc. Bars above the floor render as pill-shaped rectangles.
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

interface LiveWaveformProps {
  stream: MediaStream | null;
  className?: string;
}

// FFT size on the analyser. 2048 is the smallest reliable for the speech band
// without adding noticeable latency.
const FFT_SIZE = 2048;

// Time between sample pushes (ms). Each tick shifts the history one slot left.
// 120 ms feels calm at typical bar counts; the single knob — raise for slower
// scroll, lower for faster.
const SAMPLE_INTERVAL_MS = 120;

// Visual bar geometry in PIXELS (not viewBox units) — the SVG renders at its
// natural size, not stretched. These match the claude.ai bar density.
const BAR_W = 2;
const BAR_GAP = 2;
const SLOT_PX = BAR_W + BAR_GAP;
const HEIGHT_PX = 32;

// Amplitude at or below this threshold renders as a square dot. Above renders
// as a pill rectangle of proportional height.
const SILENCE_FLOOR = 0.06;
const DOT_PX = 2;

export function LiveWaveform({ stream, className }: LiveWaveformProps) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const groupRef = useRef<SVGGElement | null>(null);
  // Bar count derived from the container's measured width. Starts at zero so
  // the first paint is a no-op and we only render bars once we know the width.
  const [barCount, setBarCount] = useState(0);

  // Sample buffer. One extra slot beyond the visible count holds the bar
  // currently scrolling off the left edge.
  const samplesRef = useRef<Float32Array>(new Float32Array(0));
  const barRefs = useRef<(SVGRectElement | null)[]>([]);

  // ── Measure the container width and derive bar count ─────────
  useLayoutEffect(() => {
    if (!wrapperRef.current) return;
    const el = wrapperRef.current;
    const update = (width: number) => {
      const next = Math.max(0, Math.floor(width / SLOT_PX));
      setBarCount((prev) => (prev === next ? prev : next));
    };
    update(el.clientWidth);
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        update(entry.contentRect.width);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Resize the sample buffer whenever the bar count changes. New slots default
  // to zero (silence) — they fill in naturally as audio rotates through.
  useEffect(() => {
    const slots = barCount + 1;
    const next = new Float32Array(slots);
    const prev = samplesRef.current;
    const copy = Math.min(prev.length, next.length);
    next.set(prev.subarray(prev.length - copy), next.length - copy);
    samplesRef.current = next;
  }, [barCount]);

  // ── Audio + scroll loop ──────────────────────────────────────
  useEffect(() => {
    if (!stream || barCount === 0) return;

    const AudioCtor: typeof AudioContext | undefined =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!AudioCtor) return;

    const ctx = new AudioCtor();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = FFT_SIZE;
    analyser.smoothingTimeConstant = 0.3;
    source.connect(analyser);

    const td = new Float32Array(analyser.fftSize);
    samplesRef.current.fill(0);

    let rafId = 0;
    let running = true;
    let lastSampleAt = performance.now();
    let pendingPeak = 0;

    const readAmplitude = (): number => {
      analyser.getFloatTimeDomainData(td);
      let sumSq = 0;
      for (let i = 0; i < td.length; i++) {
        sumSq += td[i] * td[i];
      }
      const rms = Math.sqrt(sumSq / td.length);
      // ×4 maps a normal speaking voice to ~70-80 % of the bar height without
      // saturating at 100 % on loud passages.
      return Math.min(1, rms * 4);
    };

    const writeBar = (i: number, amp: number): void => {
      const bar = barRefs.current[i];
      if (!bar) return;
      if (amp <= SILENCE_FLOOR) {
        const y = (HEIGHT_PX - DOT_PX) / 2;
        bar.setAttribute("height", DOT_PX.toFixed(2));
        bar.setAttribute("y", y.toFixed(2));
        bar.setAttribute("rx", (DOT_PX / 2).toFixed(2));
        return;
      }
      const h = amp * HEIGHT_PX;
      const y = (HEIGHT_PX - h) / 2;
      bar.setAttribute("height", h.toFixed(2));
      bar.setAttribute("y", y.toFixed(2));
      bar.setAttribute("rx", (BAR_W / 2).toFixed(2));
    };

    const tick = () => {
      if (!running) return;
      const now = performance.now();
      const a = readAmplitude();
      if (a > pendingPeak) pendingPeak = a;

      const elapsed = now - lastSampleAt;
      const progress = Math.min(1, elapsed / SAMPLE_INTERVAL_MS);

      if (elapsed >= SAMPLE_INTERVAL_MS) {
        const samples = samplesRef.current;
        for (let i = 0; i < samples.length - 1; i++) {
          samples[i] = samples[i + 1];
        }
        samples[samples.length - 1] = pendingPeak;
        pendingPeak = 0;
        lastSampleAt = now;
        for (let i = 0; i < samples.length; i++) {
          writeBar(i, samples[i]);
        }
        if (groupRef.current) {
          groupRef.current.setAttribute("transform", "translate(0, 0)");
        }
      } else {
        const dx = -(SLOT_PX * progress);
        if (groupRef.current) {
          groupRef.current.setAttribute(
            "transform",
            `translate(${dx.toFixed(3)}, 0)`,
          );
        }
        const samples = samplesRef.current;
        const lastIdx = samples.length - 1;
        const blended =
          samples[lastIdx] + (pendingPeak - samples[lastIdx]) * progress;
        writeBar(lastIdx, blended);
      }

      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);

    return () => {
      running = false;
      cancelAnimationFrame(rafId);
      try {
        source.disconnect();
      } catch {
        // ignore
      }
      void ctx.close();
    };
  }, [stream, barCount]);

  // The visible SVG occupies the row's full width; the bar group sits inside
  // an extra slot to the right so we have a bar to slide IN from on each
  // interval. Overflow-hidden clips the group's leftward drift off the left.
  const slots = barCount + 1;
  const svgWidth = slots * SLOT_PX;

  // Wrapper is ``relative`` so the SVG can position absolutely without
  // contributing to flex sizing. ``min-w-0`` lets the wrapper actually shrink
  // inside its flex parent — without it, the row's ``flex-1`` slot would size
  // from the SVG's intrinsic width and push the Cancel/Done buttons off-screen.
  return (
    <div
      ref={wrapperRef}
      className={cn("relative h-8 w-full min-w-0 overflow-hidden", className)}
      aria-hidden="true"
    >
      {barCount > 0 && (
        <svg
          width={svgWidth}
          height={HEIGHT_PX}
          viewBox={`0 0 ${svgWidth} ${HEIGHT_PX}`}
          className="absolute inset-0"
        >
          <g ref={groupRef}>
            {Array.from({ length: slots }).map((_, i) => (
              <rect
                key={i}
                ref={(node) => {
                  barRefs.current[i] = node;
                }}
                x={i * SLOT_PX}
                y={(HEIGHT_PX - DOT_PX) / 2}
                width={BAR_W}
                height={DOT_PX}
                rx={DOT_PX / 2}
                className="fill-foreground/65"
              />
            ))}
          </g>
        </svg>
      )}
    </div>
  );
}
