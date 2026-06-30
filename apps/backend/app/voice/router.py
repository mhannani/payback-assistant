"""Voice WebSocket routes.

A single endpoint backs the widget's mic: ``/voice/dictate-stream`` proxies browser audio to
Deepgram and streams transcripts back (see :mod:`app.voice.dictation`). Single-tenant demo — no
auth token, no widget key, no DB; the handler just accepts the socket and runs the pump.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket

from app.voice.dictation import run_dictation_stream

router = APIRouter(prefix="/voice", tags=["voice"])


@router.websocket("/dictate-stream")
async def dictate_stream(websocket: WebSocket, language: str = Query("multi")) -> None:
    """Accept the browser WebSocket and run a Deepgram dictation session.

    ``language`` is forwarded to Deepgram. Default ``"multi"`` so nova-3 transcribes German AND
    English (and code-switching) in one stream — the streaming-supported way to handle a bilingual
    speaker (Deepgram's ``detect_language`` is pre-recorded-only). A specific BCP-47 code (``de`` /
    ``en``) still works if a caller wants to pin one language.
    """
    await websocket.accept()
    await run_dictation_stream(websocket, language=language)
