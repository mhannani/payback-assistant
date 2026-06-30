"""Voice dictation — streaming Deepgram proxy.

A bidirectional pipeline behind the widget's mic. The browser ships Opus audio frames over a
WebSocket; this backend opens a sibling WebSocket to Deepgram with ``interim_results=true`` and
streams transcript events back to the browser as JSON frames. The Deepgram key never leaves the
server (the only reason a backend proxy exists rather than browser-direct).

Frame format (server → client)::

  {"type":"ready"}                                   backend connected to Deepgram, send audio now
  {"type":"transcript","text":"...","is_final":bool} interim (grows word-by-word) / final utterance
  {"type":"closed","reason":"user|silence|cap|error","charged_seconds":N}   always the last frame

Frame format (client → server): binary Opus-in-WebM/Ogg chunks (forwarded to Deepgram undecoded),
and a ``{"type":"close"}`` text frame requesting a clean stop (we flush Deepgram, then close).

Hard limits (defense against a runaway client): a 60 s wallclock ceiling, a 64 kB cap per binary
frame (Opus@96kbps/250 ms is ~3 kB), and a 4 s no-speech auto-close.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import websockets
from fastapi import WebSocket, WebSocketDisconnect, status

from app.config import get_settings

logger = logging.getLogger(__name__)


# ── Tunable limits (module-level so tests can monkey-patch) ─────────────────

#: Hard wallclock ceiling per dictation session. Anything longer is almost certainly not real
#: dictation. With billing stripped, this is the primary cost guard on the Deepgram spend.
MAX_SESSION_SECONDS: int = 60

#: Max size for a single binary audio frame. Opus@96kbps at the client's 250 ms timeslice is ~3 kB.
MAX_AUDIO_FRAME_BYTES: int = 64 * 1024

#: How often (seconds) the loop checks the session cap / no-speech timeout.
_CAP_CHECK_INTERVAL: float = 0.25

#: Auto-close if no Deepgram ``SpeechStarted`` arrives within this long of ``ready`` — so a mic
#: opened but never spoken into returns to idle instead of waiting out the full 60 s ceiling.
NO_SPEECH_TIMEOUT_SECONDS: float = 4.0

_DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


# ── Close reasons surfaced to the client (plain strings, JSON-friendly) ─────

CLOSE_REASON_USER = "user"  # client sent {"type":"close"}
CLOSE_REASON_SILENCE = "silence"  # Deepgram fired speech_final / UtteranceEnd → autocommit
CLOSE_REASON_CAP = "cap"  # hit MAX_SESSION_SECONDS
CLOSE_REASON_ERROR = "error"  # backend / Deepgram error
CLOSE_REASON_CLIENT_GONE = "client_gone"  # WS disconnect from the browser


@dataclass
class _StreamLimits:
    """Effective ceilings for this dictation session."""

    session_ceiling_seconds: int
    budget_remaining_seconds: int


async def run_dictation_stream(websocket: WebSocket, *, language: str = "en") -> None:
    """Pump one dictation session end-to-end.

    Precondition: ``websocket`` is already accepted by the caller. This is a single-tenant demo, so
    there is no per-org budget/subscription gate — the only ceiling is the absolute 60 s cap. The
    function exits when dictation ends for any reason (user close, silence auto-commit, cap, error)
    and closes the WS itself so the close frame carries the reason; the caller must not close again.
    """
    s = get_settings()

    # Pre-flight: STT configured. Absent key → a clear close frame, so the rest of the app runs
    # without Deepgram (the mic just won't work).
    if not s.deepgram_api_key:
        logger.error("dictate_stream: DEEPGRAM_API_KEY missing")
        await _close_with(
            websocket,
            CLOSE_REASON_ERROR,
            0,
            extra={"message": "Voice typing isn't set up on this server yet."},
        )
        return

    # No billing — the only ceiling is the absolute dictation cap.
    limits = _StreamLimits(
        session_ceiling_seconds=MAX_SESSION_SECONDS,
        budget_remaining_seconds=MAX_SESSION_SECONDS,
    )

    # ``interim_results`` is the whole point — without it Deepgram waits until utterance_end before
    # emitting anything; we want word-by-word feedback in the composer.
    deepgram_params: dict[str, str] = {
        "model": s.deepgram_model,
        "interim_results": "true",
        "smart_format": "true",
        "punctuate": "true",
        "endpointing": "1500",  # 1.5 s of silence → utterance_end (auto-commit)
        "vad_events": "true",
        "encoding": "opus",
    }
    if language:
        deepgram_params["language"] = language

    deepgram_url = f"{_DEEPGRAM_WS_URL}?{urlencode(deepgram_params)}"
    deepgram_headers = {"Authorization": f"Token {s.deepgram_api_key}"}

    logger.info("dictate_stream_open language=%s ceiling=%ds", language, limits.session_ceiling_seconds)
    started_at = time.perf_counter()

    try:
        async with websockets.connect(
            deepgram_url,
            additional_headers=deepgram_headers,
            max_size=2**20,  # 1 MB
            ping_interval=10,
            ping_timeout=10,
        ) as dg_ws:
            # Tell the client we're ready BEFORE it streams audio — otherwise the first chunks land
            # before Deepgram is reachable and get dropped.
            await websocket.send_json({"type": "ready"})
            close_reason, elapsed = await _pump(
                browser_ws=websocket, deepgram_ws=dg_ws, limits=limits, started_at=started_at
            )
    except websockets.exceptions.InvalidStatusCode as exc:
        logger.error("dictate_stream_deepgram_handshake_failed status=%s", exc.status_code)
        await _close_with(
            websocket, CLOSE_REASON_ERROR, 0, extra={"message": "STT service rejected the stream"}
        )
        return
    except (websockets.exceptions.WebSocketException, OSError) as exc:
        logger.error("dictate_stream_deepgram_network_error error=%s", exc)
        await _close_with(
            websocket, CLOSE_REASON_ERROR, 0, extra={"message": "STT service unreachable"}
        )
        return

    # ``elapsed`` is wallclock from the "ready" frame; clamp at the ceiling (the cap loop should have
    # closed us by then — defensive only).
    charged = min(limits.session_ceiling_seconds, max(1, int(elapsed)))
    logger.info("dictate_stream_closed reason=%s elapsed=%.2fs", close_reason, elapsed)
    await _close_with(websocket, close_reason, charged)


async def _pump(
    *,
    browser_ws: WebSocket,
    deepgram_ws: websockets.WebSocketClientProtocol,
    limits: _StreamLimits,
    started_at: float,
) -> tuple[str, float]:
    """Run the bidirectional pump until something ends it.

    Three concurrent tasks: ``browser_to_deepgram`` (forward audio up), ``deepgram_to_browser``
    (forward transcripts down), ``cap_watcher`` (close on the session ceiling / no-speech timeout).
    The first to finish wins and determines the close reason; the others are cancelled.
    """
    close_reason_holder: dict[str, str] = {"reason": CLOSE_REASON_ERROR}
    # Flipped True the first time Deepgram emits ``SpeechStarted``; the cap watcher keys the
    # no-speech timeout off it.
    speech_started_holder: dict[str, bool] = {"started": False}

    async def browser_to_deepgram() -> None:
        # A ``ConnectionClosed`` on the upstream send is a normal teardown race after a sibling
        # coroutine flushed Deepgram (silence/cap) — return quietly so its reason is preserved
        # rather than clobbered to ERROR.
        try:
            while True:
                msg = await browser_ws.receive()
                msg_type = msg.get("type")
                if msg_type == "websocket.disconnect":
                    close_reason_holder["reason"] = CLOSE_REASON_CLIENT_GONE
                    return
                if msg_type != "websocket.receive":
                    continue

                # Binary frame → audio chunk → forward to Deepgram.
                data = msg.get("bytes")
                if data is not None:
                    if len(data) > MAX_AUDIO_FRAME_BYTES:
                        logger.warning("dictate_stream_oversized_frame bytes=%d", len(data))
                        close_reason_holder["reason"] = CLOSE_REASON_ERROR
                        return
                    await deepgram_ws.send(data)
                    continue

                # Text frame → control message.
                text = msg.get("text")
                if text is None:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    logger.warning("dictate_stream_bad_control_frame")
                    continue
                if payload.get("type") == "close":
                    # Flush Deepgram but don't return yet — we want the final transcript it's about
                    # to emit; ``deepgram_to_browser`` exits when the upstream closes.
                    await deepgram_ws.send(json.dumps({"type": "CloseStream"}))
                    close_reason_holder["reason"] = CLOSE_REASON_USER
        except WebSocketDisconnect:
            close_reason_holder["reason"] = CLOSE_REASON_CLIENT_GONE
        except websockets.exceptions.ConnectionClosed:
            return

    async def deepgram_to_browser() -> None:
        try:
            async for raw in deepgram_ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")
                if event_type == "Results":
                    transcript = (
                        event.get("channel", {}).get("alternatives", [{}])[0].get("transcript", "")
                    )
                    is_final = bool(event.get("is_final"))
                    speech_final = bool(event.get("speech_final"))

                    # Forward only non-empty text — but check ``speech_final`` independently: an
                    # empty transcript with speech_final=true is Deepgram's "utterance complete"
                    # marker (the auto-commit signal), not noise.
                    if transcript:
                        await browser_ws.send_json(
                            {"type": "transcript", "text": transcript, "is_final": is_final}
                        )
                    if speech_final:
                        if close_reason_holder["reason"] == CLOSE_REASON_ERROR:
                            close_reason_holder["reason"] = CLOSE_REASON_SILENCE
                        await deepgram_ws.send(json.dumps({"type": "CloseStream"}))
                elif event_type == "UtteranceEnd":
                    # Backup auto-commit if we somehow missed speech_final.
                    if close_reason_holder["reason"] == CLOSE_REASON_ERROR:
                        close_reason_holder["reason"] = CLOSE_REASON_SILENCE
                    await deepgram_ws.send(json.dumps({"type": "CloseStream"}))
                elif event_type == "SpeechStarted":
                    speech_started_holder["started"] = True
        except websockets.exceptions.ConnectionClosed:
            return

    async def cap_watcher() -> None:
        ceiling = limits.session_ceiling_seconds
        while True:
            await asyncio.sleep(_CAP_CHECK_INTERVAL)
            elapsed = time.perf_counter() - started_at

            # No-speech timeout: mic opened but never spoken into → close cleanly. Dormant once
            # SpeechStarted fires (then the speech_final / UtteranceEnd path handles auto-commit).
            if not speech_started_holder["started"] and elapsed >= NO_SPEECH_TIMEOUT_SECONDS:
                close_reason_holder["reason"] = CLOSE_REASON_SILENCE
                await deepgram_ws.send(json.dumps({"type": "CloseStream"}))
                return

            if elapsed >= ceiling:
                close_reason_holder["reason"] = CLOSE_REASON_CAP
                await deepgram_ws.send(json.dumps({"type": "CloseStream"}))
                return

    tasks = [
        asyncio.create_task(browser_to_deepgram(), name="b2dg"),
        asyncio.create_task(deepgram_to_browser(), name="dg2b"),
        asyncio.create_task(cap_watcher(), name="cap"),
    ]

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        # Only an unhandled exception with no sibling reason set leaves the default ERROR.
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, asyncio.CancelledError):
                logger.warning("dictate_stream_pump_exception task=%s error=%s", task.get_name(), exc)
    finally:
        elapsed = time.perf_counter() - started_at

    return close_reason_holder["reason"], elapsed


async def _close_with(
    websocket: WebSocket, reason: str, charged_seconds: int, extra: Optional[dict] = None
) -> None:
    """Send a final ``closed`` frame then close the WS. Best-effort — swallow if already gone."""
    payload: dict = {"type": "closed", "reason": reason, "charged_seconds": charged_seconds}
    if extra:
        payload.update(extra)
    try:
        await websocket.send_json(payload)
    except Exception:
        pass
    try:
        await websocket.close(code=status.WS_1000_NORMAL_CLOSURE, reason=reason[:120])
    except Exception:
        pass
