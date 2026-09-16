# 백엔드

기존 Ollama·Gemini·SBV2·VTS 기능을 React 화면에 연결하는 로컬 FastAPI 서버입니다.
CLI와 API는 같은 Python 대화 로직을 사용합니다.

## 실행

프로젝트 루트에서 기존 가상환경으로 실행합니다.

```sh
.venv/bin/python -B -m backend
```

- 서버: `http://127.0.0.1:8000`
- API 문서: `http://127.0.0.1:8000/docs`
- Gemini 키: 서버 프로세스의 `GEMINI_API_KEY` 환경변수로만 사용합니다.
  숨김 입력 실행 명령은 [상세 문서의 실행 안내](../docs/backend-api.md#실행)를 참고하세요.

## 주요 API

| 경로 | 역할 |
| --- | --- |
| `GET /api/health` | API 서버 응답 확인 |
| `GET /api/state` | 현재 처리 상태와 최근 결과 조회 |
| `POST /api/turn` | 한국어 메시지 전송 |
| `POST /api/end` | 진행 중인 턴이 끝난 뒤 대화 종료 |
| `WS /api/events` | 진행 상태·응답·자막·서비스 결과 수신 |

## 주의사항

- Ollama(11434), SBV2(5001), VTS(8001)는 별도로 실행합니다.
- CLI(`python main.py`)와 API는 음성 파일·VTS를 공유하므로 하나만 실행합니다.
- 단일 사용자·단일 세션용이며, 기본 주소는 `127.0.0.1`입니다.
- 키·토큰·개인 설정은 프론트엔드나 Git에 넣지 않습니다.
- `/api/health` 성공과 최근 서비스 결과는 현재 모든 외부 서비스의 정상 동작을 보장하지 않습니다.
- Python 코드 변경 후에는 API를 재시작합니다.

요청·응답 형식, WebSocket 이벤트, 오류·종료 처리, 내부 구현과 검증 방법은
[백엔드 API 상세 문서](../docs/backend-api.md)에 보존되어 있습니다.
