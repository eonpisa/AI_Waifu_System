"""Model-free API contracts and actual worker/disconnect lifecycle tests."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import logging
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.api.app import create_app
from backend.__main__ import SafeConsoleFilter, run_api
from backend.api.runtime import Runtime, TurnRejected
from backend.conversation.service import TurnEvent, TurnResult
from backend.translation.translator import KoreanInputTranslation


def success(session, text, emit):
    emit(TurnEvent("stage_changed", {"stage": "generating"}))
    emit(TurnEvent("subtitle_ready", {"korean_subtitle": "수고했어요."}))
    return TurnResult("completed", japanese_reply="お疲れ様です。",
                      korean_subtitle="수고했어요.", audio_played=True)


def wait_idle(client):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        state = client.get("/api/state").json()
        if not state["busy"]:
            return state
        time.sleep(.005)
    raise AssertionError("worker did not finish")


class ApiTests(unittest.TestCase):
    def client(self, processor=success):
        return TestClient(create_app(processor), base_url="http://127.0.0.1:8000")

    @contextlib.contextmanager
    def blocking(self):
        started, release = threading.Event(), threading.Event()

        def processor(session, text, emit):
            started.set()
            if not release.wait(4):
                raise RuntimeError("test release timeout")
            return success(session, text, emit)

        # Release before TestClient lifespan teardown, including on assertion.
        with self.client(processor) as client:
            try:
                yield client, started, release
            finally:
                release.set()

    def test_liveness_and_initial_state_do_not_claim_service_readiness(self):
        with self.client() as client:
            self.assertEqual(client.get("/api/health").json(), {"status": "ok", "scope": "api_only"})
            state = client.get("/api/state").json()
            self.assertEqual(state["stage"], "idle")
            self.assertFalse(state["busy"])
            self.assertNotIn("messages", state)

    def test_websocket_initial_state_progress_subtitle_and_completion(self):
        with self.client() as client, client.websocket_connect("ws://127.0.0.1:8000/api/events") as ws:
            self.assertEqual(ws.receive_json()["type"], "state")
            response = client.post("/api/turn", json={"text": "안녕"})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["turn_id"], 1)
            events = [ws.receive_json() for _ in range(4)]
            self.assertEqual([e["type"] for e in events], [
                "stage_changed", "stage_changed", "subtitle_ready", "turn_finished",
            ])
            self.assertEqual([e["seq"] for e in events], [1, 2, 3, 4])
            self.assertTrue(all(e["turn_id"] == 1 and e["elapsed_ms"] >= 0 for e in events))
            self.assertEqual(events[-1]["data"]["result"]["status"], "completed")
            self.assertEqual(client.get("/api/state").json()["stage"], "idle")

    def test_blocked_worker_keeps_http_responsive_and_rejects_overlap(self):
        with self.blocking() as (client, started, release):
            self.assertEqual(client.post("/api/turn", json={"text": "첫 발화"}).status_code, 202)
            self.assertTrue(started.wait(1))
            self.assertTrue(client.get("/api/state").json()["busy"])
            self.assertEqual(client.get("/api/health").status_code, 200)
            second = client.post("/api/turn", json={"text": "두 번째"})
            self.assertEqual(second.status_code, 409)
            self.assertEqual(second.json(), {"error": "busy"})
            release.set()
            wait_idle(client)
            self.assertEqual(client.post("/api/turn", json={"text": "다음"}).status_code, 202)

    def test_simultaneous_posts_reserve_only_one_worker(self):
        with self.blocking() as (client, started, release):
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(lambda _: client.post("/api/turn", json={"text": "안녕"}), range(2)))
            self.assertEqual(sorted(r.status_code for r in responses), [202, 409])
            self.assertEqual(client.get("/api/state").json()["turn_id"], 1)

    def test_disconnect_does_not_cancel_audio_or_leave_subscriber(self):
        with self.blocking() as (client, started, release):
            with client.websocket_connect("ws://127.0.0.1:8000/api/events") as ws:
                ws.receive_json()
                client.post("/api/turn", json={"text": "안녕"})
                self.assertTrue(started.wait(1))
            self.assertTrue(client.get("/api/state").json()["busy"])
            self.assertEqual(len(client.app.state.runtime.subscribers), 0)
            release.set()
            state = wait_idle(client)
            self.assertTrue(state["last_result"]["audio_played"])
            self.assertEqual(client.post("/api/turn", json={"text": "다음"}).status_code, 202)

    def test_end_waits_for_current_turn_and_refuses_future_turns(self):
        with self.blocking() as (client, started, release):
            client.post("/api/turn", json={"text": "안녕"})
            self.assertTrue(started.wait(1))
            ending = client.post("/api/end").json()
            self.assertTrue(ending["busy"])
            self.assertFalse(ending["accepting"])
            self.assertEqual(client.post("/api/turn", json={"text": "또"}).json(), {"error": "session_ended"})
            release.set()
            self.assertEqual(wait_idle(client)["stage"], "ended")
            self.assertEqual(client.post("/api/end").json()["stage"], "ended")

    def test_bad_input_never_echoes_request_or_credential_fields(self):
        with self.client() as client:
            for body in ({"text": " "}, {"text": 1}, {"text": "x" * 2001},
                         {"text": "안녕", "GEMINI_API_KEY": "FAKE_PRIVATE_MARKER"}):
                with self.subTest(body_type=type(body)):
                    response = client.post("/api/turn", json=body)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json(), {"error": "invalid_input"})
            response = client.post("/api/turn", content='{"text":"FAKE_PRIVATE_MARKER"',
                                   headers={"Content-Type": "application/json"})
            self.assertEqual(response.json(), {"error": "invalid_input"})
            self.assertEqual(client.get("/api/state").json()["turn_id"], None)

    def test_exception_is_sanitized_history_rolled_back_and_next_turn_works(self):
        calls = []

        def processor(session, text, emit):
            calls.append(len(session.messages))
            if len(calls) == 1:
                session.messages.append({"role": "user", "content": "unanswered"})
                raise RuntimeError("FAKE_PRIVATE_MARKER")
            return success(session, text, emit)

        with self.client(processor) as client, client.websocket_connect("ws://127.0.0.1:8000/api/events") as ws:
            ws.receive_json()
            client.post("/api/turn", json={"text": "안녕"})
            events = [ws.receive_json() for _ in range(3)]
            self.assertNotIn("FAKE_PRIVATE_MARKER", str(events))
            self.assertEqual(events[-1]["data"]["result"]["errors"], ["turn_failed"])
            client.post("/api/turn", json={"text": "다시"})
            self.assertEqual(wait_idle(client)["last_result"]["status"], "completed")
            self.assertEqual(calls, [1, 1])

    def test_real_shared_flow_emits_stages_in_service_order_with_local_playback(self):
        from backend.conversation.service import process_turn
        entered_stages = []

        with self.client(process_turn) as client, contextlib.ExitStack() as stack:
            runtime = client.app.state.runtime

            def step(stage, value):
                def call(*args):
                    # Worker events are posted before the service. Record the
                    # actual service order; event sequence is checked below.
                    entered_stages.append(stage)
                    return value
                return call

            for target, stage, value in (
                ("backend.translation.translator.translate_korean_input", "translating_input", KoreanInputTranslation("ok", "안녕", "こんにちは。")),
                ("backend.conversation.japanese_response.generate_validated_japanese_reply", "generating", "こんにちは。"),
                ("backend.translation.translator.japanese_to_korean", "translating_subtitle", "안녕하세요."),
                ("backend.voice.tts.speak", "synthesizing", True),
                ("backend.conversation.service.play_with_expression", "speaking", True),
            ):
                stack.enter_context(patch(target, side_effect=step(stage, value)))
            with client.websocket_connect("ws://127.0.0.1:8000/api/events") as ws:
                ws.receive_json()
                client.post("/api/turn", json={"text": "안녕"})
                events = []
                while not events or events[-1]["type"] != "turn_finished":
                    events.append(ws.receive_json())
            self.assertEqual([e["data"]["stage"] for e in events if e["type"] == "stage_changed"],
                             ["queued", *entered_stages])
            self.assertEqual(len(entered_stages), 5)
            self.assertTrue(events[-1]["data"]["result"]["audio_played"])
            self.assertEqual([m["role"] for m in runtime.session.messages], ["system", "user", "assistant"])

    def test_partial_failure_is_visible_and_another_turn_is_allowed(self):
        def processor(session, text, emit):
            return TurnResult("partial_failure", korean_subtitle="안녕", errors=("synthesis_failed",))
        with self.client(processor) as client:
            client.post("/api/turn", json={"text": "안녕"})
            state = wait_idle(client)
            self.assertEqual(state["last_result"]["errors"], ["synthesis_failed"])
            self.assertEqual(client.post("/api/turn", json={"text": "다음"}).status_code, 202)

    def test_browser_origin_and_host_are_restricted_for_http_and_websocket(self):
        with self.client() as client:
            self.assertEqual(client.get("/api/state", headers={"Origin": "https://untrusted.example"}).status_code, 403)
            self.assertEqual(client.post("/api/end", headers={"Origin": "null"}).status_code, 403)
            self.assertEqual(client.get("/api/state", headers={"Host": "untrusted.example"}).status_code, 400)
            for origin in ("https://untrusted.example", "null"):
                with self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect("ws://127.0.0.1:8000/api/events", headers={"Origin": origin}):
                        pass
            response = client.options("/api/turn", headers={
                "Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], "http://127.0.0.1:5173")


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_joins_worker_only_after_playback_cleanup(self):
        started, release, cleaned = threading.Event(), threading.Event(), threading.Event()

        def processor(session, text, emit):
            started.set()
            try:
                release.wait(3)
                return success(session, text, emit)
            finally:
                cleaned.set()

        runtime = Runtime(processor)
        runtime.submit("안녕")
        self.assertTrue(await asyncio.to_thread(started.wait, 1))
        closing = asyncio.create_task(runtime.close())
        try:
            await asyncio.sleep(.02)
            self.assertFalse(closing.done())
            self.assertTrue(runtime.busy)
        finally:
            release.set()
            await asyncio.wait_for(closing, 2)
        self.assertTrue(cleaned.is_set())
        self.assertFalse(runtime.busy)
        self.assertFalse(any(t.name.startswith("waifu-turn") for t in threading.enumerate()))

    async def test_slow_subscriber_is_detached_without_blocking_other_subscribers(self):
        runtime = Runtime(success)
        try:
            slow, fast = runtime.subscribe(), runtime.subscribe()
            for _ in range(65):
                runtime.publish("stage_changed", {"stage": "generating"})
                while not fast.empty():
                    fast.get_nowait()
            self.assertNotIn(slow, runtime.subscribers)
            self.assertIsNone(slow.get_nowait())
            self.assertIn(fast, runtime.subscribers)
            self.assertLessEqual(slow.qsize(), 64)
        finally:
            await runtime.close()

    async def test_subscriber_limit_and_event_projection_exclude_private_fields(self):
        runtime = Runtime(success)
        try:
            queues = [runtime.subscribe() for _ in range(4)]
            with self.assertRaises(TurnRejected):
                runtime.subscribe()
            queue = queues[0]
            queue.get_nowait()
            runtime.on_event(TurnEvent("subtitle_ready", {"korean_subtitle": "안녕", "headers": "FAKE_PRIVATE_MARKER"}))
            self.assertEqual(queue.get_nowait()["data"], {"korean_subtitle": "안녕"})
            runtime.on_event(TurnEvent("notice", {"code": "bad", "message": "FAKE_PRIVATE_MARKER"}))
            self.assertNotIn("FAKE_PRIVATE_MARKER", str(queue.get_nowait()))
            runtime.on_event(TurnEvent("private_event", {"secret": "FAKE_PRIVATE_MARKER"}))
            self.assertTrue(queue.empty())
        finally:
            await runtime.close()


class ApiLauncherTests(unittest.TestCase):
    def test_launcher_binds_loopback_single_worker_without_reload_or_access_logs(self):
        with patch("uvicorn.run") as run, patch("os.chdir"), patch("logging.basicConfig"), contextlib.redirect_stdout(io.StringIO()):
            # Restore logger state changed by the explicit launcher.
            loggers = [logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "translator")]
            states = [(logger, logger.handlers[:], logger.propagate, logger.level) for logger in loggers]
            try:
                run_api()
            finally:
                for logger, handlers, propagate, level in states:
                    logger.handlers[:] = handlers
                    logger.propagate = propagate
                    logger.setLevel(level)
        self.assertEqual(run.call_args.kwargs["host"], "127.0.0.1")
        self.assertEqual(run.call_args.args[0], "backend.api.app:app")
        self.assertEqual(run.call_args.kwargs["port"], 8000)
        self.assertEqual(run.call_args.kwargs["workers"], 1)
        self.assertFalse(run.call_args.kwargs["reload"])
        self.assertFalse(run.call_args.kwargs["access_log"])

    def test_console_keeps_provider_codes_but_never_raw_diagnostics(self):
        filter_ = SafeConsoleFilter()
        provider = "JA->KO provider=gemini model=gemini-3.5-flash-lite fallback_reason=none"
        record = logging.LogRecord("translator", logging.INFO, "", 0, provider, (),
                                   (ValueError, ValueError("FAKE_PRIVATE_MARKER"), None))
        self.assertTrue(filter_.filter(record))
        self.assertEqual(record.getMessage(), provider)
        self.assertIsNone(record.exc_info)
        record = logging.LogRecord("tts", logging.ERROR, "", 0, "response=%s", ("FAKE_PRIVATE_MARKER",),
                                   (ValueError, ValueError("FAKE_PRIVATE_MARKER"), None))
        self.assertTrue(filter_.filter(record))
        self.assertEqual(record.getMessage(), "service_error")
        self.assertIsNone(record.exc_info)
        record = logging.LogRecord("translator", logging.DEBUG, "", 0, "FAKE_PRIVATE_MARKER", (), None)
        self.assertFalse(filter_.filter(record))
