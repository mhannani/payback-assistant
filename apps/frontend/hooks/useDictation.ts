"use client";

import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { playVoiceCancel, playVoiceStart, playVoiceStop } from "@/lib/voice-sounds";

/** Where the dictation WebSocket lives — derived from the API base (same host, ws/wss scheme). */
function buildWsUrl(language: string): string {
  const base = process.env.NEXT_PUBLIC_API_BASE ?? "";
  const httpUrl = base || (typeof window !== "undefined" ? window.location.origin : "");
  const url = new URL(httpUrl);
  const proto = url.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${url.host}/voice/dictate-stream?language=${encodeURIComponent(language)}`;
}

/** Pick the first MediaRecorder MIME the browser supports (Opus preferred — what Deepgram wants). */
function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  for (const t of ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/webm", "audio/mp4"]) {
    try {
      if (MediaRecorder.isTypeSupported(t)) return t;
    } catch {
      /* ignore */
    }
  }
  return "";
}

export type DictationState = "idle" | "connecting" | "listening" | "error";

interface ServerFrame {
  type: "ready" | "transcript" | "closed";
  text?: string;
  is_final?: boolean;
  reason?: string;
  message?: string;
}

/** Streaming voice dictation over the backend Deepgram proxy.
 *
 * Faithful port of the Empfio mechanism: open a WebSocket, wait for ``ready``, then stream
 * MediaRecorder Opus chunks (250 ms timeslices) up; the server streams transcripts back, which we
 * pass to ``onTranscript`` (interim grows word-by-word; final commits). The backend auto-commits on
 * 1.5 s of silence and hard-caps the session at 60 s. ``stop`` requests a clean flush; ``cancel``
 * drops the socket. ``deviceId`` (from the mic picker) is threaded into getUserMedia so capture
 * follows the chosen device. Lifecycle chimes play on listen/commit/cancel. */
export function useDictation(onTranscript: (text: string) => void, deviceId?: string) {
  const [state, setState] = useState<DictationState>("idle");
  // Exposed for the recording UI: the live mic stream (waveform) + the latest interim text.
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [interim, setInterim] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  // The running transcript: finals are concatenated; an interim is appended for live display only.
  const finalTextRef = useRef("");

  const teardown = useCallback(() => {
    try {
      recorderRef.current?.stop();
    } catch {
      /* already stopped */
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    recorderRef.current = null;
    streamRef.current = null;
    setStream(null);
    setInterim("");
    wsRef.current = null;
  }, []);

  const handleFrame = useCallback(
    (raw: string) => {
      let frame: ServerFrame;
      try {
        frame = JSON.parse(raw);
      } catch {
        return;
      }
      if (frame.type === "transcript") {
        const text = frame.text ?? "";
        const combined = finalTextRef.current ? `${finalTextRef.current} ${text}`.trim() : text;
        if (frame.is_final) finalTextRef.current = combined;
        setInterim(combined); // live text shown in the recording takeover
        onTranscript(combined); // also fills the composer draft so it's there on Done
      } else if (frame.type === "closed") {
        // A clean close (user/silence/cap) committed the text → stop chime; an error → cancel chime
        // and surface the server's reason (e.g. "STT not configured") so the mic isn't silently dead.
        if (frame.reason === "error") {
          setState("error");
          toast.error(frame.message || "Sprachsteuerung ist gerade nicht verfügbar.");
          playVoiceCancel();
        } else {
          setState("idle");
          playVoiceStop();
        }
        teardown();
      }
    },
    [onTranscript, teardown],
  );

  const start = useCallback(async () => {
    if (state !== "idle") return;
    finalTextRef.current = "";
    setState("connecting");

    let micStream: MediaStream;
    try {
      // Capture from the picked device (if any), with the standard speech constraints.
      const audio: MediaTrackConstraints = {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      };
      if (deviceId) audio.deviceId = { exact: deviceId };
      micStream = await navigator.mediaDevices.getUserMedia({ audio });
    } catch {
      setState("error");
      toast.error("Mikrofonzugriff wurde blockiert. Bitte im Browser erlauben, um die Sprachsteuerung zu nutzen.");
      playVoiceCancel();
      return;
    }
    streamRef.current = micStream;
    setStream(micStream); // expose to the recording UI (waveform)

    const mimeType = pickMimeType();
    let recorder: MediaRecorder;
    try {
      recorder = mimeType
        ? new MediaRecorder(micStream, { mimeType, audioBitsPerSecond: 96_000 })
        : new MediaRecorder(micStream);
    } catch {
      teardown();
      setState("error");
      return;
    }
    recorderRef.current = recorder;

    // "multi" → Deepgram nova-3 transcribes German AND English (and code-switching) in one stream.
    // Deepgram's detect_language is pre-recorded-only; language=multi is the streaming-supported way
    // to handle a bilingual speaker (see Deepgram "Multilingual Code-Switching").
    const ws = new WebSocket(buildWsUrl("multi"));
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    recorder.ondataavailable = (e) => {
      if (e.data?.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
        e.data.arrayBuffer().then((buf) => {
          try {
            wsRef.current?.send(buf);
          } catch {
            /* socket closed mid-flight */
          }
        });
      }
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") return;
      // The recorder only starts after the server says it's ready (else the first chunks drop).
      let frame: ServerFrame;
      try {
        frame = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (frame.type === "ready") {
        try {
          recorder.start(250);
          setState("listening");
          playVoiceStart(); // chime only once the mic is genuinely armed, not on click
        } catch {
          setState("error");
          teardown();
        }
        return;
      }
      handleFrame(ev.data);
    };
    ws.onerror = () => setState("error");
    ws.onclose = () => {
      setState((s) => (s === "error" ? s : "idle"));
      teardown();
    };
  }, [state, deviceId, handleFrame, teardown]);

  /** Clean stop: ask the server to flush the final transcript, then it closes us. */
  const stop = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: "close" }));
      } catch {
        /* ignore */
      }
    }
    try {
      recorderRef.current?.stop();
    } catch {
      /* ignore */
    }
  }, []);

  /** Drop everything without committing (user cancelled). */
  const cancel = useCallback(() => {
    try {
      wsRef.current?.close();
    } catch {
      /* ignore */
    }
    teardown();
    setState("idle");
    playVoiceCancel();
  }, [teardown]);

  return {
    state,
    stream,
    interim,
    start,
    stop,
    cancel,
    recording: state === "listening" || state === "connecting",
  };
}
