"""Console entry point for the shared Python conversation flow."""

from backend.conversation.service import ConversationSession, TurnEvent, create_session, process_turn
from backend.logging_setup import configure_console_logging
from backend.subtitle_ui import format_korean_subtitle


def print_turn_event(event: TurnEvent) -> None:
    data = event.data
    if event.kind == "input_translated":
        source = data["source"]
        normalized = data["normalized_source"]
        if normalized != source.strip():
            print(f"입력 보정: '{source}' → '{normalized}'")
        if data["japanese_input"] != source:
            print("JP:", data["japanese_input"])
    elif event.kind == "reply_ready":
        print("감정:", data["emotion"])
        print("AI (JP):", data["japanese_reply"])
    elif event.kind == "subtitle_ready":
        print(format_korean_subtitle(data["korean_subtitle"]))
    elif event.kind == "tts_prepared":
        print("TTS용 문장:", data["text"])
        print("속도:", data["speed"])
    elif event.kind == "notice":
        print(data["message"])


def run_cli() -> ConversationSession:
    configure_console_logging()
    session = create_session()
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
            session.reset()
            print("대화 기록 초기화 완료.")
            continue

        process_turn(session, user_input, emit=print_turn_event)

    return session


if __name__ == "__main__":
    run_cli()
