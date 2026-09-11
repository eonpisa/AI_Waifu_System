"""Exercise the shared turn directly without console input or live services."""

import contextlib
import io
import unittest
from unittest.mock import Mock, patch

from backend.conversation import service as conversation
from backend.translation.translator import KoreanInputTranslation


class ConversationTests(unittest.TestCase):
    @contextlib.contextmanager
    def services(self, translation=None, reply="試験お疲れ様でした。", subtitle="시험 수고했어요.", synth=True, play=True):
        if translation is None:
            translation = KoreanInputTranslation("ok", "시험을 봤어", "試験を受けました。")
        with contextlib.ExitStack() as stack:
            calls = Mock()
            for name, target, value in (
                ("translate", "backend.translation.translator.translate_korean_input", translation),
                ("reply", "backend.conversation.japanese_response.generate_validated_japanese_reply", reply),
                ("subtitle", "backend.translation.translator.japanese_to_korean", subtitle),
                ("synthesize", "backend.voice.tts.speak", synth),
                ("play", "backend.conversation.service.play_with_expression", play),
            ):
                mock = stack.enter_context(patch(target, return_value=value))
                calls.attach_mock(mock, name)
            yield calls

    def test_success_without_console_returns_result_events_and_japanese_history(self):
        session = conversation.create_session()
        events, output = [], io.StringIO()
        with self.services() as calls, patch("builtins.input", side_effect=AssertionError("console input")), contextlib.redirect_stdout(output):
            result = conversation.process_turn(session, "시험을 봤어", emit=events.append)
        self.assertEqual(result.status, "completed")
        self.assertTrue(result.audio_played)
        self.assertEqual(result.errors, ())
        self.assertEqual(result.japanese_reply, "試験お疲れ様でした。")
        self.assertEqual(result.korean_subtitle, "시험 수고했어요.")
        self.assertEqual(output.getvalue(), "")
        self.assertEqual([c[0] for c in calls.mock_calls], ["translate", "reply", "subtitle", "synthesize", "play"])
        self.assertEqual([e.kind for e in events], [
            "stage_changed", "input_translated", "stage_changed", "reply_ready",
            "stage_changed", "subtitle_ready", "tts_prepared", "stage_changed", "stage_changed",
        ])
        self.assertEqual([e.data["stage"] for e in events if e.kind == "stage_changed"], [
            "translating_input", "generating", "translating_subtitle", "synthesizing", "speaking",
        ])
        self.assertEqual(events[1].data["japanese_input"], "試験を受けました。")
        self.assertEqual(session.messages[1:], [
            {"role": "user", "content": "試験を受けました。"},
            {"role": "assistant", "content": "試験お疲れ様でした。"},
        ])

    def test_empty_input_does_not_call_services(self):
        session = conversation.create_session()
        with self.services() as calls:
            result = conversation.process_turn(session, "  ")
        self.assertEqual(result.errors, ("empty_input",))
        self.assertEqual(calls.mock_calls, [])
        self.assertEqual(len(session.messages), 1)

    def test_input_failure_or_ambiguity_keeps_history_and_skips_downstream(self):
        for translated, error in [(None, "input_translation_failed"), (KoreanInputTranslation("ambiguous", "애매해", None), "ambiguous_input")]:
            with self.subTest(error=error):
                session = conversation.create_session()
                events = []
                with self.services() as calls:
                    calls.translate.return_value = translated
                    result = conversation.process_turn(session, "애매해", emit=events.append)
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.errors, (error,))
                self.assertEqual([c[0] for c in calls.mock_calls], ["translate"])
                self.assertEqual(len(session.messages), 1)
                self.assertEqual(events[-1].data["code"], error)

    def test_invalid_reply_rolls_back_only_current_user_turn(self):
        session = conversation.create_session()
        with self.services():
            conversation.process_turn(session, "시험을 봤어")
        original = [dict(message) for message in session.messages]
        with self.services(reply=None) as calls:
            result = conversation.process_turn(session, "시험을 봤어")
        self.assertEqual(result.errors, ("japanese_reply_failed",))
        self.assertEqual(session.messages, original)
        calls.subtitle.assert_not_called()
        calls.synthesize.assert_not_called()
        calls.play.assert_not_called()

    def test_subtitle_failure_keeps_audio_and_history(self):
        session = conversation.create_session()
        with self.services(subtitle=None) as calls:
            result = conversation.process_turn(session, "시험을 봤어")
        self.assertEqual(result.status, "partial_failure")
        self.assertEqual(result.errors, ("subtitle_failed",))
        self.assertTrue(result.audio_played)
        calls.play.assert_called_once()
        self.assertEqual(session.messages[-1]["role"], "assistant")

    def test_synthesis_failure_skips_playback_and_preserves_valid_reply(self):
        session = conversation.create_session()
        with self.services(synth=False) as calls:
            result = conversation.process_turn(session, "시험을 봤어")
        self.assertEqual(result.status, "partial_failure")
        self.assertEqual(result.errors, ("synthesis_failed",))
        self.assertFalse(result.audio_played)
        calls.play.assert_not_called()
        self.assertEqual(session.messages[-1]["content"], result.japanese_reply)

    def test_playback_failure_is_reported_and_next_turn_can_run(self):
        session = conversation.create_session()
        with self.services(play=False), self.assertLogs(level="ERROR"):
            failed = conversation.process_turn(session, "시험을 봤어")
        with self.services():
            following = conversation.process_turn(session, "시험을 봤어")
        self.assertEqual(failed.errors, ("playback_failed",))
        self.assertEqual(following.status, "completed")
        self.assertEqual(len(session.messages), 5)

    def test_history_limit_and_reset_apply_to_actual_next_request(self):
        session = conversation.create_session()
        system = session.messages[0]["content"]
        with self.services() as calls:
            for i in range(8):
                calls.translate.return_value = KoreanInputTranslation("ok", str(i), f"発言{i}。")
                conversation.process_turn(session, str(i))
            self.assertEqual(len(session.messages), conversation.MAX_HISTORY + 1)
            self.assertEqual(session.messages[1]["content"], "発言2。")
            self.assertEqual(session.messages[0]["content"], system)
            session.reset()
            conversation.process_turn(session, "새 대화")
        request = calls.reply.call_args.args[0]
        self.assertEqual([m["role"] for m in request], ["system", "user"])
        self.assertEqual(len(session.messages), 3)

    def test_new_cli_session_does_not_inherit_previous_run_history(self):
        first = conversation.create_session()
        with self.services():
            conversation.process_turn(first, "시험을 봤어")
        second = conversation.create_session()
        self.assertEqual(len(second.messages), 1)
        self.assertEqual(second.messages[0], first.messages[0])
        self.assertIsNot(second.messages[0], first.messages[0])
