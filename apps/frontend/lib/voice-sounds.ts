/**
 * Voice chimes — synthesised via the Web Audio API at runtime.
 *
 * Shared across every voice surface (copilot, demo, widget) and both voice
 * modes per surface:
 *
 *   * Dictation (``useVoiceInput``) — short MediaRecorder + backend Deepgram
 *     round-trip. Plays start/stop/cancel on the recording lifecycle
 *     transitions.
 *   * Voice mode (``useVoiceMode``) — full-duplex LiveKit call. Plays start
 *     when the room+mic are armed; stop on a clean hangup; cancel on
 *     permission/connection/budget failures.
 *
 * Why synthesised, not MP3 files:
 *
 *   - Zero bytes shipped, zero CDN traffic, nothing to license.
 *   - Deterministic across browsers — no codec quirks, no decode stutter, no
 *     "first play silent because the file is still loading".
 *   - Owned end-to-end — tweaking pitch / length / envelope is a code change,
 *     not an audio-editor round-trip.
 *   - Matches what claude.ai, Slack, Linear, Notion, iOS Voice Memos do for
 *     their own UI affordance chimes (content audio like voiceover is still
 *     files; affordance audio is always synth).
 *
 * Three sounds exported as named functions:
 *
 *   playVoiceStart()  — short ascending two-note pip (E5 → A5) "listening on"
 *   playVoiceStop()   — mirror descending pip (A5 → E5) "listening off,
 *                       transcript committed"
 *   playVoiceCancel() — single soft thunk (A3, fast decay) "aborted, nothing
 *                       kept"
 *
 * All three are fire-and-forget. Failures (no AudioContext, suspended state
 * without a user gesture, etc.) are swallowed — UX should never break because
 * the chime didn't play.
 *
 * Call-site rule: chimes are played from inside the relevant voice HOOK at
 * lifecycle transition points, NEVER from component render code. The hook owns
 * the lifecycle, so the hook owns the audio feedback.
 */

/**
 * Single lazily-constructed AudioContext shared across every chime.
 * Browsers require a user gesture to construct an AudioContext; the mic click
 * that triggers the first chime IS that gesture, so lazy construction is safe.
 * Re-use across chimes avoids the "20 ms of silence on first play after each
 * idle period" most browsers exhibit when an AudioContext is freshly created.
 */
let _ctx: AudioContext | null = null;

function getCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (_ctx) return _ctx;
  const Ctor =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext })
      .webkitAudioContext;
  if (!Ctor) return null;
  try {
    _ctx = new Ctor();
  } catch {
    _ctx = null;
  }
  return _ctx;
}

/**
 * One pip — sine oscillator at ``freq`` Hz, gated by an exponential gain
 * envelope so the start and end of the note are clickless. ``startAt`` and
 * ``duration`` are in seconds relative to ``ctx.currentTime`` so multi-note
 * sequences stay perfectly sample-accurate (no setTimeout drift).
 *
 * ``peakGain`` keeps the chime quiet — 0.08 lands in the "noticeable but never
 * startling" band claude.ai / iOS Voice Memos use. Anything louder and the
 * chime competes with the user's own voice on the next inhale.
 */
function playTone(
  ctx: AudioContext,
  freq: number,
  startAt: number,
  duration: number,
  peakGain = 0.08,
  type: OscillatorType = "sine",
): void {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, startAt);

  // Envelope: 6 ms attack, exponential decay to silence by end. Exponential
  // decay sounds natural (matches how acoustic instruments fade); linear decay
  // sounds synthetic.
  gain.gain.setValueAtTime(0.0001, startAt);
  gain.gain.exponentialRampToValueAtTime(peakGain, startAt + 0.006);
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);

  osc.connect(gain).connect(ctx.destination);
  osc.start(startAt);
  osc.stop(startAt + duration + 0.02);
}

/**
 * Some browsers (notably Safari) suspend the AudioContext between
 * gesture-triggered runs. Resume on every play; safe no-op when already
 * running.
 */
function ensureRunning(ctx: AudioContext): void {
  if (ctx.state === "suspended") {
    void ctx.resume().catch(() => undefined);
  }
}

/**
 * Played when a voice surface transitions to the actively-listening state —
 * the mic is genuinely armed (Deepgram ready for dictation, LiveKit room
 * joined + mic enabled for voice mode). NOT played on click — that would lie
 * about state on a failed start.
 *
 * Two-note ascending pip: E5 → A5, ~80 ms total. The ascending shape signals
 * "starting" in every cultural musical context.
 */
export function playVoiceStart(): void {
  const ctx = getCtx();
  if (!ctx) return;
  ensureRunning(ctx);
  const t0 = ctx.currentTime;
  playTone(ctx, 659.25, t0, 0.05); // E5
  playTone(ctx, 880.0, t0 + 0.05, 0.06); // A5
}

/**
 * Played on a clean close — dictation auto-commit / user-Done / cap reached;
 * voice mode hangup by either side without an error. Mirror of start:
 * descending A5 → E5 signals "stopping cleanly".
 */
export function playVoiceStop(): void {
  const ctx = getCtx();
  if (!ctx) return;
  ensureRunning(ctx);
  const t0 = ctx.currentTime;
  playTone(ctx, 880.0, t0, 0.05); // A5
  playTone(ctx, 659.25, t0 + 0.05, 0.06); // E5
}

/**
 * Played when a session aborts without a useful result — user pressed Cancel,
 * mic denied, network failure, budget exhausted, client disconnected. Single
 * low pip — "aborted, nothing kept".
 *
 * Different shape from stop (one note vs two, low vs high, triangle vs sine)
 * so the user can audibly distinguish "your text was committed" from "your
 * text was discarded".
 */
export function playVoiceCancel(): void {
  const ctx = getCtx();
  if (!ctx) return;
  ensureRunning(ctx);
  const t0 = ctx.currentTime;
  // Slightly lower gain than start/stop — cancel should feel muted, not
  // assertive.
  playTone(ctx, 220.0, t0, 0.09, 0.06, "triangle"); // A3
}
