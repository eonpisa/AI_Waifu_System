"""Validation and one-shot regeneration for Japanese chat responses."""

import logging
import re
from typing import Optional, Sequence

from backend.conversation.llm import chat


LOGGER = logging.getLogger(__name__.rsplit(".", 1)[-1])
_KANA = re.compile(r"[\u3040-\u30ff]")
_HANGUL = re.compile(r"[\uac00-\ud7a3]")
_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
_CYRILLIC = re.compile(r"[\u0400-\u052f]")
_PARENTHESES = re.compile(r"[()（）]")
_CHINESE_PUNCTUATION = re.compile(r"[，；：]" )
_EXPLANATION_LABEL = re.compile(r"(?:note|translation|翻訳|説明)\s*[:：]", re.IGNORECASE)
# These characters/phrases are not natural Japanese prose and catch Chinese text
# even when it is appended after otherwise valid Japanese.
_CHINESE_ONLY = re.compile(
    r"(?:你好|您好|是如何|天气|不错|怎么样|怎么回事|谢谢你|我们|你们|他们|因为|所以|但是|没有|可以吗|好吗|的吗|呢|吧|吗|很|这|那|不過|不过)"
)
_COMMON_SHORT_JAPANESE = {"了解", "承知", "大丈夫", "問題ない", "平気"}

STRICT_JAPANESE_RETRY = """
重要: 直前の回答は無効でした。ユーザーへの返答を最初から最後まで自然な日本語だけで再生成してください。
中国語、韓国語、英語、ローマ字、注釈、翻訳、説明、Note:、括弧書きは一切含めないでください。
日本語の本文だけを返し、内容を省略・要約しないでください。
""".strip()


def japanese_response_validation_reason(text: object) -> Optional[str]:
    """Return the first rejection reason, or None for a safe Japanese response."""
    if not isinstance(text, str):
        return "invalid_type"
    response = text.strip()
    if not response:
        return "empty_response"
    if _HANGUL.search(response):
        return "korean_text"
    if _CYRILLIC.search(response):
        return "cyrillic_text"
    if _EXPLANATION_LABEL.search(response) or _PARENTHESES.search(response):
        return "annotation"
    if _CHINESE_ONLY.search(response):
        return "chinese_expression"
    if _CHINESE_PUNCTUATION.search(response):
        return "chinese_punctuation"
    if _LATIN_WORD.search(response):
        return "latin_word"
    if _KANA.search(response):
        return None
    # A very short established Japanese all-kanji acknowledgement is valid, but
    # a longer kana-free sentence is too ambiguous to send to Japanese TTS.
    return None if response in _COMMON_SHORT_JAPANESE else "missing_japanese_kana"


def is_valid_japanese_response(text: object) -> bool:
    """Accept a complete Japanese response and reject any mixed-language payload."""
    return japanese_response_validation_reason(text) is None


def generate_validated_japanese_reply(messages: Sequence[dict]) -> Optional[str]:
    """Generate once, then regenerate once with strict Japanese-only instructions."""
    for retry in (False, True):
        request_messages = list(messages)
        if retry:
            request_messages.append({"role": "system", "content": STRICT_JAPANESE_RETRY})
        try:
            reply = chat(request_messages)
        except Exception:
            LOGGER.error("Japanese chat request failed.")
            return None
        reason = japanese_response_validation_reason(reply)
        if reason is None:
            return reply.strip()
        attempt = "regeneration" if retry else "initial generation"
        LOGGER.debug("Validation reason (%s): %s", attempt, reason)
        LOGGER.warning("Rejected non-Japanese or annotated AI response%s.", "; regenerating" if not retry else "")
    return None
