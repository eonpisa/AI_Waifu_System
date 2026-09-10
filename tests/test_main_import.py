"""Importing the CLI must be safe for a future Python API entry point."""

from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


class MainImportTests(unittest.TestCase):
    def test_fresh_import_has_no_input_network_playback_or_worker_side_effects(self):
        probe = textwrap.dedent('''
            import contextlib
            import io
            import sys
            from unittest.mock import patch

            targets = (
                "builtins.input",
                "socket.socket.connect",
                "socket.socket.connect_ex",
                "subprocess.Popen",
                "threading.Thread.start",
                "requests.sessions.Session.request",
                "logging_setup.configure_console_logging",
                "tts.speak",
                "audio_playback.play_wav",
                "vts.apply_expression",
                "vts.prepare_lip_sync",
            )
            try:
                output, errors = io.StringIO(), io.StringIO()
                with contextlib.ExitStack() as stack:
                    calls = [stack.enter_context(patch(
                        target, side_effect=AssertionError("import side effect"),
                    )) for target in targets]
                    stack.enter_context(contextlib.redirect_stdout(output))
                    stack.enter_context(contextlib.redirect_stderr(errors))
                    import main
                    assert callable(main.run_cli)
                    for call in calls:
                        call.assert_not_called()
                    assert output.getvalue() == ""
                    assert errors.getvalue() == ""
            except Exception as exc:
                # Keep probe failures independent of request/credential contents.
                print(type(exc).__name__, file=sys.stderr)
                sys.exit(1)
        ''')
        result = subprocess.run(
            [sys.executable, "-B", "-c", probe],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
