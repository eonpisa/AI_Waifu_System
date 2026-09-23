"""HTTP/WebSocket boundary for the local single-session MVP."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.conversation.service import process_turn
from backend.voice.stt import MAX_AUDIO_BYTES, transcribe_file
from .runtime import Runtime, TurnRejected
from .schemas import TurnInput


LOCAL_ORIGINS = {
    f"http://{host}:{port}" for host in ("127.0.0.1", "localhost") for port in (8000, 5173)
}


class LocalOriginMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in {"http", "websocket"}:
            headers = dict(scope.get("headers", []))
            origin = headers.get(b"origin")
            if origin is not None and origin.decode("latin-1") not in LOCAL_ORIGINS:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await JSONResponse({"error": "origin_forbidden"}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(processor=process_turn, transcriber=transcribe_file) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        app.state.runtime = Runtime(processor)
        try:
            yield
        finally:
            await app.state.runtime.close()

    app = FastAPI(title="AI Waifu Local API", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=sorted(LOCAL_ORIGINS),
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    app.add_middleware(LocalOriginMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        # FastAPI's default validation detail includes the supplied input.
        return JSONResponse({"error": "invalid_input"}, status_code=422)

    @app.exception_handler(TurnRejected)
    async def rejected(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=409)

    @app.get("/api/health")
    async def health():
        # Liveness only: this does not test Ollama/Gemini/SBV2/VTS readiness.
        return {"status": "ok", "scope": "api_only"}

    @app.get("/api/state")
    async def state(request: Request):
        return request.app.state.runtime.state()

    @app.post("/api/turn", status_code=202)
    async def turn(body: TurnInput, request: Request):
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            return JSONResponse({"error": "json_required"}, status_code=415)
        turn_id = request.app.state.runtime.submit(body.text)
        return {"turn_id": turn_id, "status": "accepted"}

    @app.post("/api/end")
    async def end(request: Request):
        return request.app.state.runtime.end()

    @app.post("/api/transcribe")
    async def transcribe(request: Request):
        mime = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        suffixes = {"audio/webm": ".webm", "audio/mp4": ".mp4",
                    "audio/ogg": ".ogg", "audio/wav": ".wav"}
        if mime not in suffixes:
            return JSONResponse({"error": "unsupported_audio"}, status_code=415)
        runtime = request.app.state.runtime

        async def work():
            try:
                data = bytearray()
                async with asyncio.timeout(15):
                    async for chunk in request.stream():
                        if len(data) + len(chunk) > MAX_AUDIO_BYTES:
                            return JSONResponse({"error": "audio_too_large"}, status_code=413)
                        data.extend(chunk)
                if not data:
                    return JSONResponse({"error": "audio_missing"}, status_code=422)

                def recognize():
                    # The worker owns the file until inference finishes, even
                    # when the HTTP client disconnects. Never log its path.
                    with TemporaryDirectory(prefix="ai-waifu-stt-") as folder:
                        audio = Path(folder) / ("recording" + suffixes[mime])
                        audio.write_bytes(data)
                        return transcriber(audio)

                result = await runtime.loop.run_in_executor(runtime.executor, recognize)
                allowed_errors = {"audio_missing", "audio_too_large", "audio_too_long",
                                  "model_not_configured", "model_missing", "dependency_missing",
                                  "transcription_failed", "no_speech"}
                if result.error:
                    code = result.error if result.error in allowed_errors else "transcription_failed"
                    return JSONResponse({"error": code}, status_code=422)
                if not isinstance(result.text, str) or not 1 <= len(result.text.strip()) <= 2000:
                    return JSONResponse({"error": "transcription_failed"}, status_code=422)
                return JSONResponse({"text": result.text.strip()}, headers={"Cache-Control": "no-store"})
            except Exception:
                return JSONResponse({"error": "transcription_failed"}, status_code=422)

        # Shield keeps the reservation and temporary-file ownership until the
        # blocking worker finishes; disconnect does not permit overlapping work.
        return await asyncio.shield(runtime.start_transcription(work))

    @app.websocket("/api/events")
    async def events(websocket: WebSocket):
        runtime = websocket.app.state.runtime
        try:
            queue = runtime.subscribe()
        except TurnRejected:
            await websocket.close(code=1013)
            return
        tasks = []
        try:
            await websocket.accept()

            async def sender():
                while True:
                    event = await queue.get()
                    if event is None:
                        await websocket.close(code=1013)
                        return
                    await websocket.send_json(event)

            async def receiver():
                # Receive only to detect disconnect, including an idle client.
                while (await websocket.receive())["type"] != "websocket.disconnect":
                    pass

            tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (WebSocketDisconnect, OSError):
            pass
        finally:
            runtime.unsubscribe(queue)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return app


app = create_app()
