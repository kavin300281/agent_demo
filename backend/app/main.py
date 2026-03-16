import asyncio
import base64
import json
import os
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai.types import Blob, Content, Part
from pydantic import BaseModel

from .live_agent.agent import root_agent

load_dotenv()

APP_NAME = "gemini_live_fastapi_adk"
MODEL_NAME = os.getenv("DEMO_AGENT_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")

app = FastAPI(title="ADK Gemini Live Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_service = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=session_service)


class HealthResponse(BaseModel):
    status: str
    backend: str
    model: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", backend="adk", model=MODEL_NAME)


def _b64_to_bytes(value: str) -> bytes:
    return base64.b64decode(value.encode("utf-8"))


def _bytes_to_b64(value: bytes) -> str:
    return base64.b64encode(value).decode("utf-8")


def _as_base64(value: Any) -> str | None:
    if isinstance(value, bytes):
      return _bytes_to_b64(value)
    if isinstance(value, str):
      try:
        base64.b64decode(value, validate=True)
        return value
      except Exception:
        try:
          return _bytes_to_b64(value.encode("utf-8"))
        except Exception:
          return None
    return None


async def _start_live_session(user_id: str, use_audio: bool):
    session_id = f"session_{uuid.uuid4().hex}"
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    live_request_queue = LiveRequestQueue()
    config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO" if use_audio else "TEXT"],
        output_audio_transcription={} if use_audio else None,
    )

    live_events = runner.run_live(
        user_id=user_id,
        session_id=session_id,
        live_request_queue=live_request_queue,
        run_config=config,
    )
    return live_request_queue, live_events


async def _handle_client_event(live_request_queue: LiveRequestQueue, raw: str) -> None:
    data = json.loads(raw)
    event_type = data.get("type")

    if event_type == "text":
        text = (data.get("text") or "").strip()
        if text:
            live_request_queue.send_content(
                content=Content(role="user", parts=[Part.from_text(text=text)]),
                turn_complete=True,
            )
        return

    if event_type == "audio":
        payload = data.get("data")
        if payload:
            mime_type = data.get("mimeType", "audio/pcm;rate=16000")
            live_request_queue.send_realtime(
                Blob(data=_b64_to_bytes(payload), mime_type=mime_type)
            )
        return

    if event_type == "image":
        payload = data.get("data")
        if payload:
            mime_type = data.get("mimeType", "image/jpeg")
            live_request_queue.send_realtime(
                Blob(data=_b64_to_bytes(payload), mime_type=mime_type)
            )
        return

    if event_type in {"audio_end", "interrupt"}:
        # Optional control events. Supported as no-op for client compatibility.
        return

    raise ValueError(f"Unsupported client event type: {event_type}")


def _extract_text(payload: dict[str, Any]) -> str:
    texts: list[str] = []
    content = payload.get("content")
    if isinstance(content, dict):
        parts = content.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str) and text:
                        texts.append(text)
    output_transcription = payload.get("output_transcription")
    if isinstance(output_transcription, dict):
        text = output_transcription.get("text")
        if isinstance(text, str) and text:
            texts.append(text)
    return " ".join(texts).strip()


def _serialize_server_event(event: Any) -> dict[str, Any]:
    payload = event.model_dump(mode="python", exclude_none=True, warnings=False) if hasattr(event, "model_dump") else {}
    text = _extract_text(payload)
    audio_chunks: list[dict[str, str]] = []

    content = payload.get("content")
    if isinstance(content, dict):
        parts = content.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict):
                    continue
                inline_data = part.get("inline_data")
                if isinstance(inline_data, dict):
                    data = inline_data.get("data")
                    mime_type = inline_data.get("mime_type")
                    normalized_data = _as_base64(data)
                    if normalized_data and isinstance(mime_type, str):
                        audio_chunks.append({"mimeType": mime_type, "data": normalized_data})

    return {
        "type": "gemini_event",
        "text": text,
        "turnComplete": bool(payload.get("turn_complete")),
        "interrupted": bool(payload.get("interrupted")),
        "audioChunks": audio_chunks,
    }


@app.websocket("/ws/live")
async def live_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    user_id = websocket.query_params.get("userId", "local-dev")
    use_audio = websocket.query_params.get("audio", "true").lower() == "true"

    live_request_queue, live_events = await _start_live_session(user_id=user_id, use_audio=use_audio)

    try:
        async def client_to_adk() -> None:
            while True:
                raw = await websocket.receive_text()
                await _handle_client_event(live_request_queue, raw)

        async def adk_to_client() -> None:
            async for event in live_events:
                await websocket.send_text(json.dumps(_serialize_server_event(event)))

        tasks = {
            asyncio.create_task(client_to_adk()),
            asyncio.create_task(adk_to_client()),
        }

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in pending:
            task.cancel()
        for task in done:
            err = task.exception()
            if err:
                try:
                    await websocket.send_text(json.dumps({
                        "type": "backend_error",
                        "message": str(err),
                    }))
                except Exception:
                    pass
                return
    except WebSocketDisconnect:
        return
    finally:
        live_request_queue.close()
