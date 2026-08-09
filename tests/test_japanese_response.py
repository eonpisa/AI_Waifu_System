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
        self.assertIn("Rejected AI response (initial generation)", joined)
        self.assertIn("Validation reason (initial generation): latin_word", joined)
        self.assertIn("Rejected AI response (regeneration)", joined)
        self.assertIn("Validation reason (regeneration): annotation", joined)
