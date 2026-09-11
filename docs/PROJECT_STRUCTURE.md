# 프로젝트 파일 안내

현재 개발 폴더의 파일 역할과 실행 기준이다. Python 모듈을 역할별 backend
패키지로 이동했고 루트 Python 파일은 CLI 진입점 `main.py`만 유지한다. 세부 검수 기록은 로컬 전용
`PROJECT_PLAN.md`, API 사용법은 `backend/README.md`에서 관리한다.

## 실행 진입점

| 위치 | 역할 |
| --- | --- |
| `main.py` | 기존 CLI. `.venv/bin/python -B main.py` |
| `backend/` | 단일 세션 HTTP/WebSocket API. `.venv/bin/python -B -m backend` |
| `frontend/` | React·TypeScript·Vite 화면 미리보기. 해당 폴더에서 `npm run dev`, 127.0.0.1:5173. 현재 모의 데이터만 사용 |
| `backend/conversation/service.py` | CLI와 API가 공유하는 세션·한 턴 처리·음성/VTS 실행 |
| `backend/character/vts.py` | 단독 표정 테스트는 루트에서 `.venv/bin/python -B -m backend.character.vts`. 기본 4초 유지 |
| `SBV2-KR-master/server_fastapi.py` | 별도 SBV2 서버 진입점. 해당 폴더에서 프로젝트 Python으로 실행 |
| `local_checks/check_conversation.py` | 로컬 수동 검수 도구. Git 제외 |

CLI와 API는 WAV와 VTS를 공유하므로 동시에 실행하지 않는다.
기본 API는 127.0.0.1:8000, SBV2는 기존 5001번 설정을 사용한다.
Gemini 키는 실행 프로세스의 환경변수로만 전달한다.

## 공통 모듈

| 파일 | 역할 |
| --- | --- |
| `backend/api/app.py`, `runtime.py`, `schemas.py` | HTTP/WebSocket·한 번에 한 턴 실행·공개 데이터 형식 |
| `backend/conversation/llm.py` | 현재 Ollama HTTP 요청 |
| `backend/conversation/legacy_ai.py` | 사용하지 않는 이전 OpenAI SDK 기반 코드 보존. 자동 import하지 않음 |
| `backend/translation/translator.py`, `gemini_translator.py` | 입력 변환과 Gemini/Qwen 자막 번역 |
| `backend/conversation/japanese_response.py` | 일본어 응답 검증·재생성 |
| `backend/character/emotion.py` | 기존 감정 판정·음성용 문장 처리 |
| `backend/voice/tts.py`, `audio_playback.py` | 음성 합성·로컬 WAV 재생 |
| `backend/character/vts.py` | VTS 인증·표정·WAV 음량 기반 립싱크 |
| `backend/subtitle_ui.py`, `logging_setup.py` | CLI 자막 표시·로깅 |
| `backend/voice/stt.py` | 현재 비어 있는 구현 예정 자리. STT 완료를 뜻하지 않음 |
| `scripts/download_elaina.py` | 데이터 준비용 별도 스크립트. 루트에서 실행하며, import만 해도 데이터 작업을 하므로 자동 import하지 않음 |

## 테스트·의존성·문서

- `tests/`: 공통 대화·CLI·번역·음성·VTS·API 자동 테스트.
  `.venv/bin/python -B -m unittest discover -s tests`로 실행한다.
- `requirements.txt`: 현재 CLI·API·자동 테스트의 직접 의존성. API 목록을 포함한다.
  데이터 준비용 선택 패키지는 주석으로 구분하며 SBV2 서버 설치 목록은 아니다.
- `requirements-api.txt`: API용 의존성만 명시한다. 전체 AI/TTS 환경의 설치
  목록이 아니며 기존 `.venv`를 재현하는 완전한 의존성 명세도 아니다.
- `README.md`: 기존 사용자 안내를 유지한다.
- `backend/README.md`: API 명세·실행 방법·종료 동작.
- `frontend/README.md`: 화면 미리보기 실행·Node 조건·자동/수동 검수. JS 의존성은 `frontend/package.json`과 lockfile로 Python과 분리한다.
- `docs/PROJECT_STRUCTURE.md`: 이 파일 안내.
- `PROJECT_PLAN.md`: 로컬 작업·검수 기록. 원격에 다시 추가하지 않는다.

비어 있던 예전 루트 `requirements.txt`는 로컬 보관 폴더에 유지하고,
사용자 요청으로 현재 실행 코드와 설치 버전에 근거한 새 목록을 작성했다.
전체 환경의 의존성을 임의로 추정하거나 `pip freeze`로 덮어쓰지 않았다.

## 그대로 보존하는 로컬 자산

- `.venv/`: 기존 실행 환경.
- `SBV2-KR-master/`, `Style-Bert-VITS2/`: 서로 다른 소스/환경/자산이 포함될
  수 있으므로 중복 폴더라고 간주해 합치거나 삭제하지 않는다.
- `elaina_dataset/`, 모델·학습 데이터: 비공개 자산.
- `tts_config.json`, `vts_token.txt`: 개인 설정·인증정보. 내용 공유 금지.
- `audio.wav`, `output.wav`: 개인 음원·실행 산출물. 현재 경로 유지.
- `artifacts/`: 과거 로컬 검수 산출물. 내용과 위치를 보존하고 Git에서 제외.
- `local_checks/backups/`: 기존 검증된 백업. 새 백업에 재귀 복사하지 않는다.
- `local_checks/archive/`: 이번 정리의 복원 가능한 보관본. Git 제외.

Git 제외 규칙은 이미 추적된 파일을 자동으로 제외하지 않는다. 커밋 전에
별도로 대상 목록을 검토해야 한다. Python 이동의 이름 변경과 import 수정은 함께 커밋해야 한다. `PROJECT_PLAN.md`는 루트 Git 제외 규칙으로 보호한다.

## 이전 임시 파일 정리와 복원

`KO`(빈 파일), `requirements.txt`(빈 파일), `tempCodeRunnerFile.py`(불완전한
임시 코드 조각)를 `local_checks/archive/20260911-083826-file-cleanup/`으로
옮겼다. 같은 폴더의 `manifest.json`에 원래 상대 경로·크기·SHA-256을 기록했고,
크기와 해시를 검증했다. `.gitignore` 수정 전 내용은 `gitignore.before`에 있다.

복원이 필요하면 보관본을 원래 위치로 복사하되, 그 위치에 새 파일이 있다면
먼저 비교한다. `.gitignore`도 이후 변경을 덮어쓰지 않도록 비교 후 복원한다.
모델·키·토큰·개인 설정은 이 보관본에 포함하지 않았다.

Python 패키지 이동 전 소스·테스트·문서의 검증된 백업은
`local_checks/backups/20260911-132135-python-layout/`에 있다.
개인 설정·토큰·WAV와 frontend 파일은 내용을 백업하지 않고 보존 확인용 해시만
기록했다. 기존 모델·가상환경·SBV2 폴더는 이동하지 않았다.
