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
* 🟢 일본어 → 한국어 자막 번역 및 검증
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

일본어 → 한국어 자막 번역
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
별도로 한국어 자막을 생성해 화면에 표시합니다.

감정 분석 결과에 따라 음성 속도와 스타일을 조절하며,
추후 VTube Studio의 표정과 모션에도 연결할 예정입니다.

---

# 🛠️ 기술 스택 (Tech Stack)

## 언어 (Language)

* Python

## AI 및 번역 (AI & Translation)

* Ollama

  * 캐릭터 대화 생성
  * 한국어 ↔ 일본어 번역
  * 환경변수를 통한 대화 모델과 번역 모델 분리
* JSON 형식 기반 번역 결과 검증
* 일본어·한국어 혼합 출력 감지 및 재생성

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
