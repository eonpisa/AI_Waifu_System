import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.voice.audio_playback import play_wav


class AudioPlaybackTests(unittest.TestCase):
    def test_missing_file_returns_false(self):
        self.assertFalse(play_wav("does-not-exist.wav"))

    def test_windows_uses_builtin_winsound(self):
        with TemporaryDirectory() as directory:
            wav = Path(directory) / "test.wav"
            wav.write_bytes(b"RIFFtest")
            with patch("backend.voice.audio_playback.platform.system", return_value="Windows"):
                with patch.dict("sys.modules", {"winsound": _Winsound()}):
                    self.assertTrue(play_wav(wav))


class _Winsound:
    SND_FILENAME = 0

    @staticmethod
    def PlaySound(*_):
        return None
