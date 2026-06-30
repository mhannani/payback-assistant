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
async def dictate_stream(websocket: WebSocket, language: str = Query("en")) -> None:
    """Accept the browser WebSocket and run a Deepgram dictation session.

    ``language`` is a BCP-47 hint (``en`` / ``de``); the dictation pump forwards it to Deepgram.
    """
    await websocket.accept()
    await run_dictation_stream(websocket, language=language)
