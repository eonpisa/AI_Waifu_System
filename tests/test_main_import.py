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
                "backend.logging_setup.configure_console_logging",
                "backend.voice.tts.speak",
                "backend.voice.audio_playback.play_wav",
                "backend.character.vts.apply_expression",
                "backend.character.vts.prepare_lip_sync",
            )
            try:
                output, errors = io.StringIO(), io.StringIO()
                with contextlib.ExitStack() as stack:
                    calls = [stack.enter_context(patch(
                        target, side_effect=AssertionError("import side effect"),
                    )) for target in targets]
                    stack.enter_context(contextlib.redirect_stdout(output))
                    stack.enter_context(contextlib.redirect_stderr(errors))
                    from backend.conversation import service as conversation
                    import main
                    import backend.api.app
                    import backend.__main__
                    assert callable(conversation.create_session)
                    assert callable(conversation.process_turn)
                    assert callable(main.run_cli)
                    assert callable(backend.api.app.create_app)
                    assert callable(backend.__main__.run_api)
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

    def test_script_entry_point_starts_and_exits_with_original_prompts(self):
        result = subprocess.run(
            [sys.executable, "-B", "main.py"],
            cwd=Path(__file__).resolve().parents[1],
            input="\n종료\n", capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "초기 입력 버퍼 제거용. Enter를 눌러 시작: 너: 입력값: '종료'\n")
        self.assertEqual(result.stderr, "")
