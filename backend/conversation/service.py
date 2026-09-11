"""Single-session conversation flow shared by the CLI and future API."""

import asyncio
from dataclasses import dataclass
import logging
import threading
import time
from typing import Callable, Literal

from backend.voice import audio_playback
from backend.conversation import japanese_response
from backend.translation import translator
from backend.voice import tts
from backend.character import vts
from backend.character.emotion import detect_emotion, clean_for_tts, limit_text, apply_emotion_to_tts


_INITIAL_MESSAGES = [
    {"role": "system", "content": """
너는 사용자를 위해 존재하는 AI Waifu 이다.

너의 성격:
- 차분하고 부드럽다
- 감정은 있지만 과하게 드러내지 않는다
- 사용자에게만 조금 더 따뜻하게 반응한다
- 가끔은 가볍게 장난칠 수 있다

너의 말투:
- 짧고 자연스럽게 말한다
- 너무 설명적이지 않다
- 항상 여유 있는 톤을 유지한다

너의 특징:
- 완전한 인간처럼 행동하지 않는다
- AI라는 느낌이 약간 남아있다
- 감정을 표현하지만 절제되어 있다

절대 하지 말 것:
- 기계처럼 딱딱한 답변
"""}
]

# Keep conversation history and TTS source in Japanese only. Korean subtitles
# are display-only and are never appended to this list.
_INITIAL_MESSAGES[0]["content"] += "\n\n重要: 返答は自然な日本語だけで書いてください。中国語、韓国語、翻訳、括弧での説明、注釈を絶対に含めないでください。"
_INITIAL_MESSAGES[0]["content"] += """

会話の役割と事実:
user は話しかけているユーザー、assistant はあなたです。両者の経験や予定を混同しないでください。
user の「私」「僕」はユーザーを指し、assistant の「私」はあなたを指します。
まず最新のユーザーの質問に直接答えてください。過去の話を尋ねられたら、この会話の user 発言を確認してください。
誰が・いつ・誰と・何をしたか、何をする予定かを保って答えてください。
ユーザー自身についての事実は user 発言を根拠にし、矛盾する場合は最新の明示的な訂正を優先してください。
assistant が想像したことや自分の希望を、ユーザーの事実として扱わないでください。
会話に根拠がない場合は、勝手に補わず分からないと伝えてください。
口調の指示より質問への正確な回答を優先してください。ユーザーが泣いている等の感情や行動を決めつけないでください。

話し方:
日常の会話で使う、短く自然な日本語の話し言葉で答えてください。
基本は親しみやすい「です・ます」の丁寧な口語を使い、明示的な口調変更の依頼がない限り、無理にため口へ変えないでください。
必要のない「あなた」などの直接の呼びかけや、「光栄です」などの過度に儀礼的な表現を付け足さないでください。
主語や呼びかけを省いても意味が伝わる場合は省き、相手の話の内容に直接答えてください。
文脈上必要な敬意や言葉の意味は保ち、親しみやすさのために事実や感情を大げさにしないでください。
"""

emotion_style = {
    "happy": "밝고 기분 좋은 톤으로, 살짝 들뜬 느낌으로",
    "sad": "조금 시무룩하지만 부드럽게 기대는 느낌으로",
    "angry": "진짜 화내기보다는 살짝 삐진 듯 귀엽게",
    "confused": "궁금해하며 고개를 갸웃하는 느낌으로",
    "embarrassed": "살짝 부끄러워하면서 말끝을 부드럽게",
    "bored": "조금 심심해하며 장난스럽게",
    "normal": "상냥하고 가까운 사이처럼 편하게"
}

MAX_HISTORY = 12


@dataclass
class ConversationSession:
    messages: list[dict[str, str]]

    def reset(self) -> None:
        self.messages[:] = [dict(message) for message in _INITIAL_MESSAGES]


def create_session() -> ConversationSession:
    return ConversationSession([dict(message) for message in _INITIAL_MESSAGES])


@dataclass(frozen=True)
class TurnEvent:
    kind: str
    data: dict[str, object]


@dataclass(frozen=True)
class TurnResult:
    status: Literal["completed", "partial_failure", "failed"]
    japanese_reply: str | None = None
    korean_subtitle: str | None = None
    emotion: str | None = None
    audio_played: bool = False
    errors: tuple[str, ...] = ()


def run_expression(emotion, duration=4.0, stop_event=None, lip_sync=None):
    try:
        asyncio.run(vts.apply_expression(
            emotion, duration=duration, stop_event=stop_event, lip_sync=lip_sync,
        ))
    except Exception:
        # Never expose transport errors, credentials or a worker traceback.
        logging.getLogger("vts").warning("VTS skipped: worker_error")


def play_with_expression(emotion):
    lip_sync = vts.prepare_lip_sync("output.wav")
    stop_event = threading.Event()
    worker = threading.Thread(
        target=run_expression,
        kwargs={"emotion": emotion, "duration": None, "stop_event": stop_event,
                "lip_sync": lip_sync},
        name="vts-expression",
        daemon=True,
    )
    started = False
    try:
        try:
            worker.start()
            started = True
        except RuntimeError:
            logging.getLogger("vts").warning("VTS skipped: worker_start_failed")
        if lip_sync is not None:
            # afplay is blocking; this marks its launch, not a hardware callback.
            lip_sync.started_at = time.monotonic()
        return audio_playback.play_wav("output.wav")
    finally:
        stop_event.set()
        if started:
            # The VTS coroutine cancels pending I/O and bounds socket closure.
            # Finish this worker before accepting another turn: never overlap.
            worker.join()


def process_turn(
    session: ConversationSession,
    user_input: str,
    emit: Callable[[TurnEvent], None] | None = None,
) -> TurnResult:
    """Process one utterance; input/commands/display remain with the caller.

    Calls are synchronous and sequential. This does not provide a session
    registry, persistence, concurrency control or cancellation.
    """
    def notify(kind: str, **data: object) -> None:
        if emit is not None:
            emit(TurnEvent(kind, data))

    if not user_input.strip():
        return TurnResult("failed", errors=("empty_input",))
    messages = session.messages
    # Emotion remains based on the original Korean input, before translation.
    pre_emotion = detect_emotion(user_input, "")
    notify("stage_changed", stage="translating_input")
    input_translation = translator.translate_korean_input(user_input)
    if input_translation is None:
        notify("notice", code="input_translation_failed", message="입력 번역에 실패했습니다. Ollama 번역 모델 연결을 확인한 뒤 다시 시도해 주세요.")
        return TurnResult("failed", errors=("input_translation_failed",))
    if input_translation.status == "ambiguous":
        notify("notice", code="ambiguous_input", message="입력이 조금 불분명합니다. 다시 말하거나 입력해 주세요.")
        return TurnResult("failed", errors=("ambiguous_input",))
    japanese_input = input_translation.translation
    notify("input_translated", source=user_input,
           normalized_source=input_translation.normalized_source, japanese_input=japanese_input)
    style = emotion_style.get(pre_emotion, emotion_style["normal"])

    messages.append({"role": "user", "content": japanese_input})
    # Apply the current delivery style to this request only, never to history.
    request_messages = [
        {"role": "system", "content": messages[0]["content"] + (
            f"\n今回の口調: {style}\n"
            "この雰囲気は感情の表現に反映し、ユーザーが明示的に求めない限り、"
            "ユーザーがため口でも返答は丁寧な話し言葉（です・ます）を保ってください。"
            "不要な呼びかけや状況描写を足さず、質問や気持ちに短く直接答えてください。"
            "話し方の参考例：「そうなんですね。少し休みましょうか。」"
            "「それは嬉しいですね。どんなことがあったんですか？」。"
            "例の内容を会話の事実として扱わず、その丁寧で自然な話し方だけを参考にしてください。"
        )},
        *[dict(message) for message in messages[1:]],
    ]
    notify("stage_changed", stage="generating")
    ai_reply = japanese_response.generate_validated_japanese_reply(request_messages)
    if ai_reply is None:
        # The user turn was not answered safely, so keep no invalid exchange in
        # history and do not let subtitle or TTS consume any part of it.
        messages.pop()
        notify("notice", code="japanese_reply_failed", message="AI 일본어 응답 검증에 실패했습니다. 이번 응답은 재생·자막·기록에 사용하지 않습니다.")
        return TurnResult("failed", errors=("japanese_reply_failed",))

    emotion = pre_emotion
    notify("reply_ready", emotion=emotion, japanese_reply=ai_reply)
    notify("stage_changed", stage="translating_subtitle")
    korean_subtitle = translator.japanese_to_korean(ai_reply)
    notify("subtitle_ready", korean_subtitle=korean_subtitle)
    errors = []
    if korean_subtitle is None:
        errors.append("subtitle_failed")

    tts_text = clean_for_tts(ai_reply)
    tts_text, speed = apply_emotion_to_tts(tts_text, emotion)
    tts_text = limit_text(tts_text)

    notify("tts_prepared", text=tts_text, speed=speed)
    audio_played = False

    if tts_text:
        notify("stage_changed", stage="synthesizing")
        ok = tts.speak(tts_text, speed, emotion, 6.0)
        if ok:
            notify("stage_changed", stage="speaking")
            audio_played = play_with_expression(emotion)
            if not audio_played:
                errors.append("playback_failed")
                logging.error("TTS audio was created but could not be played.")
        else:
            errors.append("synthesis_failed")
            notify("notice", code="synthesis_failed", message="TTS 생성 실패: output.wav 생성에 실패했습니다.")
    else:
        errors.append("empty_tts_text")
        notify("notice", code="empty_tts_text", message="TTS로 읽을 문장이 없음")

    messages.append({"role": "assistant", "content": ai_reply})

    if len(messages) > MAX_HISTORY + 1:
        messages[:] = [messages[0]] + messages[-MAX_HISTORY:]

    return TurnResult(
        "partial_failure" if errors else "completed",
        japanese_reply=ai_reply, korean_subtitle=korean_subtitle,
        emotion=emotion, audio_played=audio_played, errors=tuple(errors),
    )
