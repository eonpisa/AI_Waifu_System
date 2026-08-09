import json
import os
import unittest
from unittest.mock import patch

from requests.exceptions import ReadTimeout

import translator


def json_translation(value):
    return json.dumps({"translation": value}, ensure_ascii=False)


def json_korean_input(status, normalized_source, translation):
    return json.dumps(
        {
            "status": status,
            "normalized_source": normalized_source,
            "translation": translation,
        },
        ensure_ascii=False,
    )


class TranslatorTests(unittest.TestCase):
    def test_japanese_input_skips_translation(self):
        with patch("translator.chat") as chat_mock:
            result = translator.translate_korean_input("こんにちは")
        self.assertEqual(result.translation, "こんにちは")
        chat_mock.assert_not_called()

    def test_typo_is_normalized_before_japanese_translation(self):
        response = json_korean_input("ok", "안녕", "こんにちは")
        with patch("translator.chat", return_value=response):
            result = translator.translate_korean_input("안ㄴ여")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.normalized_source, "안녕")
        self.assertEqual(result.translation, "こんにちは")

    def test_clear_greeting_misrecognitions_are_corrected(self):
        for source in ("안녀", "아녕"):
            with self.subTest(source=source):
                response = json_korean_input("ok", "안녕", "こんにちは")
                with patch("translator.chat", return_value=response):
                    result = translator.translate_korean_input(source)
                self.assertEqual(result.normalized_source, "안녕")
                self.assertEqual(result.translation, "こんにちは")

    def test_normal_greeting_is_not_rewritten(self):
        response = json_korean_input("ok", "안녕", "こんにちは")
        with patch("translator.chat", return_value=response):
            result = translator.translate_korean_input("안녕")
        self.assertEqual(result.normalized_source, "안녕")
        self.assertEqual(result.translation, "こんにちは")

    def test_normal_greeting_rewritten_to_a_different_tone_is_rejected(self):
        invalid = json_korean_input("ok", "안녕하세요", "こんにちは")
        with patch("translator.chat", side_effect=[invalid, invalid]):
            self.assertIsNone(translator.translate_korean_input("안녕"))

    def test_greeting_changed_to_ohayou_is_rejected(self):
        invalid = json_korean_input("ok", "안녕", "おはよう")
        with patch("translator.chat", side_effect=[invalid, invalid]):
            self.assertIsNone(translator.translate_korean_input("안녕"))

    def test_short_but_clear_inputs_are_accepted(self):
        for source, japanese in (("응", "うん"), ("왜?", "どうして？")):
            with self.subTest(source=source):
                response = json_korean_input("ok", source, japanese)
                with patch("translator.chat", return_value=response):
                    result = translator.translate_korean_input(source)
                self.assertEqual(result.translation, japanese)

    def test_long_spacing_and_duplicate_character_correction_is_accepted(self):
        source = "오늘 은 날씨가  너무 너무좋아서 산책하고싶어"
        normalized = "오늘은 날씨가 너무 좋아서 산책하고 싶어"
        response = json_korean_input("ok", normalized, "今日は天気がとてもいいから散歩したい")
        with patch("translator.chat", return_value=response):
            result = translator.translate_korean_input(source)
        self.assertEqual(result.normalized_source, normalized)

    def test_ambiguous_input_is_not_translated(self):
        response = json_korean_input("ambiguous", "그거", "")
        with patch("translator.chat", return_value=response) as chat_mock:
            result = translator.translate_korean_input("그거")
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.translation)
        self.assertEqual(chat_mock.call_count, 1)

    def test_protected_character_name_is_not_rewritten(self):
        source = "일레이나에게 인사해 줘"
        response = json_korean_input("ok", source, "イレイナに挨拶して")
        with patch("translator.chat", return_value=response):
            result = translator.translate_korean_input(source)
        self.assertEqual(result.normalized_source, source)

    def test_character_name_uses_canonical_korean_to_japanese_spelling(self):
        source = "일레이나랑 이야기하고 싶어"
        response = json_korean_input("ok", source, "イレイナと話したいです")
        with patch("translator.chat", return_value=response):
            result = translator.translate_korean_input(source)
        self.assertEqual(result.translation, "イレイナと話したいです")

    def test_incorrect_character_name_spelling_is_rejected(self):
        source = "일레이나랑 이야기하고 싶어"
        invalid = json_korean_input("ok", source, "イルイナと話したいです")
        with patch("translator.chat", side_effect=[invalid, invalid]):
            self.assertIsNone(translator.translate_korean_input(source))

    def test_korean_input_uses_input_schema_and_translation_model(self):
        response = json_korean_input("ok", "안녕하세요", "こんにちは")
        with patch("translator.chat", return_value=response) as chat_mock:
            translator.translate_korean_input("안녕하세요")
        self.assertEqual(chat_mock.call_args.kwargs["model"], translator.TRANSLATOR_MODEL)
        self.assertEqual(chat_mock.call_args.kwargs["temperature"], translator.TRANSLATOR_TEMPERATURE)
        self.assertEqual(chat_mock.call_args.kwargs["response_format"], translator.KOREAN_INPUT_SCHEMA)

    def test_korean_to_japanese_retries_note_and_parenthetical_output(self):
        invalid = json_korean_input("ok", "안녕하세요", "Note: こんにちは (説明)")
        valid = json_korean_input("ok", "안녕하세요", "こんにちは。")
        with patch("translator.chat", side_effect=[invalid, valid]) as chat_mock:
            self.assertEqual(translator.korean_to_japanese("안녕하세요"), "こんにちは。")
        self.assertEqual(chat_mock.call_count, 2)

    def test_korean_input_rejects_missing_or_extra_json_fields(self):
        invalid = json.dumps({"status": "ok", "translation": "こんにちは"})
        with patch("translator.chat", side_effect=[invalid, invalid]):
            self.assertIsNone(translator.translate_korean_input("안녕하세요"))

    def test_subtitle_retries_japanese_and_note_mixed_output(self):
        outputs = [json_translation("Note: こんにちは"), json_translation("안녕하세요")]
        with patch("translator.chat", side_effect=outputs) as chat_mock:
            self.assertEqual(translator.japanese_to_korean("こんにちは"), "안녕하세요")
        self.assertEqual(chat_mock.call_count, 2)

    def test_subtitle_rejects_truncated_long_korean_output(self):
        source = "これは長い説明文です。大切な条件と理由をすべて含めて、自然な文章として伝えてください。"
        outputs = [json_translation("좋아요"), json_translation("확인했습니다")]
        with patch("translator.chat", side_effect=outputs):
            self.assertIsNone(translator.japanese_to_korean(source))

    def test_subtitle_rejects_first_part_only_for_multi_sentence_source(self):
        source = "\u3053\u3093\u306b\u3061\u306f\u3002\u4eca\u65e5\u306f\u3044\u3044\u5929\u6c17\u3067\u3059\u306d\u3002\u660e\u65e5\u3082\u6563\u6b69\u306b\u884c\u304d\u307e\u3057\u3087\u3046\u3002"
        outputs = [
            json_translation("\uc548\ub155\ud558\uc138\uc694. \uc624\ub298 \ub0a0\uc528\uac00 \uc88b\ub124\uc694."),
            json_translation("\uc548\ub155\ud558\uc138\uc694. \uc624\ub298 \ub0a0\uc528\uac00 \uc88b\ub124\uc694."),
        ]
        with patch("translator.chat", side_effect=outputs):
            self.assertIsNone(translator.japanese_to_korean(source))

    def test_subtitle_uses_source_after_two_invalid_results(self):
        with patch("translator.chat", side_effect=[json_translation("你好。"), json_translation("こんにちは")]):
            self.assertIsNone(translator.japanese_to_korean("こんにちは"))

    def test_japanese_character_name_is_mapped_to_korean_before_validation(self):
        source = "イレイナとしてお話ししましょう。"
        response = json_translation("물론이에요. \u30a4\u30ec\u30a4\u30ca로서 이야기해 드릴게요.")
        with patch("translator.chat", return_value=response):
            result = translator.japanese_to_korean(source)
        self.assertEqual(result, "물론이에요. 일레이나로서 이야기해 드릴게요.")

    def test_normal_japanese_to_korean_translation_succeeds(self):
        response = json_translation("물론이에요. 무엇에 관해 이야기하고 싶으신가요?")
        with patch("translator.chat", return_value=response):
            result = translator.japanese_to_korean("もちろんです。何について話したいですか？")
        self.assertEqual(result, "물론이에요. 무엇에 관해 이야기하고 싶으신가요?")

    def test_mixed_japanese_korean_subtitle_is_regenerated_from_full_source(self):
        source = "もちろんです、何でもお話ししましょう。今日どんなことについて話したいですか？"
        mixed = "もちろん요, 무엇이든 이야기해도 좋습니다. 오늘 어떤 주제로 이야기하고 싶으신가요?"
        complete = "물론이에요. 무엇이든 이야기해요. 오늘 어떤 주제에 관해 이야기하고 싶으신가요?"
        with patch("translator.chat", side_effect=[json_translation(mixed), json_translation(complete)]) as chat_mock:
            self.assertEqual(translator.japanese_to_korean(source), complete)
        retry_messages = chat_mock.call_args.args[0]
        retry_prompt = retry_messages[0]["content"]
        self.assertIn(source, retry_prompt)
        self.assertIn(mixed, retry_prompt)
        self.assertIn("japanese_character:も", retry_prompt)
        self.assertIn("do not copy, patch, shorten, or partially edit", retry_prompt)

    def test_japanese_to_korean_requests_are_isolated_and_debuggable(self):
        source = "もちろんです。"
        mixed = "もちろん요"
        valid = "물론이에요."
        env = {"AI_WAIFU_DEBUG": "1", "OLLAMA_JA_TO_KO_MODEL": "subtitle-model"}
        with patch.dict(os.environ, env, clear=False):
            with patch("translator.chat", side_effect=[json_translation(mixed), json_translation(valid)]) as chat_mock:
                with self.assertLogs("translator", level="DEBUG") as logs:
                    self.assertEqual(translator.japanese_to_korean(source), valid)
        first_messages = chat_mock.call_args_list[0].args[0]
        retry_messages = chat_mock.call_args_list[1].args[0]
        self.assertIsNot(first_messages, retry_messages)
        self.assertEqual([message["role"] for message in first_messages], ["system", "user"])
        self.assertEqual([message["role"] for message in retry_messages], ["system", "user"])
        self.assertEqual(first_messages[1]["content"], source)
        self.assertEqual(chat_mock.call_args_list[0].kwargs["model"], "subtitle-model")
        self.assertEqual(chat_mock.call_args_list[0].kwargs["temperature"], translator.JA_TO_KO_TEMPERATURE)
        self.assertEqual(chat_mock.call_args_list[1].kwargs["temperature"], translator.JA_TO_KO_RETRY_TEMPERATURE)
        joined = "\n".join(logs.output)
        self.assertIn("stage=initial generation model=subtitle-model", joined)
        self.assertIn("stage=regeneration model=subtitle-model", joined)
        self.assertIn("conversation_history_included=False", joined)
        self.assertIn("roles=['system', 'user']", joined)

    def test_japanese_to_korean_uses_translation_model_when_dedicated_model_is_unset(self):
        with patch.dict(os.environ, {"OLLAMA_JA_TO_KO_MODEL": ""}, clear=False):
            self.assertEqual(translator._ja_to_ko_model(), translator.TRANSLATOR_MODEL)

    def test_dedicated_japanese_to_korean_model_failure_does_not_switch_models(self):
        with patch.dict(os.environ, {"OLLAMA_JA_TO_KO_MODEL": "missing-subtitle-model"}, clear=False):
            with patch("translator.chat", side_effect=ConnectionError("model unavailable")) as chat_mock:
                self.assertIsNone(translator.japanese_to_korean("こんにちは"))
        self.assertEqual(chat_mock.call_count, 2)
        self.assertEqual(
            [call.kwargs["model"] for call in chat_mock.call_args_list],
            ["missing-subtitle-model", "missing-subtitle-model"],
        )

    def test_two_mixed_language_subtitles_fail_without_japanese_fallback(self):
        mixed = "もちろん요, 무엇이든 이야기해도 좋습니다."
        with patch("translator.chat", side_effect=[json_translation(mixed), json_translation(mixed)]):
            self.assertIsNone(translator.japanese_to_korean("もちろんです、何でもお話ししましょう。"))

    def test_korean_input_timeout_is_distinct_and_retries_once(self):
        valid = json_korean_input("ok", "일레이나랑 이야기하고 싶어", "イレイナと話したいです")
        with patch("translator.chat", side_effect=[ReadTimeout("read timeout"), valid]) as chat_mock:
            result = translator.translate_korean_input("일레이나랑 이야기하고 싶어")
        self.assertEqual(result.translation, "イレイナと話したいです")
        self.assertEqual(chat_mock.call_count, 2)
        self.assertEqual(chat_mock.call_args.kwargs["timeout"], translator.TRANSLATION_TIMEOUT_SECONDS)

    def test_japanese_to_korean_debug_logs_raw_output_and_reason_for_both_attempts(self):
        outputs = [json_translation("Note: こんにちは"), json_translation("Hello")]
        with patch.dict(os.environ, {"AI_WAIFU_DEBUG": "1"}, clear=False):
            with patch("translator.chat", side_effect=outputs):
                with self.assertLogs("translator", level="DEBUG") as logs:
                    self.assertIsNone(translator.japanese_to_korean("こんにちは"))
        joined = "\n".join(logs.output)
        self.assertIn("Rejected ja_to_ko translation (initial generation)", joined)
        self.assertIn("Validation reason (initial generation): japanese_character", joined)
        self.assertIn("Rejected ja_to_ko translation (regeneration)", joined)
        self.assertIn("Validation reason (regeneration): english_word:Hello", joined)
