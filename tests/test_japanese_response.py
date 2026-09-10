import contextlib
import io
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

from japanese_response import (
    generate_validated_japanese_reply,
    is_valid_japanese_response,
    japanese_response_validation_reason,
)


class JapaneseResponseTests(unittest.TestCase):
    def test_rejects_japanese_followed_by_chinese_and_regenerates(self):
        replies = [
            "こんにちは！今日はいい天気ですね。是如何呢？天气不错吧？",
            "こんにちは！今日はいい天気ですね。",
        ]
        with patch("japanese_response.chat", side_effect=replies) as chat_mock:
            reply = generate_validated_japanese_reply([{"role": "user", "content": "こんにちは"}])
        self.assertEqual(reply, "こんにちは！今日はいい天気ですね。")
        self.assertEqual(chat_mock.call_count, 2)

    def test_rejects_english_chinese_and_italian_mixed_response(self):
        for reply in ("Hello、こんにちは", "你好、こんにちは", "Ciao、こんにちは"):
            self.assertFalse(is_valid_japanese_response(reply))

    def test_rejects_cyrillic_and_chinese_mixed_response(self):
        self.assertFalse(is_valid_japanese_response("こんにちは、сегодня мы будем casualです"))
        self.assertFalse(is_valid_japanese_response("こんにちは。不過請注意。"))

    def test_reports_specific_validation_reasons(self):
        self.assertEqual(japanese_response_validation_reason("안녕하세요"), "korean_text")
        self.assertEqual(japanese_response_validation_reason("Hello、こんにちは"), "latin_word")
        self.assertEqual(japanese_response_validation_reason("こんにちは。天气不错吧？"), "chinese_expression")
        self.assertEqual(japanese_response_validation_reason("Note: こんにちは"), "annotation")

    def test_accepts_normal_japanese_with_kanji(self):
        self.assertTrue(is_valid_japanese_response("今日は図書館で本を読みます。"))

    def test_two_invalid_responses_return_none_for_downstream_skip(self):
        history = [{"role": "user", "content": "こんにちは"}]
        with patch("japanese_response.chat", side_effect=["你好", "Note: こんにちは"]):
            self.assertIsNone(generate_validated_japanese_reply(history))
        self.assertEqual(history, [{"role": "user", "content": "こんにちは"}])

    def test_logs_each_rejected_generation_and_reason_at_debug_level(self):
        with patch("japanese_response.chat", side_effect=["Hello、こんにちは", "Note: こんにちは"]):
            with self.assertLogs("japanese_response", level="DEBUG") as logs:
                self.assertIsNone(generate_validated_japanese_reply([]))
        joined = "\n".join(logs.output)
        self.assertNotIn("Hello、こんにちは", joined)
        self.assertIn("Validation reason (initial generation): latin_word", joined)
        self.assertNotIn("Note: こんにちは", joined)
        self.assertIn("Validation reason (regeneration): annotation", joined)

    def test_request_error_does_not_log_exception_contents(self):
        with patch("japanese_response.chat", side_effect=RuntimeError("private headers and response")):
            with self.assertLogs("japanese_response", level="DEBUG") as logs:
                self.assertIsNone(generate_validated_japanese_reply([]))
        self.assertNotIn("private headers and response", "\n".join(logs.output))

    def run_main_dialogue(self, replies):
        from translator import KoreanInputTranslation

        translated = [
            KoreanInputTranslation("ok", "힘들었어", "私は疲れました。"),
            KoreanInputTranslation("ok", "내일 산책할 거야", "私は明日散歩します。"),
        ]
        with patch("logging_setup.configure_console_logging"), patch("builtins.input", side_effect=["", "힘들었어", "내일 산책할 거야", "종료"]):
            with patch("translator.translate_korean_input", side_effect=translated):
                with patch("translator.japanese_to_korean", return_value="알겠어요") as subtitle:
                    with patch("japanese_response.chat", side_effect=replies) as chat:
                        with patch("tts.speak", return_value=False) as speak:
                            with contextlib.redirect_stdout(io.StringIO()):
                                state = runpy.run_path(str(Path(__file__).resolve().parents[1] / "main.py"), run_name="__main__")
        return state, chat, subtitle, speak

    def test_main_preserves_roles_and_applies_only_current_style_on_retry(self):
        state, chat, _, _ = self.run_main_dialogue(["少し休んでね。", "Hello", "散歩を楽しんでね。"])
        first, second, retry = [call.args[0] for call in chat.call_args_list]
        self.assertEqual([m["role"] for m in second], ["system", "user", "assistant", "user"])
        self.assertEqual([m["content"] for m in second[1:]], ["私は疲れました。", "少し休んでね。", "私は明日散歩します。"])
        self.assertIn(state["emotion_style"]["sad"], first[0]["content"])
        self.assertNotIn(state["emotion_style"]["sad"], second[0]["content"])
        self.assertIn(state["emotion_style"]["normal"], second[0]["content"])
        self.assertEqual(retry[:-1], second)
        self.assertEqual(retry[-1]["role"], "system")
        self.assertNotIn("今回の口調", state["messages"][0]["content"])
        self.assertEqual([m["role"] for m in state["messages"]], ["system", "user", "assistant", "user", "assistant"])

    def test_main_rejected_reply_does_not_leave_failed_user_or_invalid_answer_in_history(self):
        state, chat, subtitle, speak = self.run_main_dialogue(["Hello", "Note: invalid", "散歩を楽しんでね。"])
        self.assertEqual(chat.call_args.args[0][1:], [{"role": "user", "content": "私は明日散歩します。"}])
        self.assertEqual(state["messages"][1:], [
            {"role": "user", "content": "私は明日散歩します。"},
            {"role": "assistant", "content": "散歩を楽しんでね。"},
        ])
        self.assertEqual(subtitle.call_count, 1)
        self.assertEqual(speak.call_count, 1)
