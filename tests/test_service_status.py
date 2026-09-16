"""Operation evidence, per-turn isolation and safe API/UI metadata."""

import asyncio
import contextlib
import io
import json
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.schemas import public_event
from backend.character import vts
from backend.conversation import llm, service
from backend.service_status import (
    observe_services, public_subtitle_provider, report_service, report_subtitle_provider,
)
from backend.translation import translator
from backend.translation.gemini_translator import GeminiTranslationResult
from backend.voice import tts


class ObservationTests(unittest.TestCase):
    def test_observer_is_scoped_and_broken_display_cannot_break_work(self):
        outer, inner = [], []
        with observe_services(lambda kind, data: outer.append((kind, data))):
            report_service("ollama", "response_received")
            with observe_services(lambda kind, data: inner.append((kind, data))):
                report_service("vts", "connection_failed")
            report_service("sbv2", "synthesis_succeeded")
        report_service("ollama", "request_failed")
        self.assertEqual([data["service"] for _, data in outer], ["ollama", "sbv2"])
        self.assertEqual(inner[0][1]["state"], "error")
        with observe_services(Mock(side_effect=RuntimeError("PRIVATE_MARKER"))):
            report_service("ollama", "response_received")

    def test_public_projection_allowlists_codes_and_model_identifiers(self):
        for code in ("PRIVATE_MARKER", "response_received:PRIVATE_MARKER", {"secret": "PRIVATE_MARKER"}):
            self.assertIsNone(public_event(service.TurnEvent("service_status", {"service": "ollama", "code": code})))
        event = public_event(service.TurnEvent("service_status", {
            "service": "vts", "code": "authentication_failed", "state": "ok", "token": "PRIVATE_MARKER"}))
        self.assertEqual(event, {"service": "vts", "state": "error", "code": "authentication_failed"})
        data = public_subtitle_provider({"provider": "qwen", "model": "/PRIVATE_MARKER/model",
                                        "fallback_reason": "gemini_request_error;PRIVATE_MARKER",
                                        "headers": "PRIVATE_MARKER"})
        self.assertEqual(data, {"provider": "qwen", "model": "custom", "fallback_reason": "translation_failed"})

    def test_ollama_reports_actual_transport_results_and_preserves_exception(self):
        observations = []
        response = Mock()
        response.json.return_value = {"message": {"content": "reply"}}
        with observe_services(lambda kind, data: observations.append(data)), patch.object(llm.requests, "post", return_value=response) as post:
            self.assertEqual(llm.chat([]), "reply")
            failure = OSError("PRIVATE_MARKER")
            post.side_effect = failure
            with self.assertRaises(OSError) as raised:
                llm.chat([])
            self.assertIs(raised.exception, failure)
        self.assertEqual([item["code"] for item in observations], ["response_received", "request_failed"])
        self.assertNotIn("PRIVATE_MARKER", str(observations))

    def test_real_translator_gemini_acceptance_and_fallback_metadata(self):
        cases = [
            (GeminiTranslationResult("안녕하세요.", "PRIVATE_MARKER", None), "gemini", "none", "subtitle_accepted"),
            (GeminiTranslationResult(None, "PRIVATE_MARKER", "gemini_http_503"), "qwen", "gemini_http_503", "translation_failed"),
            (GeminiTranslationResult(None, None, "gemini_api_key_missing"), "qwen", "gemini_api_key_missing", "api_key_missing"),
            (GeminiTranslationResult("こんにちは요", "PRIVATE_MARKER", None), "qwen", "japanese_character", "translation_failed"),
        ]
        for result, provider, reason, code in cases:
            with self.subTest(provider=provider, reason=reason):
                events = []
                with observe_services(lambda kind, data: events.append((kind, data))), patch.object(translator, "gemini_japanese_to_korean", return_value=result), patch.object(translator, "chat", return_value='{"translation":"안녕하세요."}') as qwen:
                    self.assertEqual(translator.japanese_to_korean("こんにちは。"), "안녕하세요.")
                self.assertEqual(events[0][1]["code"], code)
                self.assertEqual(events[-1][0], "subtitle_provider")
                self.assertEqual(events[-1][1]["provider"], provider)
                self.assertEqual(events[-1][1]["fallback_reason"], reason)
                self.assertEqual(qwen.call_count, 0 if provider == "gemini" else 1)
                self.assertNotIn("PRIVATE_MARKER", str(events))

    def test_both_translators_failing_never_claims_qwen_was_adopted(self):
        events = []
        with observe_services(lambda kind, data: events.append(data)), patch.object(translator, "gemini_japanese_to_korean", return_value=GeminiTranslationResult(None, None, "gemini_request_timeout")), patch.object(translator, "chat", side_effect=OSError("PRIVATE_MARKER")):
            self.assertIsNone(translator.japanese_to_korean("こんにちは。"))
        self.assertEqual(events[-1], {"provider": "none", "model": "none", "fallback_reason": "gemini_request_timeout;qwen_request_error"})

    def test_sbv2_failure_success_and_cosyvoice_are_distinguished_without_reading_settings(self):
        for backend, synth, expected in [("sbv2", False, "synthesis_failed"), ("sbv2", True, "synthesis_succeeded"), ("cosyvoice", True, None)]:
            events = []
            with self.subTest(backend=backend, synth=synth), observe_services(lambda kind, data: events.append(data)), patch.dict("os.environ", {}, clear=True), patch.object(tts, "_read_config", return_value={"backend": backend, "fallback_to_cosyvoice": False}), patch.object(tts, "_speak_sbv2", return_value=synth), patch.object(tts, "_speak_cosyvoice", return_value=True):
                self.assertEqual(tts.speak("こんにちは。", 1, "normal", 4), synth)
            self.assertEqual([item["code"] for item in events], [expected] if expected else [])

    def test_vts_worker_inherits_observer_and_still_joins_after_playback(self):
        entered = threading.Event()
        threads, events = [], []
        async def apply(*args, stop_event, **kwargs):
            threads.append(threading.current_thread())
            report_service("vts", "parameters_applied")
            entered.set()
            while not stop_event.is_set():
                await asyncio.sleep(.001)
        def play(path):
            self.assertTrue(entered.wait(1))
            return True
        with observe_services(lambda kind, data: events.append(data)), patch.object(vts, "prepare_lip_sync", return_value=None), patch.object(vts, "apply_expression", side_effect=apply), patch.object(service.audio_playback, "play_wav", side_effect=play):
            self.assertTrue(service.play_with_expression("normal"))
        self.assertEqual(events[-1]["code"], "parameters_applied")
        self.assertTrue(all(not thread.is_alive() for thread in threads))


class VTSObservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_acknowledgement_once_and_no_auth_only_success(self):
        for auth, response, expected in [
            (False, {}, "authentication_failed"),
            (True, {"messageType": "APIError", "private": "PRIVATE_MARKER"}, "parameter_rejected"),
            (True, {"messageType": "InjectParameterDataResponse"}, "parameters_applied"),
        ]:
            ws = Mock(send=AsyncMock(), recv=AsyncMock(return_value=json.dumps(response)))
            connection = AsyncMock()
            connection.__aenter__.return_value = ws
            events = []
            with self.subTest(expected=expected), observe_services(lambda kind, data: events.append(data)), patch.object(vts.websockets, "connect", return_value=connection), patch.object(vts, "auth", new=AsyncMock(return_value=auth)), contextlib.redirect_stdout(io.StringIO()):
                await vts.apply_expression("normal", duration=.11)
            self.assertEqual([item["code"] for item in events], ["not_checked", expected])
            self.assertNotIn("PRIVATE_MARKER", str(events))

    async def test_model_limitation_and_failed_mouth_reset_override_success(self):
        for calibrated, reset_failure, expected in [(False, False, "model_not_calibrated"), (True, True, "mouth_reset_failed")]:
            connection = AsyncMock()
            async def inject(ws, values, request_id="expression"):
                if request_id == "mouth_reset" and reset_failure:
                    raise OSError("PRIVATE_MARKER")
            events = []
            with observe_services(lambda kind, data: events.append(data)), patch.object(vts.websockets, "connect", return_value=connection), patch.object(vts, "auth", new=AsyncMock(return_value=True)), patch.object(vts, "_supports_lip_sync", new=AsyncMock(return_value=calibrated)), patch.object(vts, "_inject_parameters", side_effect=inject), contextlib.redirect_stdout(io.StringIO()):
                await vts.apply_expression("normal", duration=.001, lip_sync=vts.WavLipSync((.5,), .04, .04))
            self.assertEqual(events[-1]["code"], expected)
            self.assertEqual(events[-1]["state"], "warning")


class StatusAPITests(unittest.TestCase):
    def test_http_and_ws_keep_last_observation_and_reset_subtitle_each_turn(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def processor(session, text, emit):
            calls.append(text)
            if len(calls) == 1:
                report_service("gemini", "api_key_missing")
                report_subtitle_provider("qwen", "qwen3.5:9b", "gemini_api_key_missing")
                report_service("vts", "authentication_failed")
            else:
                entered.set()
                release.wait(2)
                report_service("gemini", "subtitle_accepted")
                report_subtitle_provider("gemini", "gemini-3.5-flash-lite", "none")
                report_service("vts", "parameters_applied")
            return service.TurnResult("completed", korean_subtitle="안녕하세요.", audio_played=True)
        with TestClient(create_app(processor), base_url="http://127.0.0.1:8000") as client, client.websocket_connect("ws://127.0.0.1:8000/api/events") as ws:
            initial = ws.receive_json()["data"]
            self.assertTrue(all(item["state"] == "unknown" for item in initial["services"].values()))
            self.assertIsNone(initial["subtitle_provider"])
            client.post("/api/turn", json={"text": "first"})
            events = []
            while not events or events[-1]["type"] != "turn_finished":
                events.append(ws.receive_json())
            state = client.get("/api/state").json()
            self.assertEqual(state["services"]["vts"], {"state": "error", "code": "authentication_failed", "turn_id": 1})
            self.assertEqual(state["subtitle_provider"]["provider"], "qwen")
            self.assertEqual(state["services"]["sbv2"]["state"], "unknown")
            self.assertTrue(state["last_result"]["audio_played"])
            client.post("/api/turn", json={"text": "second"})
            try:
                self.assertTrue(entered.wait(1))
                self.assertIsNone(client.get("/api/state").json()["subtitle_provider"])
            finally:
                release.set()
            while ws.receive_json()["type"] != "turn_finished":
                pass
            with client.websocket_connect("ws://127.0.0.1:8000/api/events") as restored:
                state = restored.receive_json()["data"]
                self.assertEqual(state["subtitle_provider"], {"provider": "gemini", "model": "gemini-3.5-flash-lite", "fallback_reason": "none", "turn_id": 2})
                self.assertEqual(state["services"]["vts"]["state"], "ok")
                self.assertEqual(state["services"]["ollama"]["state"], "unknown")

    def test_ws_projection_never_forwards_response_headers_private_settings_or_unknown_codes(self):
        def processor(session, text, emit):
            emit(service.TurnEvent("service_status", {"service": "vts", "code": "connection_failed", "token": "PRIVATE_MARKER"}))
            emit(service.TurnEvent("subtitle_provider", {"provider": "qwen", "model": "PRIVATE_MARKER", "fallback_reason": "PRIVATE_MARKER", "headers": "PRIVATE_MARKER"}))
            return service.TurnResult("completed")
        with TestClient(create_app(processor), base_url="http://127.0.0.1:8000") as client, client.websocket_connect("ws://127.0.0.1:8000/api/events") as ws:
            ws.receive_json()
            client.post("/api/turn", json={"text": "test"})
            events = []
            while not events or events[-1]["type"] != "turn_finished":
                events.append(ws.receive_json())
            self.assertNotIn("PRIVATE_MARKER", json.dumps(events))
            self.assertNotIn("PRIVATE_MARKER", client.get("/api/state").text)
