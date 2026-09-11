import unittest

from backend.subtitle_ui import format_korean_subtitle


class SubtitleUiTests(unittest.TestCase):
    def test_failed_translation_does_not_label_japanese_as_korean_subtitle(self):
        self.assertEqual(format_korean_subtitle(None), "자막 번역에 실패했습니다.")

    def test_successful_translation_keeps_korean_subtitle_label(self):
        self.assertEqual(format_korean_subtitle("안녕하세요."), "자막 (KO): 안녕하세요.")
