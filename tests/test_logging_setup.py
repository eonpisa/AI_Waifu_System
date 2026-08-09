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

    def test_debug_mode_prints_validation_details_once(self):
        with patch.dict(os.environ, {"AI_WAIFU_DEBUG": "1"}, clear=False):
            configure_console_logging()
            configure_console_logging()
            logger = logging.getLogger("japanese_response")
            logger.debug("Rejected AI response (initial generation): 'bad reply'")
            logger.debug("Validation reason (initial generation): latin_word")

        output = self.stream.getvalue()
        self.assertEqual(len(self.root.handlers), 1)
        self.assertEqual(output.count("Rejected AI response"), 1)
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
        self.assertIn("Rejected AI response (initial generation): 'Hello、こんにちは'", output)
        self.assertIn("Validation reason (initial generation): latin_word", output)
        self.assertIn("Rejected AI response (regeneration): 'Note: こんにちは'", output)
        self.assertIn("Validation reason (regeneration): annotation", output)

    def test_default_mode_hides_debug_logs(self):
        with patch.dict(os.environ, {"AI_WAIFU_DEBUG": "0"}, clear=False):
            configure_console_logging()
            logging.getLogger("japanese_response").debug("hidden debug response")
            logging.getLogger("japanese_response").warning("visible warning")

        output = self.stream.getvalue()
        self.assertNotIn("hidden debug response", output)
        self.assertIn("visible warning", output)
