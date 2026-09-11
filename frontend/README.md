# AI Waifu — React 화면 미리보기

Issue #7의 3단계. 단일 사용자·단일 창용 React + TypeScript + Vite 화면이다.
현재 응답·자막·진행 단계는 고정된 모의 데이터다. **Python API, Ollama,
Gemini, SBV2, VTS에 연결하거나 실제 음성을 재생하지 않는다.**
이 단계에서는 해당 서버들과 VTube Studio를 실행할 필요가 없다.

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

## 화면과 모의 동작

- 대화 기록, 현재 한국어 자막, 일본어 원문 펼치기.
- 한국어 입력·전송 버튼, Enter 전송·Shift+Enter 줄바꿈, 2000자 제한.
- 한글 조합 중 Enter와 keyCode 229 전송 방지.
- 처리 중 입력 잠금과 즉시 중복 전송 차단, 완료 후 입력 포커스 복귀.
- 입력 번역 → 응답 생성 → 자막 번역 → 합성 → 말하는 중 상태 예시.
- Ollama·Gemini·SBV2·VTS는 실제 연결을 조회하지 않았으므로 계속 **미연결** 표시.
- 비활성 마이크 버튼. 녹음/마이크 권한을 요청하지 않는다.
- 대화 종료는 진행 중 예시 답변을 마친 뒤 적용한다. 기록은 창에 남고,
  `새 미리보기 시작`을 누르면 새 빈 화면으로 돌아간다.
- `미리보기 설정`에서 정상·음성 합성 오류·캐릭터 연결 오류를 선택할 수 있다.
  이 설정은 다음 전송에만 적용한다. 오류가 나도 다음 입력을 받을 수 있다.
- 좁은 화면에서는 연결 상태를 상단에 모으고 입력·대화는 한 열로 표시한다.
  스크롤로 과거 대화를 읽고 있다면 새 응답이 강제로 맨 아래로 이동시키지 않는다.

미리보기 응답은 입력 내용과 무관하게 같은 문장이며 실제 AI 품질 검수가 아니다.
물결 애니메이션도 음량 측정이나 실제 립싱크가 아닌 말하는 상태의 예시다.
새로고침/탭 종료 시 기록은 사라진다. 영구 기억이나 재접속 복원을 구현하지 않았다.

## 파일 역할

| 파일 | 역할 |
| --- | --- |
| `src/App.tsx` | 화면, 입력 이벤트, 한글 조합 보호, 포커스·스크롤 |
| `src/useConversationPreview.ts` | 한 턴 상태·중복 방지·종료 대기·메시지 |
| `src/mockConversation.ts` | 정해진 모의 이벤트와 해제 가능한 타이머 |
| `src/Icons.tsx`, `src/styles.css` | 로컬 SVG·반응형 화면·동작 감소 설정 |
| `src/App.test.tsx` | 입력·상태·실패·종료·정보 저장 방지 테스트 |
| `vite.config.ts` | loopback 실행·루트 파일 접근 제한·화면 테스트 설정 |

4단계에서는 이 모의 이벤트 경계를 HTTP/WebSocket 연결로 교체한다.
Python의 AI·번역·TTS·VTS 로직을 TypeScript로 다시 작성하지 않는다.
다중 세션, client_request_id, 즉시 취소, CLI/API 동시 실행 잠금, Tauri는 후속 범위다.

## 정보 보호와 검수 범위

API 키·토큰·개인 TTS 설정을 이 폴더로 복사하거나 `VITE_` 환경변수에 넣지 않는다.
키 입력 UI도 없으며 대화문을 console, 파일, localStorage/sessionStorage에 기록하지 않는다.
화면에 표시할 입력과 모의 답변만 React 메모리에 보관한다.
Vite 개발 서버의 HMR WebSocket은 화면 갱신용이며 Python API 연결이 아니다.

컴포넌트 자동 테스트는 합성 IME 이벤트를 사용한다. 실제 macOS/Windows 한글
입력기 동작과 화면 잘림은 브라우저 수동 검수로 구분해서 확인해야 한다.

수동 검수 순서:

1. 첫 화면에서 미리보기·서비스 미연결·자막·입력창·비활성 마이크가 보이는지 확인.
2. 한국어 문장을 입력하고 조합 확정 Enter가 전송으로 오인되지 않는지 확인.
   조합 종료 후 Enter로 한 번 전송하고 Shift+Enter 줄바꿈도 확인.
3. 진행 상태·예시 자막·입력 복귀, 일본어 원문 펼치기를 확인.
4. 미리보기 설정의 두 오류 사례와 오류 후 다음 입력을 확인.
5. 처리 중 대화 종료가 현재 예시 답변을 기다리는지, 좁은 창에서도 입력창이 보이는지 확인.

참고: [Vite 시작 안내](https://vite.dev/guide/),
[React 입력·composition 이벤트](https://react.dev/reference/react-dom/components/common).
