import io
import logging
import os
import unittest
from unittest.mock import patch

from logging_setup import configure_console_logging


class LoggingSetupTests(unittest.TestCase):
    def setUp(self):
        self.root = logging.getLogger()
        self.original_level = self.root.level
        self.original_handlers = list(self.root.handlers)
        self.original_child_levels = {
            name: logging.getLogger(name).level
            for name in ("translator", "japanese_response", "urllib3")
        }
        for handler in self.root.handlers[:]:
            self.root.removeHandler(handler)
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.root.addHandler(self.handler)

    def tearDown(self):
        for handler in self.root.handlers[:]:
            self.root.removeHandler(handler)
        for handler in self.original_handlers:
            self.root.addHandler(handler)
        self.root.setLevel(self.original_level)
        for name, level in self.original_child_levels.items():
            logging.getLogger(name).setLevel(level)

    def test_debug_mode_prints_validation_details_once(self):
        with patch.dict(os.environ, {"AI_WAIFU_DEBUG": "1"}, clear=False):
            configure_console_logging()
            configure_console_logging()
            logger = logging.getLogger("japanese_response")
            logger.debug("Validation reason (initial generation): latin_word")

        output = self.stream.getvalue()
        self.assertEqual(len(self.root.handlers), 1)
        self.assertEqual(output.count("Validation reason"), 1)
        self.assertIn("Validation reason (initial generation): latin_word", output)

    def test_debug_mode_overrides_existing_warning_handler_for_real_validation(self):
        from japanese_response import generate_validated_japanese_reply

        self.handler.setLevel(logging.WARNING)
        with patch.dict(os.environ, {"AI_WAIFU_DEBUG": "1"}, clear=False):
            with patch("japanese_response.chat", side_effect=["Hello、こんにちは", "Note: こんにちは"]):
                configure_console_logging()
                self.assertEqual(self.handler.level, logging.DEBUG)
                self.assertEqual(logging.getLogger("japanese_response").level, logging.DEBUG)
                self.assertEqual(logging.getLogger("urllib3").level, logging.WARNING)
                self.assertIsNone(generate_validated_japanese_reply([]))

        output = self.stream.getvalue()
        self.assertNotIn("Hello、こんにちは", output)
        self.assertIn("Validation reason (initial generation): latin_word", output)
        self.assertNotIn("Note: こんにちは", output)
        self.assertIn("Validation reason (regeneration): annotation", output)

    def test_default_mode_hides_debug_logs(self):
        with patch.dict(os.environ, {"AI_WAIFU_DEBUG": "0"}, clear=False):
            configure_console_logging()
            logging.getLogger("japanese_response").debug("hidden debug response")
            logging.getLogger("japanese_response").warning("visible warning")

        output = self.stream.getvalue()
        self.assertNotIn("hidden debug response", output)
        self.assertIn("visible warning", output)

    def test_default_mode_shows_accepted_gemini_provider_once_without_debug(self):
        import gemini_translator
        from translator import japanese_to_korean

        self.handler.setLevel(logging.WARNING)
        result = gemini_translator.GeminiTranslationResult("안녕하세요", "private raw response", None)
        with patch.dict(os.environ, {"AI_WAIFU_DEBUG": "0"}, clear=False):
            with patch("translator.gemini_japanese_to_korean", return_value=result), patch("translator.chat") as chat_mock:
                configure_console_logging()
                configure_console_logging()
                self.assertEqual(japanese_to_korean("こんにちは"), "안녕하세요")
                logging.getLogger("translator").debug("hidden raw response")
                logging.getLogger("urllib3").info("hidden HTTP details")
        chat_mock.assert_not_called()
        output = self.stream.getvalue()
        self.assertEqual(len(self.root.handlers), 1)
        self.assertEqual(output.count("JA->KO provider=gemini"), 1)
        self.assertIn(f"model={gemini_translator.GEMINI_TRANSLATOR_MODEL} fallback_reason=none", output)
        for private_text in ("こんにちは", "안녕하세요", "private raw response", "hidden raw response", "hidden HTTP details"):
            self.assertNotIn(private_text, output)
