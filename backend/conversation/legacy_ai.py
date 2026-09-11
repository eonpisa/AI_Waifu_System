from openai import OpenAI

# 🌟 Ollama 로컬 서버 주소와 모델명으로 수정
client = OpenAI(
    base_url="http://localhost:11434/v1",  # Ollama의 OpenAI 호환 엔드포인트
    api_key="ollama"                       # 로컬이라 아무 문자나 넣어도 작동합니다
)


# 내가 다운로드받은 Qwen 모델명을 정확히 적어줍니다
MODEL_NAME = "qwen3.6:latest"  # 💡 만약 qwen3 계열이나 다른 이름이라면 그 이름으로 변경해 주세요!

def get_ai_response(messages):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.7,
            # 예전 코드에 존재하던 챗봇 페르소나 설정 등은 그대로 유지하시면 됩니다!
        )
        return response.choices[0].message.content
    except Exception as e:
        print("로컬 Ollama 호출 실패:", e)
        return "뇌(Ollama)가 응답하지 않아. 터미널에서 ollama run이 잘 켜져 있는지 확인해 줘."
