# AI Waifu — React 대화 화면

Issue #7의 4단계: 기본 화면에서 단일 세션 Python API에 연결한다.
한국어 입력은 HTTP로 보내고 일본어 답변·한국어 자막·진행 상태는 WebSocket으로 받는다.
AI·번역·SBV2 합성·재생·VTS·립싱크는 기존 Python 코드가 실행한다.
브라우저는 WAV를 재생하거나 마이크 권한을 요청하지 않는다.

기존 실제 웹 4턴의 문맥·Gemini 자막·음성·립싱크는 사용자 검수를 통과했다.
새 서비스 상태·번역기 표시는 자동 검증을 완료했으며, API 재시작 후 화면 검수가 남아 있다.
연결 상태 영역은 서비스별 **최근 요청 결과**를 표시한다. 아직 호출하지 않은 서비스는
미확인으로 두며, API 연결 성공만으로 외부 서비스도 정상이라고 표시하지 않는다.
자막 아래에서 Gemini/Qwen 채택·모델·폴백 사유를 확인할 수 있다.

## 실행

검증 환경은 Node **24.18.0**, npm **11.16.0**이다. 화면 테스트의 jsdom까지
포함한 Node 조건은 `^24.15.0 || >=26.0.0`이며 `package.json`에 명시했다.
Windows에서도 Node 24의 같은 조건을 충족하는 버전을 사용한다.
Windows에서의 실제 UI/IME 검수는 아직 수행하지 않았다.

```sh
cd frontend
npm ci
npm run dev
```

이미 의존성이 설치돼 있다면 `npm run dev`만 실행한다.
브라우저 주소는 **http://127.0.0.1:5173/** 이다.
다른 프로세스가 5173번을 사용하면 포트를 임의로 바꾸지 않고 실행에 실패한다.
서버는 loopback에만 바인딩하고 `frontend/` 밖의 파일은 제공하지 않는다.
Python 의존성이나 루트 `.venv`를 설치/변경하는 명령은 포함하지 않는다.

```sh
npm test
npm run build
npm run preview
```

preview도 5173번을 쓰므로 dev를 Ctrl+C로 종료한 뒤 실행한다.
의존성은 정확한 버전 및 `package-lock.json`으로 기록한다.
`node_modules/`, `dist/`, 테스트 산출물은 Git에서 제외한다.
외부 폰트·이미지·CDN이나 UI 컴포넌트 라이브러리는 사용하지 않는다.

## 실제 대화 실행 순서

1. 기존 Ollama, SBV2(5001), VTS(8001)를 별도로 실행한다. CLI는 종료한다.
2. 프로젝트 루트의 터미널에서 키를 숨김 입력하고 API를 실행한다.

   ```sh
   .venv/bin/python -B -c 'import getpass, os; os.environ["GEMINI_API_KEY"] = getpass.getpass("Gemini API 키(입력 숨김): ").strip(); from backend.__main__ import run_api; run_api()'
   ```

   기존 개인 TTS 설정의 SBV2 5001, CosyVoice fallback 비활성화를 유지한다.
3. 다른 터미널에서 `cd frontend` → `npm run dev` 후
   http://127.0.0.1:5173/ 에 접속한다.
4. 대화 서버가 연결되면 한국어를 입력한다. 첫 WebSocket state 수신 전에는
   전송할 수 없다. 입력은 2000자 이내이며 Enter 전송, Shift+Enter 줄바꿈,
   한국어 조합 중 Enter 전송 방지를 유지한다.
5. 진행 단계, 일본어 원문 펼치기, 한국어 자막, 입력 복귀를 확인한다.
   처리 시간은 서버 접수부터 로컬 재생 종료까지이며 청취 성공을 대신하지 않는다.

### 연결·종료 동작

- 고정 주소: HTTP `http://127.0.0.1:8000`, WS `ws://127.0.0.1:8000/api/events`.
  Vite와 API 모두 loopback만 사용한다. 주소 변경 UI나 키 입력 UI는 없다.
- 전송 즉시 잠그고 `202`는 접수로만 해석한다. `turn_finished` 이후 다시 입력한다.
  완료 이벤트가 HTTP 응답보다 먼저 와도 중복 답변이나 영구 잠금을 만들지 않는다.
- `409`/`422` 거절은 안전한 안내를 표시하고 현재 서버 상태를 다시 조회한다.
  접수 거절된 입력은 화면 기록에 남지만 자동으로 다시 보내지 않는다.
- 통신 실패·10초 초기 연결/HTTP 응답 시간 초과는 입력을 막고 새로고침을 안내한다.
  요청 접수 여부를 알 수 없는 경우 자동 재전송하지 않는다.
  이 10초는 모델 응답 시간 제한이 아니다. 진행 중인 모델·음성은 기존 서버 제한을 따른다.
- 자막·TTS 실패는 안내와 결과를 표시하며 서버가 idle이면 다음 입력을 허용한다.
  VTS 실패는 기존 Python 정책대로 음성을 중단하지 않는다. 서비스 상태는 실제 요청
  결과 이벤트로 갱신하며, 다음 성공 요청이 이전 실패 표시를 갱신한다. 정기적인
  연결 점검은 하지 않으므로 표시된 턴 이후 서버가 계속 실행 중임을 보장하지 않는다.
  API 연결이 끊기면 이전 결과로 표시한다. 인증·연결 실패와 VTS 제어 응답,
  립싱크 모델 미보정·입 닫기 응답 실패를 구분한다.
  자막 채택 정보는 다음 전송 때 비우며 Gemini 실패 시 Qwen 대체 채택과 이유를
  표시한다. 두 번역기가 모두 실패하면 자막 번역 실패로 표시한다.
- 대화 종료는 `/api/end`로 현재 음성이 끝나기를 기다린다. 즉시 취소하지 않는다.
  새 대화는 API를 재시작한 뒤 화면을 새로고침한다.
- 탭 종료/연결 끊김 때 브라우저 WS·요청·타이머는 정리하지만 `/api/end`를 보내지 않는다.
  서버의 음성과 VTS는 기존 finally 처리까지 계속된다.
- 화면 기록은 React 메모리만 사용한다. 새로고침은 서버 세션을 초기화하지 않는다.
  초기 state는 서버 잠금·최근 서비스 결과·번역기 정보를 동기화하며 과거 대화 기록은 복원하지 않는다.

## 독립 화면 미리보기

http://127.0.0.1:5173/?preview=1 에서는 기존 3단계 고정 모의 응답을 사용한다.
API·Ollama·Gemini·SBV2·VTS는 필요 없다. 미리보기 설정에서 정상·합성 오류·캐릭터
연결 오류를 선택할 수 있다. 실제 음성을 재생하지 않으며 모든 서비스는 미연결이다.
`새 미리보기 시작`은 모의 화면에만 있고 실제 API 세션을 초기화하지 않는다.

## 파일 역할

| 파일 | 역할 |
| --- | --- |
| `src/App.tsx` | 화면, 입력 이벤트, 한글 조합 보호, 포커스·스크롤 |
| `src/conversationClient.ts` | HTTP/WS·접수 잠금·이벤트 순서·연결 정리 |
| `src/serviceStatus.ts` | 서비스 결과·번역기 정보의 허용 필드 검사와 표시 문구 |
| `src/useConversation.ts` | React 구독과 연결 생명주기 |
| `src/useConversationPreview.ts` | 한 턴 상태·중복 방지·종료 대기·메시지 |
| `src/mockConversation.ts` | 정해진 모의 이벤트와 해제 가능한 타이머 |
| `src/Icons.tsx`, `src/styles.css` | 로컬 SVG·반응형 화면·동작 감소 설정 |
| `src/App.test.tsx`, `src/LiveApp.test.tsx`, `src/conversationClient.test.ts` | 모의 화면·실제 화면 연결·전송 경합·실패·종료·정보 비노출 테스트 |
| `vite.config.ts` | loopback 실행·루트 파일 접근 제한·화면 테스트 설정 |

실제 연결과 미리보기는 화면 컴포넌트를 공유하고 서로 다른 대화 상태 모듈을 사용한다.
Python의 AI·번역·TTS·VTS 로직을 TypeScript로 다시 작성하지 않는다.
다중 세션, client_request_id, 즉시 취소, CLI/API 동시 실행 잠금, Tauri는 후속 범위다.

## 정보 보호와 검수 범위

API 키·토큰·개인 TTS 설정을 이 폴더로 복사하거나 `VITE_` 환경변수에 넣지 않는다.
키 입력 UI도 없으며 대화문을 console, 파일, localStorage/sessionStorage에 기록하지 않는다.
화면에 표시할 입력과 답변만 React 메모리에 보관한다. Python은 기존 정책에 따라
자막 번역에 Gemini를 사용할 수 있다.
Vite HMR WebSocket과 Python 대화 WebSocket은 별개다.

컴포넌트 자동 테스트는 합성 IME 이벤트를 사용한다. 실제 macOS/Windows 한글
입력기 동작과 화면 잘림은 브라우저 수동 검수로 구분해서 확인해야 한다.

자동 검증: 프론트엔드 35개 테스트·타입 검사·빌드 통과. 최근 상태 표시 변경은
별도 FastAPI와 현재 TS 클라이언트의 실제 HTTP/WS로 정상→폴백→복구,
HTTP/WS 상태 일치와 새 연결의 상태 수신을 확인했다. 모델·음성·VTS 전송은
대역이며 실제 청취나 브라우저 배치 검수가 아니다. 기존 CORS·접수 경합·종료와
IME 자동 검증도 유지한다.

실제 환경 검수:

1. 한글 조합/Enter와 Shift+Enter, 실제 전송 1회, 처리 중 중복 방지를 확인한다.
2. 일본어 응답, Gemini 지정 모델·fallback_reason=none 로그, 한국어 자막을 확인한다.
3. SBV2 음성·VTS 표정·입 움직임과 음성 종료 후 입 닫힘·입력 복귀를 확인한다.
4. 서버 종료/연결 끊김 시 입력이 잠기고 자동 재전송하지 않는지 확인한다.
   실제 API 화면에서는 오류를 주입하는 UI를 제공하지 않는다.

참고: [Vite 시작 안내](https://vite.dev/guide/),
[React 입력·composition 이벤트](https://react.dev/reference/react-dom/components/common).
