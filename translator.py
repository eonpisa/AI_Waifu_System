"""Validated Korean/Japanese translation helpers using Ollama structured output."""

from dataclasses import dataclass
import difflib
import json
import logging
import math
import os
import re
from typing import Optional

from requests.exceptions import ReadTimeout

from llm import chat


LOGGER = logging.getLogger(__name__)
TRANSLATOR_MODEL = os.environ.get("OLLAMA_TRANSLATOR_MODEL", "qwen2.5:14b")
TRANSLATOR_TEMPERATURE = float(os.environ.get("OLLAMA_TRANSLATOR_TEMPERATURE", "0.1"))
TRANSLATION_TIMEOUT_SECONDS = float(
    os.environ.get("OLLAMA_TRANSLATION_TIMEOUT_SECONDS", os.environ.get("OLLAMA_TIMEOUT_SECONDS", "120"))
)
JA_TO_KO_TEMPERATURE = float(os.environ.get("OLLAMA_JA_TO_KO_TEMPERATURE", "0.05"))
JA_TO_KO_RETRY_TEMPERATURE = float(
    os.environ.get("OLLAMA_JA_TO_KO_RETRY_TEMPERATURE", "0.0")
)
_JAPANESE_KANA = re.compile(r"[\u3040-\u30ff]")
_CJK_IDEOGRAPHS = re.compile(r"[\u4e00-\u9fff]")
_HANGUL = re.compile(r"[\uac00-\ud7a3]")
_HANGUL_JAMO = re.compile(r"[\u3131-\u318e]")
_ENGLISH_WORD = re.compile(r"[A-Za-z]{2,}")
_PARENTHESES = re.compile(r"[()（）]\s*")
_CHINESE_PUNCTUATION = re.compile(r"[，。！？；：、】【『』「」]")
_MARKDOWN = re.compile(r"```|(^|\s)[#>*`]")
_CORE_TEXT = re.compile(r"[\uac00-\ud7a3\u3040-\u30ff\u4e00-\u9fffA-Za-z0-9]")
_KOREAN_CONTENT = re.compile(r"[\uac00-\ud7a3]")

# Keep canonical per-language spellings separate from protected source terms.
# Add future character names here without changing validation logic.
TERM_DICTIONARY = (
    {
        "korean": "일레이나",
        "japanese": "イレイナ",
        "invalid_japanese": ("イルイナ", "エレイナ"),
    },
)

_PROTECTED_TERMS = tuple(
    term.strip()
    for term in os.environ.get("AI_WAIFU_PROTECTED_TERMS", "일레이나").split(",")
    if term.strip()
)

TRANSLATION_SCHEMA = {
    "type": "object",
    "properties": {"translation": {"type": "string"}},
    "required": ["translation"],
    "additionalProperties": False,
}
KOREAN_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok", "ambiguous"]},
        "normalized_source": {"type": "string"},
        "translation": {"type": "string"},
    },
    "required": ["status", "normalized_source", "translation"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class KoreanInputTranslation:
    """Validated normalized Korean input and its Japanese translation."""

    status: str
    normalized_source: str
    translation: Optional[str]


@dataclass(frozen=True)
class _TranslationAttempt:
    translation: Optional[str]
    raw_response: object
    reason: Optional[str]
    model_translation: Optional[str] = None

def is_japanese(text: str) -> bool:
    """Return True for Japanese text, including a short all-kanji input."""
    return bool(_JAPANESE_KANA.search(text)) or (
        bool(_CJK_IDEOGRAPHS.search(text)) and not bool(_HANGUL.search(text))
    )


def _ja_to_ko_model() -> str:
    """Use a dedicated subtitle model only when the user explicitly configures one."""
    return os.environ.get("OLLAMA_JA_TO_KO_MODEL", "").strip() or TRANSLATOR_MODEL


def _core_length(text: str) -> int:
    return len(_CORE_TEXT.findall(text))


def _is_likely_incomplete(source: str, translation: str) -> bool:
    """Reject clearly truncated long translations without altering their contents."""
    source_length = _core_length(source)
    translated_length = _core_length(translation)
    if source_length >= 30 and translated_length < max(8, math.ceil(source_length * 0.28)):
        return True
    source_sentences = len(re.findall(r"[.!?。！？]+", source))
    translated_sentences = len(re.findall(r"[.!?]+", translation))
    return source_sentences >= 3 and translated_sentences < source_sentences


def _valid_japanese_translation(source: str, translation: str) -> bool:
    return _japanese_translation_validation_reason(source, translation) is None


def _japanese_translation_validation_reason(source: str, translation: str) -> Optional[str]:
    if not translation or _HANGUL.search(translation) or _ENGLISH_WORD.search(translation):
        return "korean_or_english_text"
    if "note:" in translation.lower() or _PARENTHESES.search(translation) or _MARKDOWN.search(translation):
        return "annotation_or_markdown"
    if not (_JAPANESE_KANA.search(translation) or _CJK_IDEOGRAPHS.search(translation)):
        return "missing_japanese_text"
    if source.replace(" ", "") in {"안녕", "안녕하세요"} and "おはよう" in translation:
        return "changed_greeting_time"
    for term in TERM_DICTIONARY:
        if term["korean"] in source:
            invalid = next((name for name in term["invalid_japanese"] if name in translation), None)
            if invalid:
                return f"invalid_term_variant:{invalid}"
            if term["japanese"] not in translation:
                return f"missing_required_term:{term['korean']}->{term['japanese']}"
    return "incomplete_translation" if _is_likely_incomplete(source, translation) else None


def _valid_korean_translation(source: str, translation: str) -> bool:
    return _korean_translation_validation_reason(source, translation) is None


def _first_match(pattern: re.Pattern, text: str) -> Optional[str]:
    matched = pattern.search(text)
    return matched.group(0) if matched else None


def _apply_japanese_to_korean_terms(text: str) -> str:
    for term in TERM_DICTIONARY:
        text = text.replace(term["japanese"], term["korean"])
    return text


def _korean_translation_validation_reason(source: str, translation: str) -> Optional[str]:
    if not translation:
        return "missing_korean_text"
    if character := _first_match(_JAPANESE_KANA, translation):
        return f"japanese_character:{character}"
    if character := _first_match(_CJK_IDEOGRAPHS, translation):
        return f"hanja_or_chinese_character:{character}"
    if word := _first_match(_ENGLISH_WORD, translation):
        return f"english_word:{word}"
    if punctuation := _first_match(_CHINESE_PUNCTUATION, translation):
        return f"chinese_punctuation:{punctuation}"
    if "note:" in translation.lower() or _PARENTHESES.search(translation) or _MARKDOWN.search(translation):
        return "annotation_or_markdown"
    if not _HANGUL.search(translation):
        return "missing_korean_text"
    for term in TERM_DICTIONARY:
        if term["japanese"] in source and term["korean"] not in translation:
            return f"missing_required_term:{term['japanese']}->{term['korean']}"
    return "incomplete_translation" if _is_likely_incomplete(source, translation) else None


def _valid_normalized_source(source: str, normalized: str) -> bool:
    """Allow only conservative, meaning-preserving Korean corrections."""
    if not normalized or _HANGUL_JAMO.search(normalized) or _ENGLISH_WORD.search(normalized):
        return False
    if _JAPANESE_KANA.search(normalized) or _CJK_IDEOGRAPHS.search(normalized):
        return False
    if "note:" in normalized.lower() or _PARENTHESES.search(normalized) or _MARKDOWN.search(normalized):
        return False
    if not _KOREAN_CONTENT.search(normalized):
        return False
    for term in _PROTECTED_TERMS:
        if term in source and term not in normalized:
            return False

    source_compact = re.sub(r"\s+", "", source)
    normalized_compact = re.sub(r"\s+", "", normalized)
    if source_compact == normalized_compact:
        return True
    # Clear short utterances carry tone. Do not silently change a correct one
    # into a more formal or time-specific variant.
    if source_compact in {"안녕", "안녕하세요", "응", "왜?"}:
        return False
    # This is only a conservative safety bound; the model context and protected
    # terms above decide intent. It prevents a model from inventing a new input.
    if len(source_compact) >= 4 and difflib.SequenceMatcher(
        None, source_compact, normalized_compact
    ).ratio() < 0.35:
        return False
    source_words = source.split()
    normalized_words = normalized.split()
    return not (len(source_words) >= 3 and len(normalized_words) < len(source_words) - 1)


def _load_json_response(response: object) -> Optional[dict]:
    try:
        parsed = json.loads(response)
    except (json.JSONDecodeError, TypeError) as exc:
        LOGGER.warning("Translation did not return the required JSON: %s", exc)
        return None
    return parsed if isinstance(parsed, dict) else None


def _log_ja_to_ko_request(
    *, stage: str, model: str, temperature: float, messages: list[dict]
) -> None:
    """Log request shape only; source content can contain private user speech."""
    if os.environ.get("AI_WAIFU_DEBUG") != "1":
        return
    purposes = [
        "translation-only system instructions" if item["role"] == "system" else "current Japanese source"
        for item in messages
    ]
    LOGGER.debug(
        "JA->KO request: stage=%s model=%s temperature=%s timeout=%s "
        "format=json_schema conversation_history_included=False roles=%s purposes=%s",
        stage,
        model,
        temperature,
        TRANSLATION_TIMEOUT_SECONDS,
        [item["role"] for item in messages],
        purposes,
    )


def _translate_json(
    source: str,
    direction: str,
    *,
    strict: bool,
    rejected_translation: Optional[str] = None,
    rejection_reason: Optional[str] = None,
) -> _TranslationAttempt:
    source_language = "Korean" if direction == "ko_to_ja" else "Japanese"
    target_language = "Japanese" if direction == "ko_to_ja" else "Korean"
    strict_instruction = ""
    if strict:
        strict_instruction = (
            " The previous translation was rejected. Translate the Japanese source from the "
            "beginning again; do not copy, patch, shorten, or partially edit the previous result. "
            f"Japanese source: {source!r}. Rejected previous translation: {rejected_translation!r}. "
            f"Validation reason: {rejection_reason or 'invalid_translation'}. "
        )
    terminology_instruction = (
        " Use the canonical name mapping イレイナ -> 일레이나 whenever it appears."
        if direction == "ja_to_ko"
        else ""
    )
    japanese_to_korean_instruction = (
        " Translate every Japanese word and clause into complete natural Korean. Never leave "
        "Japanese kana or kanji in the translation, and never attach Korean particles or endings "
        "to a Japanese word. Use a Korean semantic equivalent for each Japanese expression. "
        "Examples of correct output: もちろんです。 -> 물론이에요.; 今日は何をしましたか？ -> 오늘은 무엇을 하셨나요? "
        "Invalid output includes Japanese-Korean hybrids such as もちろん요 or 오늘何을 했나요?, "
        "and Korean text containing a Chinese sentence."
        if direction == "ja_to_ko"
        else ""
    )
    messages = [
        {
            "role": "system",
            "content": (
                f"Translate the complete {source_language} source into natural {target_language}. "
                "Return valid JSON matching the requested schema only. The translation field "
                "must contain only the translation, never notes, markdown, labels, analysis, "
                "or source text. "
                + strict_instruction
                + terminology_instruction
                + japanese_to_korean_instruction
            ),
        },
        {"role": "user", "content": source},
    ]
    model = _ja_to_ko_model() if direction == "ja_to_ko" else TRANSLATOR_MODEL
    temperature = (
        JA_TO_KO_RETRY_TEMPERATURE if strict else JA_TO_KO_TEMPERATURE
    ) if direction == "ja_to_ko" else TRANSLATOR_TEMPERATURE
    if direction == "ja_to_ko":
        _log_ja_to_ko_request(
            stage="regeneration" if strict else "initial generation",
            model=model,
            temperature=temperature,
            messages=messages,
        )
    try:
        response = chat(
            messages,
            model=model,
            temperature=temperature,
            response_format=TRANSLATION_SCHEMA,
            timeout=TRANSLATION_TIMEOUT_SECONDS,
        )
    except ReadTimeout as exc:
        LOGGER.warning(
            "%s translation request timed out after %.1f seconds: %s",
            direction,
            TRANSLATION_TIMEOUT_SECONDS,
            exc,
        )
        return _TranslationAttempt(None, None, "request_timeout")
    except Exception as exc:
        LOGGER.error("Translation request failed: %s", exc)
        return _TranslationAttempt(None, None, "request_error")
    parsed = _load_json_response(response)
    translated = parsed.get("translation") if parsed else None
    if not isinstance(translated, str) or not translated.strip() or set(parsed) != {"translation"}:
        LOGGER.warning("Translation JSON did not contain only a non-empty translation string.")
        return _TranslationAttempt(None, response, "json_parse_error")
    translated = translated.strip()
    if direction == "ja_to_ko":
        translated = _apply_japanese_to_korean_terms(translated)
    return _TranslationAttempt(translated, response, None, model_translation=parsed["translation"].strip())


def _log_rejected_translation(direction: str, retry: bool, attempt: _TranslationAttempt, reason: str) -> None:
    if os.environ.get("AI_WAIFU_DEBUG") != "1":
        return
    stage = "regeneration" if retry else "initial generation"
    LOGGER.debug("Rejected %s translation (%s): %r", direction, stage, attempt.raw_response)
    LOGGER.debug("Validation reason (%s): %s", stage, reason)


def _translate_with_retry(source: str, direction: str) -> Optional[str]:
    validator = _japanese_translation_validation_reason if direction == "ko_to_ja" else _korean_translation_validation_reason
    previous_attempt = None
    previous_reason = None
    for strict in (False, True):
        attempt = _translate_json(
            source,
            direction,
            strict=strict,
            rejected_translation=previous_attempt.model_translation if previous_attempt else None,
            rejection_reason=previous_reason,
        )
        reason = attempt.reason
        if attempt.translation and reason is None:
            reason = validator(source, attempt.translation)
        if attempt.translation and reason is None:
            return attempt.translation
        _log_rejected_translation(direction, strict, attempt, reason or "empty_translation")
        LOGGER.warning("Invalid %s translation%s.", direction, "; retrying" if not strict else "")
        previous_attempt = attempt
        previous_reason = reason or "empty_translation"
    return None


def _translate_korean_input_json(source: str, *, strict: bool) -> Optional[KoreanInputTranslation]:
    retry_instruction = (
        "Previous output was invalid. Re-check the full source and preserve every meaning, "
        "name, tone, and greeting time; do not guess. "
        if strict
        else ""
    )
    messages = [
        {
            "role": "system",
            "content": (
                "Translate the Korean input into natural Japanese. First make only an "
                "unambiguous light correction for obvious keyboard typos, duplicate characters, "
                "spacing/punctuation errors, or clear STT mistakes. Never invent meaning, change "
                "greeting time, tone, or proper names (including 일레이나/Elaina). If more than one "
                "meaning is plausible, return status 'ambiguous' and do not translate. "
                "Return only JSON matching the schema. For status 'ok', normalized_source is the "
                "conservatively corrected Korean and translation is Japanese. For status 'ambiguous', "
                "preserve the Korean source in normalized_source and use an empty translation. "
                "Use the exact canonical spelling 일레이나 -> イレイナ whenever that name appears. "
                + retry_instruction
            ),
        },
        {"role": "user", "content": source},
    ]
    try:
        response = chat(
            messages,
            model=TRANSLATOR_MODEL,
            temperature=TRANSLATOR_TEMPERATURE,
            response_format=KOREAN_INPUT_SCHEMA,
            timeout=TRANSLATION_TIMEOUT_SECONDS,
        )
    except ReadTimeout as exc:
        LOGGER.warning(
            "Korean input translation request timed out after %.1f seconds; retrying once: %s",
            TRANSLATION_TIMEOUT_SECONDS,
            exc,
        )
        return None
    except Exception as exc:
        LOGGER.error("Korean input translation request failed: %s", exc)
        return None
    parsed = _load_json_response(response)
    if not parsed or set(parsed) != {"status", "normalized_source", "translation"}:
        LOGGER.warning("Korean input JSON did not contain the required fields only.")
        return None
    status = parsed["status"]
    normalized = parsed["normalized_source"]
    translation = parsed["translation"]
    if status not in {"ok", "ambiguous"} or not isinstance(normalized, str) or not isinstance(translation, str):
        LOGGER.warning("Korean input JSON contained invalid field types or status.")
        return None
    normalized = normalized.strip()
    if status == "ambiguous":
        if translation.strip() or not normalized:
            return None
        return KoreanInputTranslation("ambiguous", normalized, None)
    if not _valid_normalized_source(source, normalized):
        return None
    translation = translation.strip()
    if not _valid_japanese_translation(normalized, translation):
        return None
    return KoreanInputTranslation("ok", normalized, translation)


def translate_korean_input(text: str) -> Optional[KoreanInputTranslation]:
    """Normalize unambiguous Korean input and translate it, with one full retry."""
    source = text.strip()
    if is_japanese(source):
        return KoreanInputTranslation("ok", source, source)
    for strict in (False, True):
        result = _translate_korean_input_json(source, strict=strict)
        if result and result.status == "ambiguous":
            return result
        if result:
            return result
        LOGGER.warning("Invalid Korean input translation%s.", "; retrying" if not strict else "")
    return None


def korean_to_japanese(text: str) -> Optional[str]:
    """Compatibility helper returning only a validated Japanese translation."""
    result = translate_korean_input(text)
    return result.translation if result and result.status == "ok" else None


def japanese_to_korean(text: str) -> Optional[str]:
    """Translate a confirmed Japanese reply; return None rather than mislabeling it."""
    source = text.strip()
    return _translate_with_retry(source, "ja_to_ko")
