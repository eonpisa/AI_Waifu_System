"""Small Gemini REST adapter dedicated to Japanese-to-Korean translation."""

from dataclasses import dataclass
import json
import os
from typing import Optional
from urllib.parse import quote

import requests
from requests.exceptions import ReadTimeout, RequestException


GEMINI_TRANSLATOR_MODEL = os.environ.get(
    "GEMINI_TRANSLATOR_MODEL", "gemini-3.5-flash-lite"
)
GEMINI_TRANSLATION_TEMPERATURE = float(
    os.environ.get("GEMINI_TRANSLATION_TEMPERATURE", "0.0")
)
GEMINI_TRANSLATION_TIMEOUT_SECONDS = float(
    os.environ.get("GEMINI_TRANSLATION_TIMEOUT_SECONDS", "30")
)
GEMINI_API_BASE_URL = os.environ.get(
    "GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
).rstrip("/")
TRANSLATION_SCHEMA = {
    "type": "object",
    "properties": {"translation": {"type": "string"}},
    "required": ["translation"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class GeminiTranslationResult:
    translation: Optional[str]
    raw_response: object
    reason: Optional[str]


def translate_japanese_to_korean(source: str) -> GeminiTranslationResult:
    """Make one structured Gemini request and return a result for validation."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return GeminiTranslationResult(None, None, "gemini_api_key_missing")

    system_instruction = (
        "Translate the complete Japanese source into complete, natural Korean. "
        "Translate every Japanese word and clause; never leave Japanese kana or kanji, "
        "Chinese text, or English words in the Korean translation. Return translation only, "
        "without notes, markdown, labels, analysis, parentheses, or source text. "
        "Always use the canonical name mapping イレイナ -> 일레이나. "
        "Populate the provided JSON response schema."
    )
    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": source}]}],
        "generationConfig": {
            "temperature": GEMINI_TRANSLATION_TEMPERATURE,
            "responseMimeType": "application/json",
            "responseJsonSchema": TRANSLATION_SCHEMA,
        },
    }
    model = quote(GEMINI_TRANSLATOR_MODEL, safe="")
    url = f"{GEMINI_API_BASE_URL}/models/{model}:generateContent"
    try:
        response = requests.post(
            url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=GEMINI_TRANSLATION_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        response_body = response.json()
        parts = response_body["candidates"][0]["content"]["parts"]
        raw_response = "".join(
            part.get("text", "") for part in parts if isinstance(part, dict)
        ).strip()
    except ReadTimeout:
        return GeminiTranslationResult(None, None, "gemini_request_timeout")
    except RequestException as exc:
        # Exception text can contain a URL, headers or a response body. Return
        # only a status code; the caller logs the final provider and reason.
        status = getattr(exc.response, "status_code", None)
        if isinstance(status, int) and 100 <= status <= 599:
            return GeminiTranslationResult(None, None, f"gemini_http_{status}")
        return GeminiTranslationResult(None, None, "gemini_request_error")
    except (KeyError, IndexError, TypeError, ValueError):
        return GeminiTranslationResult(None, None, "gemini_response_error")

    try:
        parsed = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        return GeminiTranslationResult(None, raw_response, "gemini_json_parse_error")
    translated = parsed.get("translation") if isinstance(parsed, dict) else None
    if (
        not isinstance(translated, str)
        or not translated.strip()
        or set(parsed) != {"translation"}
    ):
        return GeminiTranslationResult(None, raw_response, "gemini_json_parse_error")
    return GeminiTranslationResult(translated.strip(), raw_response, None)
