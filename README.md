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

---

# 🗺️ 계획 (Roadmap)

## 핵심 기능 (Core Features)

- [x] LLM 기반 대화 시스템
- [x] TTS 음성 출력
- [x] 감정 분석 시스템
- [ ] STT 음성 입력
- [ ] Memory System
    - [ ] 대화 저장
    - [ ] RAG 기반 장기 기억

## 캐릭터 시스템 (Character System)

- [ ] VTube Studio 연동
- [ ] 캐릭터 행동 시스템
- [ ] 표정 및 모션 개선
- [ ] Live2D 연동

## 향후 계획 (Future Plans)

- [ ] VR 환경 지원
- [ ] 로봇 플랫폼 연동

---

# 🏗️ 시스템 구조 (System Structure)

User Input

↓

STT (예정 / Planned)
(Speech Recognition)

↓

LLM
(Local / API Model)

↓

Memory System
(RAG / Vector DB)

↓

TTS
(Voice Generation)

↓

Character System
(Live2D / Avatar)


### 동작 과정 (process)

사용자의 입력을 STT(Speech To Text)를 통해 텍스트로 변환하고,
LLM(Large Language Model)이 대화를 처리합니다.

Memory System을 통해 대화 정보를 관리하며,
TTS(Text To Speech)를 이용해 음성을 생성한 뒤
Character System과 연결하여 캐릭터 표현을 구현합니다.

---

# 🛠️ 기술 스택 (Tech Stack)

## 언어 (Language)

- Python

## AI

- Ollama
- SBV2

## 라이브러리 (Libraries)

- requests
- torch
- torchaudio
- websockets

## 캐릭터 시스템 (Character System)

- VTube Studio

---

# 📂 폴더 구조

```text
AI-Waifu-System
│
├── main.py
├── requirements.txt
├── README.md
│
├── ai/
│   ├── llm.py
│   ├── memory.py
│   └── prompt.py
│
├── voice/
│   ├── stt.py
│   └── tts.py
│
├── character/
│   └── emotion.py
│
├── data/
│   └── memory.json (추가 예정)
│
└── config/
    └── settings.py
```
