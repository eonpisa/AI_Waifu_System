# AI Waifu System

> Local AI 기반 가상 캐릭터 시스템

> LLM, TTS, Character System을 기반으로 확장 가능한 AI 캐릭터 시스템 구현

---

## 📌 프로젝트 소개 (Project Introduction)

AI Waifu System은 사용자의 입력을 이해하고,
자연스러운 대화와 음성 출력을 제공하는
AI 기반 가상 캐릭터 시스템입니다.

단순한 챗봇이 아닌,
STT(Speech To Text),
LLM(Large Language Model),
TTS(Text To Speech),
Character System을 결합하여

실시간 상호작용이 가능한 AI 캐릭터 구현을 목표로 합니다.

현재 프로젝트는 개발 중이며,
기능과 구조가 계속 변경될 수 있습니다.

실제 검증 상태, 1차 완성 범위와 작업 순서는 [PROJECT_PLAN.md](PROJECT_PLAN.md)에서 관리합니다.
아래 상태 표시는 사용자 안내이며, 코드 구현과 사용자 환경에서의 검수 완료는 구분합니다.

---

# 🚦 상태 표시

* 🟢 구현 완료 또는 현재 사용 중
* 🟡 개발 예정, 개선 중 또는 현재 사용 보류
* 🔴 오류가 있거나 현재 사용하지 않아 삭제·교체 예정

---

# 🗺️ 계획 (Roadmap)

## 핵심 기능 (Core Features)

* 🟢 Ollama 기반 대화 시스템
* 🟢 한국어 입력 보정 및 한국어 → 일본어 번역
* 🟢 일본어 AI 응답 검증 및 재생성
* 🟢 Gemini 기반 일본어 → 한국어 자막 번역 및 검증
* 🟢 대화 중 일본어·한국어·중국어 등 혼합 언어 감지
* 🟢 현재 실행 중인 대화의 단기 기록 관리
* 🟢 감정 분석 시스템
* 🟡 일본어 → 한국어 자막 번역 품질 개선
* 🟡 STT 음성 입력
* 🟡 대화 내용 저장
* 🟡 RAG 기반 장기 기억 시스템

## TTS 시스템 (TTS System)

* 🟢 Style-Bert-VITS2(SBV2) 연동

  * 현재 주력으로 사용하는 TTS 방식
  * 일본어 AI 응답을 음성으로 합성
  * 감정에 따른 말하기 속도와 스타일 적용
* 🟡 CosyVoice 2

  * 연동 기능은 구현되어 있음
  * 현재는 주력으로 사용하지 않고 보류
  * 필요할 경우 선택형 TTS 방식으로 다시 사용 가능
* 🟢 Windows, macOS, Linux 환경별 WAV 음성 재생
* 🟢 TTS 실패 시 프로그램이 종료되지 않도록 예외 처리

## 캐릭터 시스템 (Character System)

* 🟢 감정별 표정 프리셋
* 🟡 VTube Studio 연동

  * API 연결과 표정 적용 코드는 구현되어 있음
  * 메인 실행 흐름 연결 및 안정화 작업 예정
* 🟡 캐릭터 행동 시스템
* 🟡 표정 및 모션 개선
* 🟡 Live2D 캐릭터 연동 개선

## 향후 계획 (Future Plans)

* 🟡 VR 환경 지원
* 🟡 로봇 플랫폼 연동

---

# 🏗️ 시스템 구조 (System Structure)

```text
사용자 입력
(현재 키보드 입력 / STT 구현 예정)

↓

한국어 입력 보정
한국어 → 일본어 번역 및 검증

↓

Ollama LLM
일본어 AI 응답 생성

↓

일본어 응답 검증
잘못된 응답 감지 및 재생성

↓

감정 분석

↓

Gemini 일본어 → 한국어 자막 번역
(실패 시 Ollama Qwen fallback)
+
SBV2 일본어 음성 합성

↓

한국어 자막 출력
+
WAV 음성 재생

↓

VTube Studio 캐릭터 표현
(연동 개선 중)
```

### 동작 과정 (Process)

현재는 사용자가 한국어로 입력하면
입력 내용을 확인하고 일본어로 번역합니다.

번역된 일본어 입력을 Ollama 기반 LLM에 전달하고,
AI가 생성한 응답이 자연스러운 일본어로만 이루어졌는지 검사합니다.

응답에 한국어, 중국어, 영어, 러시아어 또는 설명문이 섞이면
해당 응답을 거부하고 한 번 다시 생성합니다.

검증된 일본어 응답은 TTS 음성으로 사용하며,
Gemini API로 한국어 자막을 생성해 화면에 표시합니다.
Gemini 호출 또는 결과 검증이 실패하면 기존 Ollama Qwen 번역을 사용합니다.

감정 분석 결과에 따라 음성 속도와 스타일을 조절하며,
추후 VTube Studio의 표정과 모션에도 연결할 예정입니다.

---

# 🛠️ 기술 스택 (Tech Stack)

## 언어 (Language)

* Python

## AI 및 번역 (AI & Translation)

* Ollama

  * 캐릭터 대화 생성
  * 한국어 → 일본어 번역
  * Gemini 실패 시 일본어 → 한국어 fallback 번역
  * 환경변수를 통한 대화 모델과 번역 모델 분리
* Gemini API

  * 일본어 → 한국어 자막 번역
  * 구조화 JSON 출력과 기존 검증 로직 사용
* JSON 형식 기반 번역 결과 검증
* 일본어·한국어 혼합 출력 감지 및 재생성

### Gemini API 설정

키는 아래 macOS 실행 절차의 숨김 입력으로 받습니다. `.env`, 소스, 설정 파일,
셸 명령에 키 값을 적지 않습니다. 키 누락 또는 Gemini 실패 시 Qwen 자막으로
전환되므로, Gemini 검수는 `provider=gemini model=gemini-3.5-flash-lite fallback_reason=none`
로그를 기준으로 합니다.

### 현재 정상 실행 기준 — macOS / zsh

이 절차는 기존 개인 실행 환경 기준입니다. SBV2 소스·학습 모델·개인
`tts_config.json`은 이 저장소에 포함하지 않습니다. 새 clone만으로 바로 실행되는
배포 패키지는 아닙니다. 아래 경로는 사용자 환경에 맞게 조정합니다.

기존 SBV2의 `style_bert_vits2/nlp/bert_models.py`에서 transformers 4.51.3과
호환되도록 두 `from_pretrained()` 호출의 `dtype="float32"`를
`torch_dtype="float32"`로 수정한 환경을 검수했습니다. fp32 지정 의도는 유지하며,
원격에서 제거된 SBV2 소스 전체는 다시 포함하지 않습니다.

프로젝트 Python은 `/Users/eonpisa_1017/Desktop/AI_Waifu_System/.venv/bin/python`
(확인 버전 3.11.0)입니다. 서버와 앱 모두 이 환경을 사용합니다.

| 항목 | 실행 기준·설정 출처 |
| --- | --- |
| Ollama | `http://127.0.0.1:11434/api/chat`, 대화·번역 모델 `qwen3.5:9b` |
| SBV2 서버 | `SBV2-KR-master/config.yml`의 `server.port: 5001` |
| SBV2 모델 위치 | `SBV2-KR-master/configs/paths.yml`의 `assets_root: model_assets`, 기존 개인 모델 유지 |
| 앱 TTS | 프로젝트 `tts_config.json`: `backend: sbv2`, `sbv2.api_url: http://127.0.0.1:5001`, `fallback_to_cosyvoice: false` |
| Gemini | 프로세스 환경변수 `GEMINI_API_KEY`, 모델 `gemini-3.5-flash-lite`, REST `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent` |
| 재생 | macOS `afplay`, 프로젝트 `output.wav`를 매 합성 시 교체 |

1. Ollama 앱 또는 기존 서버를 실행합니다. 이미 실행 중이면 새 서버를 띄우지 않습니다.
   `curl -fsS http://127.0.0.1:11434/api/tags`에서 기존 `qwen3.5:9b` 모델을 확인합니다.
   Ollama CLI로 기동할 경우 별도 터미널에서 `ollama serve`를 사용합니다.
2. SBV2용 터미널에서 실행합니다. 이미 5001 서버가 정상 실행 중이면 그대로 사용합니다.

   ```bash
   cd /Users/eonpisa_1017/Desktop/AI_Waifu_System/SBV2-KR-master
   ../.venv/bin/python -B server_fastapi.py
   ```

   `--port` 옵션은 지원하지 않습니다. 포트는 `config.yml`에서 읽습니다.
   현재 서버 코드는 CUDA가 없으면 CPU를 선택하므로 이 Mac에서는 CPU 경로입니다.
   브라우저의 `http://127.0.0.1:5001/docs` 또는 아래 명령으로 확인합니다.

   ```bash
   curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5001/docs
   ```

   통과 기준은 HTTP 200입니다. 문서 응답만으로 합성 성공을 판정하지 않습니다.
3. 앱용 zsh 터미널에서 다음 블록을 실행하고 키를 숨김 입력합니다.
   괄호 안의 별도 셸에서만 키·실행 설정을 유지하며, 앱 종료 후 부모 셸에 키를 남기지 않습니다.

   ```zsh
   (
     set +x
     cd /Users/eonpisa_1017/Desktop/AI_Waifu_System || exit 1
     source .venv/bin/activate
     export OLLAMA_API_URL='http://127.0.0.1:11434/api/chat'
     export OLLAMA_CHAT_MODEL='qwen3.5:9b'
     export OLLAMA_TRANSLATOR_MODEL='qwen3.5:9b'
     export TTS_CONFIG_PATH="$PWD/tts_config.json"
     export TTS_BACKEND='sbv2'
     export SBV2_API_URL='http://127.0.0.1:5001'
     export TTS_FALLBACK_TO_COSYVOICE='false'
     export GEMINI_TRANSLATOR_MODEL='gemini-3.5-flash-lite'
     export GEMINI_API_BASE_URL='https://generativelanguage.googleapis.com/v1beta'
     export AI_WAIFU_DEBUG='0'
     read -rs 'GEMINI_API_KEY?Gemini API 키(입력 숨김): ' || exit 1
     print
     [[ -n "$GEMINI_API_KEY" ]] || exit 1
     export GEMINI_API_KEY
     python -B main.py
     unset GEMINI_API_KEY
   )
   ```

   초기 Enter를 누른 뒤 한국어 문장을 입력합니다. 일본어 응답 → Gemini 한국어 자막
   → 음성 재생 → 다음 `너:` 복귀를 확인합니다. 종료는 `종료`입니다.
   `-B`는 바이트코드 캐시 생성을 억제하며 앱 동작은 `python main.py`와 같습니다.

반드시 프로젝트 루트에서 앱을 실행합니다. TTS 저장 위치는 프로젝트 기준이지만
현재 재생 파일 경로는 작업 폴더 기준입니다. 환경변수는 JSON보다 우선하며,
`tts_config.local.json`은 자동으로 읽지 않습니다. 설정 누락 시 코드에는 5000 및
CosyVoice 기본값이 남아 있으므로 위 명시 설정과 기존 `tts_config.json`을 사용합니다.
Qwen 자막 폴백과 CosyVoice 음성 폴백은 별개입니다.

자동 테스트는 프로젝트 루트에서 실행합니다.

```bash
.venv/bin/python -B -m unittest discover -s tests -q
```

기능별 검수 결과와 일반 실행의 남은 확인 사항은 `PROJECT_PLAN.md`에서 관리합니다.

## 음성 합성 (TTS)

* 🟢 Style-Bert-VITS2(SBV2)

  * 현재 주력 TTS
* 🟡 CosyVoice 2

  * 연동 완료
  * 현재 사용 보류

## 캐릭터 시스템 (Character System)

* VTube Studio Public API
* Live2D

---

# 📂 폴더 구조

```text
AI_Waifu_System/
├── README.md
├── main.py                 # 전체 대화·번역·감정·TTS 실행 흐름
├── llm.py                  # Ollama 채팅 API 호출과 모델 설정
├── translator.py           # 한국어↔일본어 번역 및 결과 검증
├── japanese_response.py    # 일본어 AI 응답 검증 및 재생성
├── tts.py                  # SBV2 주력 음성 합성 및 CosyVoice 2 선택형 연동
├── audio_playback.py       # 운영체제별 WAV 음성 재생
├── subtitle_ui.py          # 한국어 자막 출력 형식 관리
├── emotion.py              # 감정 감지와 표정·음성 프리셋
├── vts.py                  # VTube Studio 연결 및 표정 적용
├── logging_setup.py        # 일반·디버그 로그 설정
├── stt.py                  # 🟡 STT 구현 예정
└── ai.py                   # 🔴 현재 사용하지 않는 이전 Ollama 호출 코드로 삭제 예정
```

실행 과정에서 생성되거나 개인 설정이 포함되는
`output.wav`, `tts_config.json`, `vts_token.txt`, TTS 모델 파일 등은
프로젝트의 기본 폴더 구조에 포함하지 않습니다.

---

# 🗨️ 피드백 (Feedback)

현재 이 프로젝트는 아직 개발 중이며,
기능이나 구조가 계속 변경될 수 있습니다.

사용 중 발견한 버그, 개선할 점, 추가했으면 하는 기능 등
프로젝트와 관련된 피드백은 언제든지 GitHub Issues를 통해 남겨주세요.

가능한 범위에서 피드백을 확인하고
추후 개발 및 개선 과정에 참고할 예정입니다.

다만 캐릭터 음성 구현을 위해 직접 학습한 TTS 모델과
학습에 사용된 데이터는 공개하거나 배포할 계획이 없습니다.

TTS 모델을 제외한 프로젝트의 기능, 구조, 사용성 등에 대한
피드백은 자유롭게 남겨주셔도 됩니다.
