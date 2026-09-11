import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from backend.voice import tts


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return b"RIFFtest"


class SBV2TtsTests(unittest.TestCase):
    def test_sbv2_request_uses_selected_checkpoint_and_emotion_prompt(self):
        config = {
            "sbv2": {
                "api_url": "http://127.0.0.1:5000",
                "model_name": "Elaina_JPExtra",
                "model_file": "Elaina_JPExtra_e150_s187420.safetensors",
                "speaker_name": "Elaina",
                "emotion": {"happy": {"assist_text": "明るく話してください。"}},
            }
        }
        with patch("backend.voice.tts.urlopen", return_value=_Response()) as urlopen_mock:
            with patch("backend.voice.tts._write_wav_atomically", return_value=True):
                self.assertTrue(tts._speak_sbv2("こんにちは", 1.25, "happy", config))

        request = urlopen_mock.call_args.args[0]
        query = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(query["model_name"], ["Elaina_JPExtra"])
        self.assertEqual(query["model_file"], ["Elaina_JPExtra_e150_s187420.safetensors"])
        self.assertEqual(query["speaker_name"], ["Elaina"])
        self.assertEqual(query["assist_text"], ["明るく話してください。"])
        self.assertEqual(query["length"], ["0.8"])


if __name__ == "__main__":
    unittest.main()
