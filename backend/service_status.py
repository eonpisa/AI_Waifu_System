"""Opt-in, request-scoped observations; never probe services or parse logs.

CLI callers have no observer. API callers receive only these public codes,
not settings, credentials, transport errors or response bodies.
"""

from contextlib import contextmanager
from contextvars import ContextVar
import re


SERVICE_CODES = {
    "ollama": {"not_checked": "unknown", "response_received": "ok", "request_failed": "error"},
    "gemini": {"not_checked": "unknown", "subtitle_accepted": "ok",
               "api_key_missing": "error", "translation_failed": "error"},
    "sbv2": {"not_checked": "unknown", "synthesis_succeeded": "ok", "synthesis_failed": "error"},
    "vts": {"not_checked": "unknown", "parameters_applied": "ok",
            "model_not_calibrated": "warning", "mouth_reset_failed": "warning",
            "authentication_failed": "error", "parameter_rejected": "error",
            "timeout": "error", "connection_failed": "error", "response_error": "error",
            "stop_event_required": "error", "worker_error": "error", "worker_start_failed": "error"},
}
_VALIDATION_CODES = {
    "empty_translation", "japanese_character", "hanja_or_chinese_character", "english_word",
    "chinese_punctuation", "annotation_or_markdown", "missing_korean_text",
    "missing_required_term", "incomplete_translation", "request_timeout", "request_error", "json_parse_error",
}
_GEMINI_CODES = {"gemini_api_key_missing", "gemini_request_timeout", "gemini_request_error",
                 "gemini_response_error", "gemini_json_parse_error"}
_observer = ContextVar("service_status_observer", default=None)


def public_service(data):
    service, code = data.get("service"), data.get("code")
    if not isinstance(service, str) or not isinstance(code, str):
        return None
    state = SERVICE_CODES.get(service, {}).get(code)
    return {"service": service, "state": state, "code": code} if state else None


def _safe_reason(value):
    if not isinstance(value, str):
        return "translation_failed"
    parts = value.split(";")
    if not 1 <= len(parts) <= 2:
        return "translation_failed"
    def allowed(code):
        return (code in {"none", "translation_failed"} | _GEMINI_CODES | _VALIDATION_CODES
                or re.fullmatch(r"gemini_http_[1-5][0-9]{2}", code)
                or code in {f"qwen_{reason}" for reason in _VALIDATION_CODES})
    return value if all(allowed(part) for part in parts) else "translation_failed"


def public_subtitle_provider(data):
    provider = data.get("provider")
    if not isinstance(provider, str) or provider not in {"gemini", "qwen", "none"}:
        return None
    model = data.get("model")
    pattern = r"gemini-[A-Za-z0-9._:-]{1,70}" if provider == "gemini" else r"qwen[A-Za-z0-9._:-]{1,70}"
    # Only public provider model identifiers; never forward a custom path/URL.
    model = (model if isinstance(model, str) and re.fullmatch(pattern, model) else "custom")
    return {"provider": provider, "model": "none" if provider == "none" else model,
            "fallback_reason": _safe_reason(data.get("fallback_reason"))}


@contextmanager
def observe_services(callback):
    token = _observer.set(callback)
    try:
        yield
    finally:
        _observer.reset(token)


def _report(kind, data):
    callback = _observer.get()
    if callback is not None and data is not None:
        try:
            callback(kind, data)
        except Exception:
            # Display failures must not change generation, playback or cleanup.
            pass


def report_service(service, code):
    _report("service_status", public_service({"service": service, "code": code}))


def report_subtitle_provider(provider, model, fallback_reason):
    _report("subtitle_provider", public_subtitle_provider(
        {"provider": provider, "model": model, "fallback_reason": fallback_reason}))
