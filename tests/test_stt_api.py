from pathlib import Path
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.api.app import create_app
from backend.voice.stt import TranscriptionResult


class STTAPITests(unittest.TestCase):
    def test_transcript_is_draft_only_and_temp_file_is_removed(self):
        files = []

        def recognize(path):
            files.append(Path(path))
            self.assertEqual(path.read_bytes(), b"sample")
            return TranscriptionResult("안녕하세요", None, 0.1)

        with TestClient(create_app(transcriber=recognize), base_url="http://127.0.0.1") as client:
            before = list(client.app.state.runtime.session.messages)
            response = client.post("/api/transcribe", content=b"sample", headers={"Content-Type": "audio/webm"})
            self.assertEqual(response.json(), {"text": "안녕하세요"})
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(client.app.state.runtime.session.messages, before)
            self.assertIsNone(client.get("/api/state").json()["turn_id"])
        self.assertTrue(files)
        self.assertTrue(all(not path.exists() for path in files))

    def test_errors_are_private_and_release_reservation(self):
        def fail(path):
            raise RuntimeError("PRIVATE_TOKEN " + str(path))
        with TestClient(create_app(transcriber=fail), base_url="http://127.0.0.1") as client:
            for data, mime, expected in [(b"x", "text/plain", 415), (b"", "audio/wav", 422),
                                         (b"x", "audio/wav", 422)]:
                result = client.post("/api/transcribe", content=data, headers={"Content-Type": mime})
                self.assertEqual(result.status_code, expected)
                self.assertNotIn("PRIVATE", result.text)
                self.assertFalse(client.get("/api/state").json()["busy"])
            with patch("backend.api.app.MAX_AUDIO_BYTES", 2):
                self.assertEqual(client.post("/api/transcribe", content=b"123", headers={"Content-Type": "audio/wav"}).status_code, 413)

    def test_stt_blocks_overlapping_turns_and_end_waits_for_cleanup(self):
        entered, release = threading.Event(), threading.Event()

        def recognize(path):
            entered.set()
            release.wait(5)
            return TranscriptionResult("안녕", None, 0.1)

        with TestClient(create_app(transcriber=recognize), base_url="http://127.0.0.1") as client:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(client.post, "/api/transcribe", content=b"x", headers={"Content-Type": "audio/wav"})
                try:
                    self.assertTrue(entered.wait(3))
                    state = client.get("/api/state").json()
                    self.assertTrue(state["busy"])
                    self.assertEqual(state["stage"], "transcribing_audio")
                    self.assertEqual(client.post("/api/turn", json={"text": "안녕"}).status_code, 409)
                    self.assertEqual(client.post("/api/transcribe", content=b"x", headers={"Content-Type": "audio/wav"}).status_code, 409)
                    self.assertTrue(client.post("/api/end").json()["busy"])
                finally:
                    release.set()
                self.assertEqual(pending.result().status_code, 200)
            self.assertEqual(client.get("/api/state").json()["stage"], "ended")

    def test_foreign_origin_cannot_upload_audio(self):
        with TestClient(create_app(), base_url="http://127.0.0.1") as client:
            response = client.post("/api/transcribe", content=b"x", headers={"Content-Type": "audio/wav", "Origin": "https://example.com"})
            self.assertEqual(response.status_code, 403)
