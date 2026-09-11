"""Public API projections; never serialize the session or service configuration."""

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from backend.conversation.service import TurnEvent, TurnResult


class TurnInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: StrictStr = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("empty_input")
        return value


ERROR_MESSAGES = {
    "empty_input": "내용을 입력해 주세요.",
    "input_translation_failed": "입력 번역에 실패했습니다. 다시 시도해 주세요.",
    "ambiguous_input": "입력이 불분명합니다. 다시 입력해 주세요.",
    "japanese_reply_failed": "일본어 응답 검증에 실패했습니다. 다시 시도해 주세요.",
    "subtitle_failed": "한국어 자막을 만들지 못했습니다.",
    "synthesis_failed": "음성 합성에 실패했습니다.",
    "playback_failed": "음성을 재생하지 못했습니다.",
    "empty_tts_text": "읽을 문장이 없습니다.",
    "turn_failed": "대화 처리에 실패했습니다. 다시 시도해 주세요.",
}
STAGES = {"translating_input", "generating", "translating_subtitle", "synthesizing", "speaking"}
TEXT_FIELDS = {
    "input_translated": ("source", "normalized_source", "japanese_input"),
    "reply_ready": ("emotion", "japanese_reply"),
    "subtitle_ready": ("korean_subtitle",),
}


def error_code(value: object) -> str:
    return value if isinstance(value, str) and value in ERROR_MESSAGES else "turn_failed"


def public_event(event: TurnEvent) -> dict | None:
    if event.kind == "stage_changed":
        stage = event.data.get("stage")
        return {"stage": stage} if isinstance(stage, str) and stage in STAGES else None
    if event.kind == "notice":
        code = error_code(event.data.get("code"))
        return {"code": code, "message": ERROR_MESSAGES[code]}
    if event.kind in TEXT_FIELDS:
        return {key: value for key in TEXT_FIELDS[event.kind]
                if isinstance(value := event.data.get(key), str) or value is None}
    return None


def public_result(result: TurnResult) -> dict:
    return {
        "status": result.status,
        "japanese_reply": result.japanese_reply,
        "korean_subtitle": result.korean_subtitle,
        "emotion": result.emotion,
        "audio_played": result.audio_played,
        "errors": [error_code(code) for code in result.errors],
    }
