# 프로젝트 파일 안내

CLI와 로컬 API가 공통 Python 대화 로직을 사용합니다. 실행 방법은
[루트 README](../README.md), API 안내는 [백엔드 README](../backend/README.md)를 참고하세요.

## 실행 진입점

명령은 별도 안내가 없으면 프로젝트 루트에서 실행합니다.

| 위치 | 역할 |
| --- | --- |
| `main.py` | CLI. `.venv/bin/python -B main.py` |
| `backend/__main__.py` | 단일 세션 HTTP/WebSocket API. `.venv/bin/python -B -m backend` |
| `frontend/` | React·TypeScript·Vite 대화 화면. 해당 폴더에서 `npm run dev` |
| `backend/character/vts.py` | 단독 표정 검수. `.venv/bin/python -B -m backend.character.vts`, 기본 4초 |

CLI와 API는 WAV와 VTS를 공유하므로 하나만 실행합니다. 기본 주소는
API `127.0.0.1:8000`, 웹 화면 `127.0.0.1:5173`입니다.
`?preview=1`은 서비스 연결 없이 동작하는 화면 미리보기입니다.

Ollama(11434), SBV2(5001), VTS(8001)는 별도로 실행합니다.
별도 준비한 SBV2 소스의 `SBV2-KR-master/`에서
`../.venv/bin/python -B server_fastapi.py`로 서버를 시작합니다.
Gemini 키는 실행 프로세스의 환경변수로만 전달합니다.

## 백엔드 모듈

| 파일 | 역할 |
| --- | --- |
| `backend/api/app.py`, `runtime.py`, `schemas.py` | HTTP/WebSocket·단일 세션·한 번에 한 턴 처리·공개 데이터 형식 |
| `backend/conversation/service.py` | CLI/API 공통 세션·한 턴 처리·음성/VTS 실행 |
| `backend/conversation/llm.py` | Ollama HTTP 요청 |
| `backend/conversation/japanese_response.py` | 일본어 응답 검증·재생성 |
| `backend/translation/translator.py`, `gemini_translator.py` | 입력 변환과 Gemini/Qwen 자막 번역 |
| `backend/voice/tts.py`, `audio_playback.py` | 음성 합성·로컬 WAV 재생 |
| `backend/voice/stt.py` | 선택형 로컬 모델을 사용한 한국어 녹음 전사. 웹 녹음은 `/api/transcribe`로 전달 |
| `backend/character/emotion.py` | 감정 판정·음성용 문장 처리 |
| `backend/character/vts.py` | VTS 인증·표정·WAV 음량 기반 립싱크 |
| `backend/service_status.py` | 요청별 서비스 결과·번역기 정보를 안전한 공개 코드로 전달 |
| `backend/subtitle_ui.py`, `logging_setup.py` | CLI 자막 표시·로깅 |
| 각 패키지의 `__init__.py` | Python 패키지 구성. import만으로 대화를 실행하지 않음 |

## 테스트·의존성·문서

- `tests/`: 공통 대화·CLI·번역·음성·VTS·API 자동 테스트.
  `.venv/bin/python -B -m unittest discover -s tests`로 실행합니다.
- `frontend/src/*.test.ts`, `*.test.tsx`: 화면과 HTTP/WebSocket 클라이언트 테스트.
  `frontend/`에서 `npm test`로 실행합니다.
- `requirements.txt`: CLI·API·자동 테스트의 직접 의존성. API 목록을 포함하며 SBV2 서버 설치 목록은 아닙니다.
- `requirements-api.txt`: FastAPI와 API 실행·데이터 처리에 필요한 패키지 목록입니다.
- `requirements-stt.txt`: 웹 마이크 입력에만 필요한 선택형 로컬 STT 의존성입니다. 모델 파일은 별도 준비합니다.
- `frontend/package.json`, `package-lock.json`: 프론트엔드 의존성과 고정된 설치 버전입니다.
- [backend/README.md](../backend/README.md): 백엔드 역할·실행·주요 API·주의사항.
- [docs/backend-api.md](backend-api.md): 요청·응답·WebSocket·오류·종료 처리 상세 명세.
- [frontend/README.md](../frontend/README.md): 화면 실행·미리보기·Node 조건·검수 방법.

## Git에 포함하지 않는 파일

모델·학습 데이터, WAV, `.env`, Gemini 키, `vts_token.txt`, `tts_config.json` 등
개인 설정·인증정보는 공개 저장소에 포함하지 않습니다. `.venv/`와 프론트엔드
`node_modules/`, `dist/` 같은 환경·생성물도 제외합니다.

제외 규칙은 `.gitignore`에서 관리합니다. 이미 추적된 파일에는 제외 규칙만으로
추적 해제가 적용되지 않으므로 커밋 대상을 별도로 확인해야 합니다.
