import threading
import asyncio
import os
import logging


from logging_setup import configure_console_logging
from translator import japanese_to_korean, translate_korean_input
from japanese_response import generate_validated_japanese_reply
from subtitle_ui import format_korean_subtitle
from tts import speak
from vts import apply_expression
from audio_playback import play_wav
from emotion import (
    detect_emotion,
    clean_for_tts,
    limit_text,
    apply_emotion_to_tts
)


configure_console_logging()


messages = [
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
messages[0]["content"] += "\n\n重要: 返答は自然な日本語だけで書いてください。中国語、韓国語、翻訳、括弧での説明、注釈を絶対に含めないでください。"
messages[0]["content"] += """

会話の役割と事実:
user は話しかけているユーザー、assistant はあなたです。両者の経験や予定を混同しないでください。
user の「私」「僕」はユーザーを指し、assistant の「私」はあなたを指します。
まず最新のユーザーの質問に直接答えてください。過去の話を尋ねられたら、この会話の user 発言を確認してください。
誰が・いつ・誰と・何をしたか、何をする予定かを保って答えてください。
ユーザー自身についての事実は user 発言を根拠にし、矛盾する場合は最新の明示的な訂正を優先してください。
assistant が想像したことや自分の希望を、ユーザーの事実として扱わないでください。
会話に根拠がない場合は、勝手に補わず分からないと伝えてください。
口調の指示より質問への正確な回答を優先してください。ユーザーが泣いている等の感情や行動を決めつけないでください。
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

def run_expression(emotion, duration=4.0):
    asyncio.run(apply_expression(emotion, duration=duration))

input("초기 입력 버퍼 제거용. Enter를 눌러 시작: ")

while True:
    user_input = input("너: ")
    print("입력값:", repr(user_input))

    if user_input.lower().strip() in [
        "d:\\ai_agent\\venv\\scripts\\activate",
        "venv\\scripts\\activate",
        "activate"
    ]:
        print("터미널 명령어 대화 입력에서 무시.")
        continue

    if not user_input.strip():
        continue

    if user_input.strip() == "종료":
        break

    if user_input.strip() == "기록초기화":
        messages = [messages[0]]
        print("대화 기록 초기화 완료.")
        continue

    # Emotion remains based on the original Korean input, before translation.
    pre_emotion = detect_emotion(user_input, "")
    input_translation = translate_korean_input(user_input)
    if input_translation is None:
        print("입력 번역에 실패했습니다. Ollama 번역 모델 연결을 확인한 뒤 다시 시도해 주세요.")
        continue
    if input_translation.status == "ambiguous":
        print("입력이 조금 불분명합니다. 다시 말하거나 입력해 주세요.")
        continue
    japanese_input = input_translation.translation
    if input_translation.normalized_source != user_input.strip():
        print(f"입력 보정: '{user_input}' → '{input_translation.normalized_source}'")
    if japanese_input != user_input:
        print("JP:", japanese_input)
    style = emotion_style.get(pre_emotion, emotion_style["normal"])

    messages.append({"role": "user", "content": japanese_input})
    # Apply the current delivery style to this request only, never to history.
    request_messages = [
        {"role": "system", "content": messages[0]["content"] + f"\n今回の口調: {style}"},
        *[dict(message) for message in messages[1:]],
    ]
    ai_reply = generate_validated_japanese_reply(request_messages)
    if ai_reply is None:
        # The user turn was not answered safely, so keep no invalid exchange in
        # history and do not let subtitle or TTS consume any part of it.
        messages.pop()
        print("AI 일본어 응답 검증에 실패했습니다. 이번 응답은 재생·자막·기록에 사용하지 않습니다.")
        continue

    emotion = pre_emotion
    print("감정:", emotion)

    print("AI (JP):", ai_reply)
    korean_subtitle = japanese_to_korean(ai_reply)
    print(format_korean_subtitle(korean_subtitle))

    tts_text = clean_for_tts(ai_reply)
    tts_text, speed = apply_emotion_to_tts(tts_text, emotion)
    tts_text = limit_text(tts_text)

    print("TTS용 문장:", tts_text)
    print("속도:", speed)

    if tts_text:
        ok = speak(tts_text, speed, emotion, 6.0)
        if ok:
            if not play_wav("output.wav"):
                logging.error("TTS audio was created but could not be played.")
        else:
            print("TTS 생성 실패: output.wav 생성에 실패했습니다.")
    else:
        print("TTS로 읽을 문장이 없음")

    messages.append({"role": "assistant", "content": ai_reply})

    if len(messages) > MAX_HISTORY + 1:
        messages = [messages[0]] + messages[-MAX_HISTORY:]
