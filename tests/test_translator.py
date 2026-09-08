import json
import os
import unittest
from unittest.mock import Mock, patch

from requests.exceptions import HTTPError, ReadTimeout, RequestException

import gemini_translator
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


def gemini_response(translation):
    response = Mock()
    response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json_translation(translation)}],
                }
            }
        ]
    }
    return response


class TranslatorTests(unittest.TestCase):
    def setUp(self):
        self.gemini_env = patch.dict(
            os.environ, {"GEMINI_API_KEY": ""}, clear=False
        )
        self.gemini_env.start()
        self.addCleanup(self.gemini_env.stop)

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

    def test_latin_product_name_in_source_is_preserved_and_transliterated(self):
        source = "GPT가 뭐야?"
        response = json_korean_input("ok", source, "ジーピーティーって何？")
        with patch("translator.chat", return_value=response):
            result = translator.translate_korean_input(source)
        self.assertEqual(result.normalized_source, source)
        self.assertEqual(result.translation, "ジーピーティーって何？")

    def test_normalizer_cannot_invent_a_latin_product_name(self):
        invalid = json_korean_input("ok", "GPT가 뭐야?", "それは何？")
        with patch("translator.chat", side_effect=[invalid, invalid]):
            self.assertIsNone(translator.translate_korean_input("그게 뭐야?"))

    def test_conversational_jamo_can_be_preserved_in_normalized_source(self):
        source = "안녕 ㅋㅋ"
        response = json_korean_input("ok", source, "こんにちは、ふふ")
        with patch("translator.chat", return_value=response):
            result = translator.translate_korean_input(source)
        self.assertEqual(result.normalized_source, source)
        self.assertEqual(result.translation, "こんにちは、ふふ")

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

    def test_japanese_to_korean_uses_gemini_without_calling_qwen(self):
        response = gemini_response("물론이에요. 무엇을 이야기할까요?")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "secret-key"}, clear=False):
            with patch("gemini_translator.requests.post", return_value=response) as post:
                with patch("translator.chat") as chat_mock:
                    result = translator.japanese_to_korean(
                        "もちろんです。何を話しましょうか？"
                    )

        self.assertEqual(result, "물론이에요. 무엇을 이야기할까요?")
        chat_mock.assert_not_called()
        request_url = post.call_args.args[0]
        request_kwargs = post.call_args.kwargs
        self.assertIn("/models/gemini-3.5-flash-lite:generateContent", request_url)
        self.assertEqual(request_kwargs["headers"]["x-goog-api-key"], "secret-key")
        self.assertNotIn("secret-key", json.dumps(request_kwargs["json"]))
        generation_config = request_kwargs["json"]["generationConfig"]
        self.assertEqual(generation_config["responseMimeType"], "application/json")
        self.assertEqual(
            generation_config["responseJsonSchema"],
            gemini_translator.TRANSLATION_SCHEMA,
        )

    def test_invalid_gemini_translation_falls_back_to_existing_qwen_path(self):
        response = gemini_response("もちろん요")
        qwen_output = json_translation("물론이에요")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "secret-key"}, clear=False):
            with patch("gemini_translator.requests.post", return_value=response):
                with patch("translator.chat", return_value=qwen_output) as chat_mock:
                    result = translator.japanese_to_korean("もちろんです")

        self.assertEqual(result, "물론이에요")
        self.assertEqual(chat_mock.call_count, 1)
        self.assertEqual(chat_mock.call_args.kwargs["model"], translator._ja_to_ko_model())

    def test_gemini_request_failure_falls_back_to_existing_qwen_path(self):
        qwen_output = json_translation("안녕하세요")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "secret-key"}, clear=False):
            with patch(
                "gemini_translator.requests.post",
                side_effect=RequestException("Gemini unavailable"),
            ):
                with patch("translator.chat", return_value=qwen_output) as chat_mock:
                    result = translator.japanese_to_korean("こんにちは")

        self.assertEqual(result, "안녕하세요")
        self.assertEqual(chat_mock.call_count, 1)

    def test_missing_gemini_key_skips_api_and_uses_qwen(self):
        with patch("gemini_translator.requests.post") as post:
            with patch(
                "translator.chat", return_value=json_translation("안녕하세요")
            ) as chat_mock:
                result = translator.japanese_to_korean("こんにちは")

        self.assertEqual(result, "안녕하세요")
        post.assert_not_called()
        self.assertEqual(chat_mock.call_count, 1)

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

    def test_japanese_to_korean_requests_are_isolated_and_log_only_adopted_provider(self):
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
        self.assertEqual(len(logs.records), 1)
        self.assertIn("provider=qwen model=subtitle-model fallback_reason=gemini_api_key_missing", joined)
        for private_text in (source, mixed, valid, "roles=", "temperature=", "stage="):
            self.assertNotIn(private_text, joined)

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

    def test_japanese_to_korean_debug_logs_failure_codes_without_raw_output(self):
        outputs = [json_translation("Note: こんにちは"), json_translation("Hello")]
        with patch.dict(os.environ, {"AI_WAIFU_DEBUG": "1"}, clear=False):
            with patch("translator.chat", side_effect=outputs):
                with self.assertLogs("translator", level="DEBUG") as logs:
                    self.assertIsNone(translator.japanese_to_korean("こんにちは"))
        joined = "\n".join(logs.output)
        self.assertEqual(len(logs.records), 1)
        self.assertIn("provider=none model=none", joined)
        self.assertIn("fallback_reason=gemini_api_key_missing;qwen_english_word", joined)
        for private_text in ("こんにちは", "Hello", "Note:", *outputs):
            self.assertNotIn(private_text, joined)

    def test_gemini_success_logs_only_validated_provider_and_model(self):
        source, subtitle = "こんにちは。", "안녕하세요."
        env = {"GEMINI_API_KEY": "test-only-secret", "AI_WAIFU_DEBUG": "1"}
        with patch.dict(os.environ, env, clear=False):
            with patch("gemini_translator.requests.post", return_value=gemini_response(subtitle)):
                with patch("translator.chat") as chat_mock, self.assertLogs(level="DEBUG") as logs:
                    self.assertEqual(translator.japanese_to_korean(source), subtitle)
        chat_mock.assert_not_called()
        self.assertEqual(len(logs.records), 1)
        self.assertEqual(
            logs.records[0].getMessage(),
            f"JA->KO provider=gemini model={gemini_translator.GEMINI_TRANSLATOR_MODEL} fallback_reason=none",
        )
        for private_text in (source, subtitle, "test-only-secret", "x-goog-api-key", "candidates"):
            self.assertNotIn(private_text, "\n".join(logs.output))

    def test_rejected_gemini_is_never_logged_as_adopted(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-only-secret", "AI_WAIFU_DEBUG": "1"}, clear=False):
            with patch("gemini_translator.requests.post", return_value=gemini_response("privateword 안녕하세요")):
                with patch("translator.chat", return_value=json_translation("안녕하세요")):
                    with self.assertLogs(level="DEBUG") as logs:
                        self.assertEqual(translator.japanese_to_korean("こんにちは"), "안녕하세요")
        joined = "\n".join(logs.output)
        self.assertEqual(len(logs.records), 1)
        self.assertIn("provider=qwen", joined)
        self.assertIn("fallback_reason=english_word", joined)
        for private_text in ("provider=gemini", "privateword", "안녕하세요", "test-only-secret"):
            self.assertNotIn(private_text, joined)

    def test_gemini_exceptions_log_codes_without_key_headers_or_exception_text(self):
        secret = "test-only-secret"
        sensitive = f"x-goog-api-key: {secret}; headers; private response body"
        forbidden_response = Mock(status_code=403)
        cases = [
            (ReadTimeout(sensitive), "gemini_request_timeout"),
            (RequestException(sensitive), "gemini_request_error"),
            (HTTPError(sensitive, response=forbidden_response), "gemini_http_403"),
        ]
        for error, reason in cases:
            with self.subTest(reason=reason), patch.dict(os.environ, {"GEMINI_API_KEY": secret, "AI_WAIFU_DEBUG": "1"}, clear=False):
                with patch("gemini_translator.requests.post", side_effect=error):
                    with patch("translator.chat", return_value=json_translation("안녕하세요")) as chat_mock:
                        with self.assertLogs(level="DEBUG") as logs:
                            self.assertEqual(translator.japanese_to_korean("こんにちは"), "안녕하세요")
                self.assertEqual(chat_mock.call_count, 1)
                self.assertEqual(len(logs.records), 1)
                joined = "\n".join(logs.output)
                self.assertIn(f"fallback_reason={reason}", joined)
                for private_text in (secret, "x-goog-api-key", "headers", "private response body", "こんにちは", "안녕하세요"):
                    self.assertNotIn(private_text, joined)

    def test_malformed_gemini_responses_fall_back_without_logging_bodies(self):
        missing_candidates = Mock()
        missing_candidates.json.return_value = {"private response body": "test-only-secret"}
        invalid_json = gemini_response("안녕하세요")
        invalid_json.json.return_value["candidates"][0]["content"]["parts"][0]["text"] = "test-only-secret private response body"
        unreadable_json = Mock()
        unreadable_json.json.side_effect = ValueError("test-only-secret private response body")
        for response, reason in ((missing_candidates, "gemini_response_error"), (invalid_json, "gemini_json_parse_error"), (unreadable_json, "gemini_response_error")):
            with self.subTest(reason=reason), patch.dict(os.environ, {"GEMINI_API_KEY": "test-only-secret", "AI_WAIFU_DEBUG": "1"}, clear=False):
                with patch("gemini_translator.requests.post", return_value=response):
                    with patch("translator.chat", return_value=json_translation("안녕하세요")):
                        with self.assertLogs(level="DEBUG") as logs:
                            self.assertEqual(translator.japanese_to_korean("こんにちは"), "안녕하세요")
                self.assertEqual(len(logs.records), 1)
                joined = "\n".join(logs.output)
                self.assertIn(f"fallback_reason={reason}", joined)
                self.assertNotIn("test-only-secret", joined)
                self.assertNotIn("private response body", joined)

    def test_qwen_failure_does_not_claim_a_provider_was_adopted(self):
        with patch.dict(os.environ, {"AI_WAIFU_DEBUG": "1"}, clear=False):
            with patch("translator.chat", side_effect=RequestException("private headers and response")) as chat_mock:
                with self.assertLogs(level="DEBUG") as logs:
                    self.assertIsNone(translator.japanese_to_korean("こんにちは"))
        self.assertEqual(chat_mock.call_count, 2)
        self.assertEqual(len(logs.records), 1)
        joined = "\n".join(logs.output)
        self.assertIn("provider=none model=none fallback_reason=gemini_api_key_missing;qwen_request_error", joined)
        self.assertNotIn("private headers and response", joined)

    def test_korean_input_debug_mode_does_not_log_raw_response(self):
        response = json_korean_input("ok", "안녕", "こんにちは")
        with patch.dict(os.environ, {"AI_WAIFU_DEBUG": "1"}, clear=False):
            with patch("translator.chat", return_value=response):
                with self.assertNoLogs("translator", level="DEBUG"):
                    self.assertEqual(translator.translate_korean_input("안녕").translation, "こんにちは")

    def test_korean_input_errors_do_not_log_exception_contents(self):
        sensitive = "private key headers response body"
        for error in (ReadTimeout(sensitive), RequestException(sensitive)):
            with self.subTest(error=type(error).__name__), patch("translator.chat", side_effect=error):
                with self.assertLogs("translator", level="DEBUG") as logs:
                    self.assertIsNone(translator.translate_korean_input("안녕"))
            self.assertNotIn(sensitive, "\n".join(logs.output))

    def test_complete_multisentence_japanese_passes_without_retry(self):
        source = "안녕. 오늘 학교에서 시험을 봤어. 한 문장으로 짧게 답해 줘."
        translations = (
            "こんにちは。今日は学校で試験を受けたよ。一文で短く答えてね。",
            "こんにちは！今日は学校で試験を受けたよ。一文で短く答えてね？",
        )
        for translated in translations:
            with self.subTest(translation=translated):
                response = json_korean_input("ok", source, translated)
                with patch("translator.chat", return_value=response) as chat_mock:
                    result = translator.translate_korean_input(source)
                self.assertIsNotNone(result)
                self.assertEqual(result.translation, translated)
                self.assertEqual(chat_mock.call_count, 1)

    def test_missing_japanese_sentence_still_retries(self):
        source = "안녕. 오늘 학교에서 시험을 봤어. 한 문장으로 짧게 답해 줘."
        incomplete = "こんにちは。今日は学校で試験を受けたよ。"
        complete = "こんにちは。今日は学校で試験を受けたよ。一文で短く答えてね。"
        responses = [
            json_korean_input("ok", source, incomplete),
            json_korean_input("ok", source, complete),
        ]
        with patch("translator.chat", side_effect=responses) as chat_mock:
            result = translator.translate_korean_input(source)
        self.assertIsNotNone(result)
        self.assertEqual(result.translation, complete)
        self.assertEqual(chat_mock.call_count, 2)
