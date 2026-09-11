"""Regressions caused by moving the shared runtime into backend packages."""

import io
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

from backend.voice import tts


ROOT = Path(__file__).resolve().parents[1]


class PackageLayoutTests(unittest.TestCase):
    def test_default_tts_config_and_output_still_resolve_to_project_root(self):
        # Never read or modify the user's real TTS configuration/WAV.
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(Path, "is_file", return_value=True):
                with patch.object(Path, "open", autospec=True,
                                  return_value=io.StringIO('{"backend":"sbv2"}')) as opened:
                    self.assertEqual(tts._read_config(), {"backend": "sbv2"})
        self.assertEqual(opened.call_args.args[0], ROOT / "tts_config.json")
        self.assertEqual(tts.PROJECT_ROOT, ROOT)
        self.assertEqual(tts.OUTPUT_PATH, ROOT / "output.wav")

    def test_cli_does_not_import_api_or_optional_training_and_legacy_sdks(self):
        probe = textwrap.dedent('''
            import builtins
            import sys
            original = builtins.__import__
            forbidden = {
                "fastapi", "uvicorn", "pydantic", "openai", "torch",
                "torchaudio", "datasets", "soundfile", "cosyvoice",
            }
            def guarded(name, *args, **kwargs):
                if name.split(".")[0] in forbidden:
                    raise AssertionError("unnecessary dependency imported")
                return original(name, *args, **kwargs)
            builtins.__import__ = guarded
            try:
                import main
                assert callable(main.run_cli)
                assert not any(name.split(".")[0] in forbidden for name in sys.modules)
            except Exception:
                print("CLI package isolation failed", file=sys.stderr)
                sys.exit(1)
        ''')
        result = subprocess.run([sys.executable, "-B", "-c", probe], cwd=ROOT,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
