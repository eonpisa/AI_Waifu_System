"""The optional STT adapter never downloads a model or changes conversation state."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.voice import stt


class STTTests(unittest.TestCase):
    def setUp(self):
        self.decoder = patch.object(stt, "_decode_audio", return_value=[0.1])
        self.decoder.start()
        self.addCleanup(self.decoder.stop)

    def test_missing_audio_and_model_return_safe_codes_without_loading(self):
        with TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            with patch.object(stt, "_load_model") as load:
                self.assertEqual(stt.transcribe_file(audio).error, "audio_missing")
                audio.write_bytes(b"sample")
                with patch.dict(os.environ, {}, clear=True):
                    self.assertEqual(stt.transcribe_file(audio).error, "model_not_configured")
                self.assertEqual(stt.transcribe_file(audio, model_path=Path(folder) / "absent").error,
                                 "model_missing")
                load.assert_not_called()

    def test_large_audio_is_rejected_before_model_load(self):
        with TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            with audio.open("wb") as stream:
                stream.truncate(stt.MAX_AUDIO_BYTES + 1)
            with patch.object(stt, "_load_model") as load:
                self.assertEqual(stt.transcribe_file(audio, model_path=folder).error,
                                 "audio_too_large")
                load.assert_not_called()

    def test_korean_transcription_uses_local_model_without_touching_session(self):
        with TemporaryDirectory() as folder:
            audio = Path(folder) / "sample.wav"
            audio.write_bytes(b"sample")
            calls = []

            class FakeModel:
                def transcribe(self, path, **options):
                    calls.append((path, options))
                    return iter([SimpleNamespace(text=" 안녕하세요. "),
                                 SimpleNamespace(text=" 오늘은 괜찮아요. ")]), None

            with patch.object(stt, "_load_model", return_value=FakeModel()) as load:
                output = stt.transcribe_file(audio, model_path=folder)
            self.assertEqual(output.text, "안녕하세요. 오늘은 괜찮아요.")
            self.assertIsNone(output.error)
            self.assertGreaterEqual(output.elapsed_seconds, 0)
            load.assert_called_once_with(folder)
            self.assertEqual(calls, [([0.1], {
                "language": "ko", "task": "transcribe", "beam_size": 3,
                "vad_filter": True, "condition_on_previous_text": False,
            })])

    def test_silence_and_failures_do_not_expose_audio_or_model_paths(self):
        with TemporaryDirectory() as folder:
            audio = Path(folder) / "private-utterance.wav"
            audio.write_bytes(b"sample")

            class SilentModel:
                def transcribe(self, *_args, **_kwargs):
                    return iter([SimpleNamespace(text="  ")]), None

            with patch.object(stt, "_load_model", return_value=SilentModel()):
                self.assertEqual(stt.transcribe_file(audio, model_path=folder).error, "no_speech")
            with patch.object(stt, "_load_model", side_effect=ImportError("private dependency detail")):
                output = stt.transcribe_file(audio, model_path=folder)
                self.assertEqual(output.error, "dependency_missing")
                self.assertNotIn(folder, repr(output))
            with patch.object(stt, "_load_model", side_effect=RuntimeError("private model detail")):
                output = stt.transcribe_file(audio, model_path=folder)
                self.assertEqual(output.error, "transcription_failed")
                self.assertNotIn(folder, repr(output))

    def test_loader_disables_download_and_uses_cpu(self):
        import sys
        fake = SimpleNamespace(WhisperModel=unittest.mock.Mock())
        stt._load_model.cache_clear()
        with patch.dict(sys.modules, {"faster_whisper": fake}):
            stt._load_model("/local/private/model")
        fake.WhisperModel.assert_called_once_with(
            "/local/private/model", device="cpu", compute_type="int8", local_files_only=True)
        stt._load_model.cache_clear()

    def test_real_decoder_bounds_duration_and_does_not_load_long_audio(self):
        import wave
        try:
            import av  # noqa: F401
        except ImportError:
            self.skipTest("optional STT decoder not installed")
        self.decoder.stop()
        with TemporaryDirectory() as folder:
            audio = Path(folder) / "long.wav"
            with wave.open(str(audio), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(b"\0\0" * 16000 * 31)
            with patch.object(stt, "_load_model") as load:
                self.assertEqual(stt.transcribe_file(audio, model_path=folder).error, "audio_too_long")
                load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
