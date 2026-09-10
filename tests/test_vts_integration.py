import asyncio
import contextlib
import io
import json
import logging
import math
from pathlib import Path
import runpy
import struct
import tempfile
import threading
import time
import unittest
import wave
from unittest.mock import AsyncMock, Mock, patch

import vts
from emotion import expression_presets
from translator import KoreanInputTranslation


MAIN = Path(__file__).resolve().parents[1] / "main.py"


class VTSProtocolTests(unittest.IsolatedAsyncioTestCase):
    def connection(self):
        ws = Mock()
        ws.send = AsyncMock()
        ws.recv = AsyncMock(return_value=json.dumps({
            "messageType": "InjectParameterDataResponse", "data": {},
        }))
        connection = AsyncMock()
        connection.__aenter__.return_value = ws
        connection.__aexit__.return_value = False
        return ws, connection

    async def test_existing_happy_and_unknown_emotion_presets(self):
        for emotion, preset in [("happy", "happy"), ("unknown", "normal")]:
            with self.subTest(emotion=emotion):
                ws, connection = self.connection()
                with patch("vts.websockets.connect", return_value=connection) as connect:
                    with patch("vts.auth", new=AsyncMock(return_value=True)):
                        with contextlib.redirect_stdout(io.StringIO()):
                            await vts.apply_expression(emotion, duration=0.001)
                message = json.loads(ws.send.call_args.args[0])
                self.assertEqual(message["messageType"], "InjectParameterDataRequest")
                self.assertEqual(
                    {p["id"]: p["value"] for p in message["data"]["parameterValues"]},
                    expression_presets[preset],
                )
                self.assertEqual(connect.call_args.kwargs["open_timeout"], vts.IO_TIMEOUT)
                self.assertEqual(connect.call_args.kwargs["close_timeout"], vts.CLOSE_TIMEOUT)
                transport = connect.call_args.kwargs["logger"]
                self.assertFalse(transport.isEnabledFor(logging.DEBUG))
                self.assertFalse(transport.propagate)
                connection.__aexit__.assert_awaited_once()

    async def test_connection_failure_is_sanitized(self):
        with patch("vts.websockets.connect", side_effect=OSError("private token / response")):
            with self.assertLogs("vts", level="WARNING") as logs:
                await vts.apply_expression("happy")
        self.assertEqual(logs.output, ["WARNING:vts:VTS skipped: connection_failed"])

    async def test_authentication_failure_skips_parameter_injection(self):
        ws, connection = self.connection()
        with patch("vts.websockets.connect", return_value=connection):
            with patch("vts.auth", new=AsyncMock(return_value=False)):
                with self.assertLogs("vts", level="WARNING") as logs:
                    await vts.apply_expression("happy")
        ws.send.assert_not_awaited()
        self.assertEqual(logs.output, ["WARNING:vts:VTS skipped: authentication_failed"])

    async def test_bad_response_and_parameter_rejection_hide_raw_response(self):
        for response, reason in [
            ("private malformed response", "response_error"),
            (json.dumps({"messageType": "APIError", "data": {"message": "private token"}}), "parameter_rejected"),
        ]:
            with self.subTest(reason=reason):
                ws, connection = self.connection()
                ws.recv.return_value = response
                with patch("vts.websockets.connect", return_value=connection):
                    with patch("vts.auth", new=AsyncMock(return_value=True)):
                        with self.assertLogs("vts", level="WARNING") as logs:
                            await vts.apply_expression("happy")
                self.assertEqual(logs.output, [f"WARNING:vts:VTS skipped: {reason}"])

    async def test_auth_and_response_timeouts_are_bounded(self):
        async def stalled(*args):
            await asyncio.Future()

        for phase in ["auth", "send", "recv"]:
            with self.subTest(phase=phase):
                ws, connection = self.connection()
                auth = AsyncMock(return_value=True)
                if phase == "auth":
                    auth.side_effect = stalled
                else:
                    getattr(ws, phase).side_effect = stalled
                with patch("vts.websockets.connect", return_value=connection), patch("vts.auth", auth):
                    with patch("vts.IO_TIMEOUT", 0.01):
                        with self.assertLogs("vts", level="WARNING") as logs:
                            await asyncio.wait_for(vts.apply_expression("happy"), timeout=1)
                self.assertEqual(logs.output, ["WARNING:vts:VTS skipped: timeout"])

    async def test_stop_cancels_pending_connection_auth_or_response(self):
        for phase in ["connect", "auth", "recv"]:
            with self.subTest(phase=phase):
                ws, connection = self.connection()
                entered, cancelled = asyncio.Event(), asyncio.Event()
                stop = threading.Event()

                async def stalled(*args):
                    entered.set()
                    try:
                        await asyncio.Future()
                    finally:
                        cancelled.set()

                auth = AsyncMock(return_value=True)
                if phase == "connect":
                    connection.__aenter__.side_effect = stalled
                elif phase == "auth":
                    auth.side_effect = stalled
                else:
                    ws.recv.side_effect = stalled
                with patch("vts.websockets.connect", return_value=connection), patch("vts.auth", auth):
                    job = asyncio.create_task(vts.apply_expression("happy", stop_event=stop))
                    try:
                        await asyncio.wait_for(entered.wait(), timeout=1)
                        stop.set()
                        await asyncio.wait_for(job, timeout=1)
                    finally:
                        job.cancel()
                        await asyncio.gather(job, return_exceptions=True)
                self.assertTrue(cancelled.is_set())
                if phase != "connect":
                    connection.__aexit__.assert_awaited_once()

    async def test_already_stopped_never_connects(self):
        stop = threading.Event()
        stop.set()
        with patch("vts.websockets.connect") as connect:
            await vts.apply_expression("happy", stop_event=stop)
        connect.assert_not_called()

    async def test_unlimited_duration_without_stop_signal_is_rejected(self):
        with patch("vts.websockets.connect") as connect:
            with self.assertLogs("vts", level="WARNING") as logs:
                await asyncio.wait_for(vts.apply_expression("happy", duration=None), timeout=1)
        connect.assert_not_called()
        self.assertEqual(logs.output, ["WARNING:vts:VTS skipped: stop_event_required"])

    async def test_standalone_default_still_finishes_after_four_seconds(self):
        ws, connection = self.connection()
        start = time.monotonic()
        with patch("vts.websockets.connect", return_value=connection):
            with patch("vts.auth", new=AsyncMock(return_value=True)):
                with contextlib.redirect_stdout(io.StringIO()):
                    await asyncio.wait_for(vts.apply_expression("happy"), timeout=7)
        self.assertGreaterEqual(time.monotonic() - start, 4.0)
        self.assertGreater(ws.send.await_count, 1)
        connection.__aexit__.assert_awaited_once()


class MainVTSIntegrationTests(unittest.TestCase):
    def run_dialogue(self, speak, play, apply, on_input=None, lip_sync=None):
        inputs = iter(["", "좋은 일이 있어", "조금 힘들어", "종료"])

        def read(prompt):
            if on_input:
                on_input(prompt)
            return next(inputs)

        translations = [
            KoreanInputTranslation("ok", "좋은 일이 있어", "いいことがありました。"),
            KoreanInputTranslation("ok", "조금 힘들어", "少し疲れました。"),
        ]
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("logging_setup.configure_console_logging"))
            stack.enter_context(patch("builtins.input", side_effect=read))
            stack.enter_context(patch("translator.translate_korean_input", side_effect=translations))
            stack.enter_context(patch("translator.japanese_to_korean", return_value="알겠어요"))
            stack.enter_context(patch("japanese_response.chat", return_value="わかりました。"))
            stack.enter_context(patch("vts.apply_expression", side_effect=apply))
            stack.enter_context(patch("vts.prepare_lip_sync", return_value=lip_sync))
            stack.enter_context(patch("tts.speak", side_effect=speak))
            stack.enter_context(patch("audio_playback.play_wav", side_effect=play))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            return runpy.run_path(str(MAIN), run_name="__main__")

    def test_two_turns_use_emotion_and_stop_workers_before_next_input(self):
        active = set()
        entered = threading.Event()
        emotions, stops, threads = [], [], []
        synthesized = []

        def speak(text, speed, emotion, duration):
            self.assertFalse(active)
            entered.clear()
            synthesized.append(emotion)
            return True

        async def apply(emotion, duration, stop_event, lip_sync=None):
            self.assertIsNone(duration)
            self.assertEqual(synthesized[-1], emotion)
            self.assertFalse(active)
            active.add(emotion)
            emotions.append(emotion)
            stops.append(stop_event)
            threads.append(threading.current_thread())
            entered.set()
            try:
                while not stop_event.is_set():
                    await asyncio.sleep(0.001)
            finally:
                active.remove(emotion)

        def play(path):
            self.assertEqual(path, "output.wav")
            self.assertTrue(entered.wait(timeout=1))
            self.assertEqual(len(active), 1)
            self.assertFalse(stops[-1].is_set())
            return True

        def on_input(prompt):
            self.assertFalse(active)
            self.assertTrue(all(not t.is_alive() for t in threads))

        state = self.run_dialogue(speak, play, apply, on_input)
        self.assertEqual(emotions, ["happy", "sad"])
        self.assertTrue(all(s.is_set() for s in stops))
        self.assertEqual(len(state["messages"]), 5)

    def test_real_expression_survives_long_playback_then_exits_before_next_turn(self):
        real_apply = vts.apply_expression
        ws = Mock()
        connection = AsyncMock()
        connection.__aenter__.return_value = ws
        connection.__aexit__.return_value = False
        injected = threading.Event()
        send_times, workers, stop_events = [], [], []

        async def send(message):
            send_times.append(time.monotonic())
            injected.set()

        ws.send = AsyncMock(side_effect=send)
        ws.recv = AsyncMock(return_value=json.dumps({"messageType": "InjectParameterDataResponse"}))

        async def apply(*args, **kwargs):
            self.assertIsNone(kwargs["duration"])
            workers.append(threading.current_thread())
            stop_events.append(kwargs["stop_event"])
            await real_apply(*args, **kwargs)

        def speak(*args):
            self.assertTrue(all(not worker.is_alive() for worker in workers))
            injected.clear()
            send_times.clear()
            return True

        def play(path):
            self.assertTrue(injected.wait(timeout=1))
            if len(workers) == 1:
                time.sleep(4.3)  # Regression: the old default ended at four seconds.
                self.assertTrue(workers[-1].is_alive())
                self.assertGreater(send_times[-1] - send_times[0], 4.0)
            self.assertFalse(stop_events[-1].is_set())
            return True

        def on_input(prompt):
            self.assertTrue(all(not worker.is_alive() for worker in workers))
            self.assertTrue(all(event.is_set() for event in stop_events))

        with patch("vts.websockets.connect", return_value=connection), patch("vts.auth", new=AsyncMock(return_value=True)):
            state = self.run_dialogue(speak, play, apply, on_input)
        self.assertEqual(len(workers), 2)
        self.assertEqual(len(state["messages"]), 5)
        self.assertEqual(connection.__aexit__.await_count, 2)

    def test_worker_failure_keeps_audio_and_next_turn_running(self):
        async def apply(*args, **kwargs):
            raise RuntimeError("private token and response")

        play = Mock(return_value=True)
        with self.assertLogs("vts", level="WARNING") as logs:
            state = self.run_dialogue(Mock(return_value=True), play, apply)
        self.assertEqual(play.call_count, 2)
        self.assertEqual(len(state["messages"]), 5)
        self.assertEqual(logs.output, ["WARNING:vts:VTS skipped: worker_error"] * 2)

    def test_real_expression_connection_or_auth_failure_keeps_two_turns_running(self):
        real_apply = vts.apply_expression
        for failure in ["connection", "authentication"]:
            with self.subTest(failure=failure):
                connection = AsyncMock()
                connection.__aexit__.return_value = False
                play = Mock(return_value=True)
                finished = threading.Event()

                async def apply(*args, **kwargs):
                    # Exercise the failure before playback finishes, otherwise
                    # an immediate mocked player could cancel before connecting.
                    try:
                        await real_apply(*args, **kwargs)
                    finally:
                        finished.set()

                def play_audio(path):
                    self.assertTrue(finished.wait(timeout=1))
                    return play(path)

                def speak(*args):
                    finished.clear()
                    return True

                connect = Mock(return_value=connection)
                if failure == "connection":
                    connect.side_effect = OSError("private token")
                with patch("vts.websockets.connect", connect), patch("vts.auth", new=AsyncMock(return_value=False)):
                    with self.assertLogs("vts", level="WARNING") as logs:
                        state = self.run_dialogue(speak, play_audio, apply)
                self.assertEqual(play.call_count, 2)
                self.assertEqual(len(state["messages"]), 5)
                self.assertEqual(logs.output, [f"WARNING:vts:VTS skipped: {failure}_failed"] * 2)

    def test_real_expression_stalled_auth_is_cancelled_before_next_turn(self):
        real_apply = vts.apply_expression
        entered, cancelled = threading.Event(), threading.Event()
        connection = AsyncMock()
        connection.__aexit__.return_value = False
        workers = []

        async def auth(ws):
            workers.append(threading.current_thread())
            entered.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

        def speak(*args):
            self.assertTrue(all(not t.is_alive() for t in workers))
            entered.clear()
            cancelled.clear()
            return True

        def play(path):
            self.assertTrue(entered.wait(timeout=1))
            self.assertFalse(cancelled.is_set())
            return False  # Playback failure must also signal stop and join.

        def on_input(prompt):
            self.assertTrue(all(not t.is_alive() for t in workers))
            if workers:
                self.assertTrue(cancelled.is_set())

        with patch("vts.websockets.connect", return_value=connection), patch("vts.auth", side_effect=auth):
            with self.assertLogs(level="ERROR"):
                state = self.run_dialogue(speak, play, real_apply, on_input)
        self.assertEqual(len(workers), 2)
        self.assertEqual(len(state["messages"]), 5)

    def test_synthesis_failure_does_not_start_expression_or_playback(self):
        apply, play = AsyncMock(), Mock()
        state = self.run_dialogue(Mock(return_value=False), play, apply)
        apply.assert_not_called()
        play.assert_not_called()
        self.assertEqual(len(state["messages"]), 5)

    def test_playback_exception_still_stops_and_joins_worker(self):
        entered, stopped = threading.Event(), threading.Event()
        threads = []

        async def apply(emotion, duration, stop_event, lip_sync=None):
            threads.append(threading.current_thread())
            entered.set()
            while not stop_event.is_set():
                await asyncio.sleep(0.001)
            stopped.set()

        def play(path):
            self.assertTrue(entered.wait(timeout=1))
            raise RuntimeError("player failed")

        with self.assertRaisesRegex(RuntimeError, "player failed"):
            self.run_dialogue(Mock(return_value=True), play, apply)
        self.assertTrue(stopped.is_set())
        self.assertTrue(all(not t.is_alive() for t in threads))

    def test_thread_start_failure_still_plays_audio(self):
        play = Mock(return_value=True)
        with patch("threading.Thread.start", side_effect=RuntimeError("private error")):
            with self.assertLogs("vts", level="WARNING") as logs:
                self.run_dialogue(Mock(return_value=True), play, AsyncMock())
        self.assertEqual(play.call_count, 2)
        self.assertEqual(logs.output, ["WARNING:vts:VTS skipped: worker_start_failed"] * 2)

    def test_lip_sync_clock_starts_at_playback_and_worker_is_joined_on_all_exits(self):
        for result in [True, False, RuntimeError("player failed"), KeyboardInterrupt()]:
            with self.subTest(result=type(result).__name__):
                lip = vts.WavLipSync((0.5,), 0.04, 0.04)
                entered, exited = threading.Event(), threading.Event()
                workers, stops = [], []

                async def apply(emotion, duration, stop_event, lip_sync):
                    self.assertIs(lip_sync, lip)
                    workers.append(threading.current_thread())
                    stops.append(stop_event)
                    entered.set()
                    try:
                        while not stop_event.is_set():
                            await asyncio.sleep(0.001)
                    finally:
                        exited.set()

                def speak(*args):
                    self.assertTrue(all(not w.is_alive() for w in workers))
                    entered.clear()
                    exited.clear()
                    lip.started_at = None
                    return True

                def play(path):
                    self.assertIsNotNone(lip.started_at)
                    self.assertLess(time.monotonic() - lip.started_at, 1)
                    self.assertTrue(entered.wait(1))
                    if isinstance(result, BaseException):
                        raise result
                    return result

                with contextlib.redirect_stderr(io.StringIO()):
                    if isinstance(result, BaseException):
                        with self.assertRaises(type(result)):
                            self.run_dialogue(speak, play, apply, lip_sync=lip)
                    else:
                        self.run_dialogue(speak, play, apply, lip_sync=lip)
                self.assertTrue(exited.is_set())
                self.assertTrue(all(s.is_set() for s in stops))
                self.assertTrue(all(not w.is_alive() for w in workers))


class WavLipSyncTests(unittest.TestCase):
    def analyse(self, samples, channels=1, rate=1000, width=2):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setparams((channels, width, rate, 0, "NONE", "not compressed"))
                wav.writeframes(struct.pack("<" + "h" * len(samples), *samples))
            return vts.prepare_lip_sync(path)

    def test_silence_attack_release_and_range(self):
        lip = self.analyse([0] * 40 + [8192] * 120 + [1638] * 40 + [0] * 40)
        self.assertEqual(lip.frame_seconds, 0.04)
        self.assertAlmostEqual(lip.duration, 0.24)
        self.assertEqual(lip.values[0], 0)
        self.assertEqual(lip.values[-1], 0)
        self.assertTrue(all(0 <= v <= 1 for v in lip.values))
        self.assertTrue(0 < lip.values[1] < lip.values[2] < lip.values[3] < 1)
        self.assertTrue(0 < lip.values[4] < lip.values[3])

    def test_louder_audio_opens_more_and_negative_peak_does_not_overflow(self):
        quiet = self.analyse([1000] * 40)
        loud = self.analyse([8000] * 40)
        peak = self.analyse([-32768] * 40)
        self.assertLess(quiet.values[0], loud.values[0])
        self.assertLessEqual(loud.values[0], peak.values[0])
        self.assertTrue(math.isfinite(peak.values[0]))
        self.assertLessEqual(peak.values[0], 1)

    def test_opposite_stereo_phases_do_not_cancel(self):
        mono = self.analyse([5000] * 40)
        stereo = self.analyse([5000, -5000] * 40, channels=2)
        self.assertEqual(mono.values, stereo.values)

    def test_partial_window_and_elapsed_time_skip_expired_frames(self):
        lip = self.analyse([5000] * 85)
        self.assertEqual(len(lip.values), 3)
        self.assertEqual(lip.mouth_value(100), 0)
        lip.started_at = 10
        self.assertEqual(lip.mouth_value(9), 0)
        self.assertEqual(lip.mouth_value(10.081), lip.values[2])
        self.assertEqual(lip.mouth_value(10.086), 0)

    def test_missing_unsupported_and_empty_audio_skip_without_private_details(self):
        with self.assertLogs("vts", level="WARNING") as logs:
            self.assertIsNone(vts.prepare_lip_sync("/nonexistent/private-audio.wav"))
            self.assertIsNone(self.analyse([0] * 40, width=1))
            self.assertIsNone(self.analyse([]))
        self.assertEqual(logs.output, [
            "WARNING:vts:VTS lip sync skipped: wav_unavailable_or_unsupported",
        ] * 3)


class LipSyncProtocolTests(unittest.IsolatedAsyncioTestCase):
    def connection(self, model_id=vts.LIP_SYNC_MODEL_ID):
        self.packets = []
        self.replies = asyncio.Queue()
        ws = Mock()

        async def send(raw):
            packet = json.loads(raw)
            self.packets.append(packet)
            if packet["messageType"] == "CurrentModelRequest":
                data = {"modelLoaded": True, "modelID": model_id}
                kind = "CurrentModelResponse"
            else:
                data, kind = {}, "InjectParameterDataResponse"
            await self.replies.put(json.dumps({
                "requestID": packet["requestID"], "messageType": kind, "data": data,
            }))

        ws.send = AsyncMock(side_effect=send)
        ws.recv = AsyncMock(side_effect=self.replies.get)
        connection = AsyncMock()
        connection.__aenter__.return_value = ws
        connection.__aexit__.return_value = False
        return ws, connection

    def lip(self):
        return vts.WavLipSync((0.5,) * 250, 0.04, 10, time.monotonic())

    async def test_emotion_and_calibrated_mouth_share_packets_then_reset_before_close(self):
        ws, connection = self.connection()

        async def closed(*args):
            self.assertEqual(self.packets[-1]["requestID"], "mouth_reset")
            return False

        connection.__aexit__.side_effect = closed
        with patch("vts.websockets.connect", return_value=connection) as connect, patch("vts.auth", new=AsyncMock(return_value=True)):
            with contextlib.redirect_stdout(io.StringIO()):
                await vts.apply_expression("happy", duration=0.085, lip_sync=self.lip())
        connect.assert_called_once()
        injections = [p for p in self.packets if p["requestID"] == "expression"]
        self.assertGreaterEqual(len(injections), 2)
        for packet in injections:
            values = {p["id"]: p["value"] for p in packet["data"]["parameterValues"]}
            self.assertAlmostEqual(values.pop("VoiceVolume"), 0.5 / 2.1)
            self.assertEqual(values, expression_presets["happy"])
        self.assertEqual(self.packets[-1]["data"]["parameterValues"], [{"id": "VoiceVolume", "value": 0.0}])

    async def test_other_model_keeps_expression_without_injecting_mouth(self):
        ws, connection = self.connection("another-model")
        with patch("vts.websockets.connect", return_value=connection), patch("vts.auth", new=AsyncMock(return_value=True)):
            with self.assertLogs("vts", level="WARNING") as logs, contextlib.redirect_stdout(io.StringIO()):
                await vts.apply_expression("happy", duration=0.001, lip_sync=self.lip())
        self.assertEqual(logs.output, ["WARNING:vts:VTS lip sync skipped: model_not_calibrated"])
        self.assertTrue(any(p["requestID"] == "expression" for p in self.packets))
        self.assertFalse(any(v["id"] == "VoiceVolume" for p in self.packets for v in p.get("data", {}).get("parameterValues", [])))

    async def test_stop_and_external_cancellation_reset_even_with_stale_reply(self):
        for external in [False, True]:
            with self.subTest(external=external):
                ws, connection = self.connection()
                entered = asyncio.Event()
                stop = threading.Event()
                receive = ws.recv.side_effect

                async def stalled_receive():
                    if self.packets[-1]["requestID"] == "expression":
                        entered.set()
                        await asyncio.Future()  # Leave this reply queued.
                    return await receive()

                ws.recv.side_effect = stalled_receive
                with patch("vts.websockets.connect", return_value=connection), patch("vts.auth", new=AsyncMock(return_value=True)):
                    job = asyncio.create_task(vts.apply_expression("happy", duration=None, stop_event=stop, lip_sync=self.lip()))
                    await asyncio.wait_for(entered.wait(), 1)
                    if external:
                        job.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await job
                    else:
                        stop.set()
                        await asyncio.wait_for(job, 1)
                self.assertEqual(self.packets[-1]["requestID"], "mouth_reset")
                self.assertTrue(self.replies.empty())  # Reset ack, not old ack, consumed.
                connection.__aexit__.assert_awaited_once()

    async def test_disconnected_socket_reset_is_bounded_and_logs_are_sanitized(self):
        ws, connection = self.connection()
        send = ws.send.side_effect

        async def disconnected(raw):
            if json.loads(raw)["messageType"] == "InjectParameterDataRequest":
                raise OSError("private token / raw response")
            await send(raw)

        ws.send.side_effect = disconnected
        with patch("vts.websockets.connect", return_value=connection), patch("vts.auth", new=AsyncMock(return_value=True)):
            with self.assertLogs("vts", level="WARNING") as logs:
                await asyncio.wait_for(vts.apply_expression("happy", lip_sync=self.lip()), 1)
        self.assertEqual(logs.output, [
            "WARNING:vts:VTS lip sync: mouth_reset_failed",
            "WARNING:vts:VTS skipped: connection_failed",
        ])

    async def test_slow_reply_uses_current_playback_window(self):
        ws, connection = self.connection()
        send = ws.send.side_effect
        lip = vts.WavLipSync(tuple(i / 100 for i in range(100)), 0.04, 4)
        observed = []

        async def slow(raw):
            packet = json.loads(raw)
            if packet["requestID"] == "expression":
                elapsed = time.monotonic() - lip.started_at
                value = next(p["value"] for p in packet["data"]["parameterValues"] if p["id"] == "VoiceVolume")
                observed.append((elapsed, value * 2.1))
                await asyncio.sleep(0.12)
            await send(raw)

        ws.send.side_effect = slow
        lip.started_at = time.monotonic()
        with patch("vts.websockets.connect", return_value=connection), patch("vts.auth", new=AsyncMock(return_value=True)):
            with contextlib.redirect_stdout(io.StringIO()):
                await vts.apply_expression("happy", duration=0.27, lip_sync=lip)
        self.assertGreaterEqual(len(observed), 2)
        self.assertGreaterEqual(observed[1][1], 0.03)
        for elapsed, value in observed:
            self.assertAlmostEqual(value, int(elapsed / 0.04) / 100, delta=0.011)

    async def test_stalled_reset_times_out_and_closes_connection(self):
        ws, connection = self.connection()
        receive = ws.recv.side_effect

        async def stalled_reset():
            if self.packets[-1]["requestID"] == "mouth_reset":
                await asyncio.Future()
            return await receive()

        ws.recv.side_effect = stalled_reset
        with patch("vts.websockets.connect", return_value=connection), patch("vts.auth", new=AsyncMock(return_value=True)), patch("vts.MOUTH_RESET_TIMEOUT", 0.02):
            with self.assertLogs("vts", level="WARNING") as logs, contextlib.redirect_stdout(io.StringIO()):
                await asyncio.wait_for(vts.apply_expression("happy", duration=0.001, lip_sync=self.lip()), 1)
        self.assertEqual(logs.output, ["WARNING:vts:VTS lip sync: mouth_reset_failed"])
        self.assertEqual(self.packets[-1]["requestID"], "mouth_reset")
        connection.__aexit__.assert_awaited_once()
