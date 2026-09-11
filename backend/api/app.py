"""HTTP/WebSocket boundary for the local single-session MVP."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.conversation.service import process_turn
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


def create_app(processor=process_turn) -> FastAPI:
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
