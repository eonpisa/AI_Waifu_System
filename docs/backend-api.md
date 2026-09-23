# 로컬 API — Issue #7 2단계

단일 사용자·단일 실행 세션용 HTTP/WebSocket 인터페이스다. React 화면은
`frontend/`에서 HTTP/WebSocket으로 연결한다. `?preview=1`은 독립 모의 화면이다.
기존 `python main.py`도 유지한다. `backend.conversation.service.process_turn()`을
작업 스레드 하나에서 실행하므로 대화 처리 중에도 HTTP와 WebSocket이 응답한다.

## 실행

프로젝트 루트에서 기존 `.venv`를 사용한다. 현재 설치된 패키지로 검증했으며
이번 변경에서 패키지를 설치하거나 교체하지 않았다. API 의존성 목록은
루트의 `requirements-api.txt`이며 모델·음성 및 향후 프론트엔드 의존성과 분리한다.

```sh
cd /path/to/AI_Waifu_System
.venv/bin/python -B -m backend
```

기본 주소는 `http://127.0.0.1:8000`, API 문서는 `/docs`다. 공식 실행기는
프로젝트 루트를 작업 경로로 맞추며 **worker 1개, reload 끔**으로 실행한다.
`uvicorn`을 다른 옵션으로 직접 실행하는 방식은 이번 검수 기준이 아니다.
내부 ASGI 경로는 `backend.api.app:app`이다. HTTP/WebSocket 코드는 `api/`,
공통 대화는 `conversation/`, 번역은 `translation/`, 음성은 `voice/`,
감정·VTS는 `character/`에 있다. 패키지 import만으로 서비스를 시작하지 않는다.
기존 CLI와 API는 `output.wav`와 VTS를 공유하므로 **하나만 실행한다**.
프로세스 간 잠금은 후속 범위다. VTS·SBV2·Ollama는 별도로 실행한다.

Gemini 키가 현재 터미널 환경에 없으면 다음 명령으로 숨김 입력하고 API를
시작한다. 실제 키 값은 셸 명령이나 파일에 쓰지 않는다. 키는 이 Python
프로세스의 `GEMINI_API_KEY` 환경변수에만 설정한다.

```sh
.venv/bin/python -B -c 'import getpass, os; os.environ["GEMINI_API_KEY"] = getpass.getpass("Gemini API 키(입력 숨김): ").strip(); from backend.__main__ import run_api; run_api()'
```

키가 없거나 Gemini가 실패하면 기존 Qwen 폴백 정책을 사용한다. API 자체는
키·개인 설정을 받거나 조회하는 경로를 제공하지 않는다. SBV2 5001번,
Ollama 11434번, VTS 8001번의 기존 모듈·환경 설정을 그대로 사용한다.
`/api/health` 성공은 이 외부 서비스의 연결 성공을 뜻하지 않는다.

API 실행기의 콘솔은 번역기의 채택 provider·model·fallback_reason을 남기고,
기타 경고·오류의 상세 내용은 `service_warning`/`service_error`로 제한한다.
이는 기존 TTS 오류 응답·개인 경로 노출을 막기 위한 API 전용 정책이다.
CLI의 출력·로깅은 변경하지 않았다. HTTP 접근 로그와 디버그 상세 출력은 끈다.

## 최소 HTTP 명세

| 경로 | 요청 | 응답 |
| --- | --- | --- |
| `GET /api/health` | 없음 | `200 {"status":"ok","scope":"api_only"}` |
| `GET /api/state` | 없음 | busy, accepting, stage, turn_id, seq, last_result, services, subtitle_provider |
| `POST /api/turn` | JSON `{"text":"안녕. 짧게 답해 줘."}` | `202 {"turn_id":1,"status":"accepted"}` |
| `POST /api/end` | 없음 | 새 입력을 거절하도록 바꾼 현재 상태 |

`text`는 공백만 있는 문자열을 제외한 1~2000자 문자열이다. 다른 필드는 받지
않는다. 잘못된 입력은 원문을 반사하지 않는 `422 {"error":"invalid_input"}`이다.
실행 중 추가 입력은 `409 {"error":"busy"}`, 종료 요청 이후 입력은
`409 {"error":"session_ended"}`이다. 대기열은 없고 자동 재전송하지 않는다.

202는 **접수 성공**이다. 실제 완료는 WebSocket의 `turn_finished` 또는
`GET /api/state`에서 `busy=false`, `last_result`를 확인해야 한다.
결과 status는 `completed`, `partial_failure`, `failed`이고 `errors`에는
`input_translation_failed`, `japanese_reply_failed`, `subtitle_failed`,
`synthesis_failed`, `playback_failed`, `turn_failed` 등의 코드만 담긴다.
`audio_played=true`는 재생 함수의 성공이며 사용자의 청취 판정을 대신하지 않는다.

`POST /api/end`는 서버 프로세스를 끄거나 진행 중 음성을 즉시 취소하지 않는다.
현재 턴이 끝나면 `stage=ended`가 된다. 다시 대화하려면 API를 재시작한다.
CLI의 `종료`/`기록초기화` 문자열 명령은 HTTP 입력 명령으로 해석하지 않는다.

## WebSocket

`ws://127.0.0.1:8000/api/events`에 먼저 연결한 뒤 POST한다. 연결 시 현재
`state` 하나를 받고 이후 이벤트를 받는다. 이전 이벤트 재전송은 없다.

```json
{
  "type": "stage_changed",
  "turn_id": 1,
  "seq": 4,
  "elapsed_ms": 1250,
  "data": {"stage": "generating"}
}
```

단계는 `queued` → `translating_input` → `generating` →
`translating_subtitle` → `synthesizing` → `speaking` 순이다. 실패한 이후 단계는
생략될 수 있다. `speaking`은 로컬 재생 함수 호출 직전이며 실제 오디오 장치의
재생 시작 신호를 측정한 값은 아니다. elapsed_ms는 접수 이후 경과 시간이며
첫 응답 지연이나 순수 추론 시간으로 해석하지 않는다.

| type | data |
| --- | --- |
| `state` | HTTP 상태와 같은 필드 |
| `stage_changed` | stage |
| `input_translated` | source, normalized_source, japanese_input |
| `reply_ready` | emotion, japanese_reply |
| `subtitle_ready` | korean_subtitle (실패 시 null) |
| `service_status` | service (`ollama`/`gemini`/`sbv2`/`vts`), state, code |
| `subtitle_provider` | provider (`gemini`/`qwen`/`none`), model, fallback_reason |
| `notice` | code, 안전한 안내 message |
| `turn_finished` | result, stage (`idle` 또는 `ended`) |

result에는 status, japanese_reply, korean_subtitle, emotion, audio_played,
errors만 포함한다. 시스템 프롬프트, 내부 messages, 설정, 키, 토큰, 요청 헤더,
외부 서비스 응답 원문은 전송하지 않는다. 화면에 필요한 대화문·자막만 전달한다.
상태 조회는 마지막 결과 하나만 제공하며 대화 저장·재접속 복원 기능은 아니다.
Gemini/Qwen 채택 정보는 기존 콘솔 로그와 위 이벤트로 확인한다.
`services`는 서비스별 마지막 요청 결과와 해당 `turn_id`를 보관한다. 호출 전은
`unknown`이며, `ok`는 그 요청의 응답 확인이다. 현재 연결이 계속 유지됨을
보장하는 헬스 체크가 아니며 추가 모델/API 호출을 하지 않는다. Ollama 응답 수신은
내용 검증 성공과 별개이고, SBV2 합성 성공은 청취 판정을 뜻하지 않는다.
VTS는 인증 후 첫 파라미터 적용 응답에서 성공을 알리고, 인증/연결 오류와
립싱크 모델 미보정·입 닫기 실패를 구분한다. 상태 알림 실패는 대화를 중단하지 않는다.

`subtitle_provider`는 채택된 번역기만 나타내며 두 번역기 모두 실패하면 `none`이다.
다음 턴 접수 시 이전 번역기 정보는 비운다. 초기 WS state와 HTTP state에서
최근 상태를 확인할 수 있지만 과거 대화 기록을 복원하지는 않는다. 공개 정보는
고정 코드와 Gemini/Qwen 모델 식별자로 제한하고 사용자 지정 경로/식별자는
`custom`으로 표시한다. 응답 원문·키·토큰·헤더·개인 설정은 포함하지 않는다.
API에서만 요청별 관찰자를 등록하며 CLI의 출력·반환값·처리 순서는 유지한다.

브라우저 Origin은 localhost/127.0.0.1의 8000·5173번 HTTP 출처만 허용한다.
Host도 localhost/127.0.0.1로 제한한다. Origin 없는 로컬 CLI 클라이언트는
사용할 수 있다. 이는 로컬 개발용 경계이며 사용자 인증이나 원격 공개용 서버가 아니다.

## 연결 해제·종료

- WebSocket이 끊겨도 현재 턴의 음성과 VTS는 정상 마무리한다. API의 다음 입력은
  이전 worker가 끝난 뒤에만 받는다.
- 구독자는 최대 4개, 연결별 대기 이벤트는 최대 64개다. 느린 구독자는 닫고
  음성 처리를 계속한다. 느린 구독/구독 한도 초과의 닫힘 코드는 1013이다.
- Ctrl+C 한 번은 진행 중 턴을 기다린 뒤 executor를 정리한다. 기존 네트워크
  요청의 타임아웃과 음성 길이만큼 기다릴 수 있다. 강제 종료까지 정상 복구를
  보장하는 즉시 취소 기능은 이번 범위가 아니다.
- 음성·VTS·립싱크는 브라우저가 아닌 **Python을 실행한 컴퓨터에서** 작동한다.
  브라우저로 WAV를 스트리밍하거나 VTS를 직접 제어하지 않는다.

현재 macOS 대화 경로는 내장 스피커 청취 검수에 맞춰 립싱크 음량 시계만
0.7초 늦춘다(`backend/conversation/service.py`의 `MACOS_LIP_SYNC_DELAY_SECONDS`).
음성 재생 자체나 표정 종료 신호는 지연하지 않는다. 출력 장치가 바뀌면 재검수가
필요하며 Windows/Linux와 VTS 단독 표정 검수에는 이 보정을 적용하지 않는다.
Python 코드 변경 후에는 API를 재시작해야 한다(자동 reload 없음).

## 검증

```sh
.venv/bin/python -B -m unittest discover -s tests -v
```

API 테스트는 기존 환경의 httpx 0.28.1/TestClient를 사용하고 실제 모델이나
오디오를 호출하지 않는다. import 부작용 방지, 공통 한 턴 호출, 중복 거절,
진행 중 상태 응답, WS 해제, 오류 복구, 종료 대기, 정보 노출 제한을 검증한다.
실제 Gemini·SBV2·VTS 한 턴 검수는 별도로 진행하고 청취·입 움직임은 사용자가
확인한다. React 실제 환경 검수, 재접속 복원, 즉시 취소, 다중 세션, Tauri는 후속 작업이다.
## 선택형 음성 입력

브라우저에서 녹음한 음성은 `POST /api/transcribe`로 로컬 Python에 전달한다.
인식 결과는 입력창의 초안이며, 사용자가 전송하기 전에는 대화 기록이나 LLM에 넣지 않는다.

- 요청: WAV/WebM/MP4/Ogg 오디오 본문. `Content-Type`은 `audio/wav`, `audio/webm`,
  `audio/mp4`, `audio/ogg` 중 하나이며 multipart 업로드가 아니다.
- 성공: `200 {"text": "한국어 전사문"}`. 응답은 `Cache-Control: no-store`.
- 실패: `409` 처리 중/세션 종료, `413` 용량 초과, `415` 형식 미지원,
  `422` 모델 미설정·누락, 무음, 전사 실패 등 고정 오류 코드.
- 최대 업로드 20MiB, 업로드 대기 15초, 디코딩한 음성 최대 30초.
  화면 녹음은 20초에서 자동 종료한다.
- 전사 중 HTTP와 WS 상태는 `busy=true`, `stage=transcribing_audio`이다.
  기존 단일 작업자를 공유하므로 대화·다른 전사 요청은 겹치지 않는다.
- 녹음 파일은 시스템 임시 폴더에서 처리한 뒤 삭제한다. HTTP 연결이 끊어져도
  진행 중인 로컬 추론이 끝나야 파일과 예약을 해제한다. 즉시 추론 취소는 제공하지 않는다.
- 음성·전사문·모델 경로를 로그에 기록하지 않는다. 모델 경로는 HTTP/WS에 보내지 않는다.

STT 의존성은 기본 의존성과 별개인 루트 `requirements-stt.txt`에 있다.
이미 설치된 환경은 재설치할 필요가 없다. CTranslate2 형식의 다국어 Whisper 모델을
로컬에 준비하고, API를 실행하는 터미널에서 경로를 지정한다.

```sh
export AI_WAIFU_STT_MODEL="$PWD/local_checks/stt_models/faster-whisper-base"
.venv/bin/python -B -m backend
```

위 경로는 Git에서 제외되는 로컬 준비 위치의 예다. 모델 파일은 저장소에 포함하지 않으며
위 실행 명령이 모델을 다운로드하지 않는다. Gemini를 사용하는 대화 검수에서는
기존 키 숨김 입력 실행 절차에도 같은 환경변수를 적용한다.
CPU int8 전사로 시작하며 실제 마이크 정확도·속도와 Windows 동작은 별도 검수한다.
