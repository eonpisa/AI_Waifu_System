import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, FormEvent, KeyboardEvent, PointerEvent } from 'react'
import { Icon } from './Icons'
import { stageLabels } from './mockConversation'
import type { Scenario } from './mockConversation'
import { useConversationPreview } from './useConversationPreview'
import { useConversation } from './useConversation'
import { fallbackLabel, observationDetail, observationLabel, unknownServices } from './serviceStatus'
import type { Services, SubtitleProvider } from './serviceStatus'
import { useMicrophone } from './useMicrophone'

const services = [
  ['ollama', 'Ollama', '대화와 입력 번역'], ['gemini', 'Gemini', '한국어 자막'],
  ['sbv2', 'SBV2', '일본어 음성'], ['vts', 'VTube Studio', '표정과 입 움직임'],
] as const
const suggestions = ['오늘 학교에서 시험을 봤어.', '오늘은 기분이 정말 좋아!', '내일은 친구와 산책할 거야.']
const progressText: Record<string, string> = {
  queued: '답변을 준비하고 있어요', translating_input: '입력을 살펴보고 있어요',
  generating: '답변을 생각하고 있어요', translating_subtitle: '한국어 자막을 준비하고 있어요',
  synthesizing: '음성을 준비하고 있어요', speaking: '이야기하고 있어요',
  transcribing_audio: '음성을 인식하고 있어요',
}

export default function App({ preview = false }: { preview?: boolean }) {
  return preview ? <PreviewApp /> : <LiveApp />
}
function PreviewApp() {
  const chat = useConversationPreview()
  return <ConversationScreen chat={{ ...chat, connected: true, accepting: true, elapsedMs: null, audioPlayed: null, services: unknownServices(), subtitleProvider: null }} preview />
}
function LiveApp() {
  const chat = useConversation()
  return <ConversationScreen chat={chat} />
}
type Chat = Omit<ReturnType<typeof useConversationPreview>, 'restart'> & {
  connected: boolean; accepting: boolean; elapsedMs: number | null; audioPlayed: boolean | null; restart?: () => void
  services: Services; subtitleProvider: SubtitleProvider | null
}
function ProviderInfo({ provider, connected }: { provider: SubtitleProvider; connected: boolean }) {
  return <div className="subtitle-provider" aria-label="자막 번역 정보">
    <span>{provider.turn_id}턴 · {provider.provider === 'gemini' ? 'Gemini 자막 채택' : provider.provider === 'qwen' ? 'Qwen 대체 자막 채택' : '자막 번역 실패'}{!connected && ' · 이전 결과'}</span>
    <span>모델: {provider.model === 'custom' ? '사용자 지정' : provider.model}</span>
    <span>{fallbackLabel(provider.fallback_reason)}</span>
    {provider.fallback_reason !== 'none' && <span className="fallback-code">{provider.fallback_reason}</span>}
  </div>
}
function ConversationScreen({ chat, preview = false }: { chat: Chat; preview?: boolean }) {
  const [draft, setDraft] = useState('')
  const [scenario, setScenario] = useState<Scenario>('normal')
  const [menuOpen, setMenuOpen] = useState(() =>
    typeof window.matchMedia !== 'function' || !window.matchMedia('(max-width: 820px)').matches)
  const [showLatest, setShowLatest] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(400)
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth)
  const [resizingSidebar, setResizingSidebar] = useState(false)
  const sidebarDrag = useRef<{ pointerId: number; startX: number; startWidth: number } | null>(null)
  const sidebarMax = Math.min(880, viewportWidth <= 820 ? Math.floor(viewportWidth * .9) : viewportWidth - 480)
  const sidebarMin = Math.min(400, sidebarMax)
  const visibleSidebarWidth = Math.max(sidebarMin, Math.min(sidebarMax, sidebarWidth))
  const composing = useRef(false)
  const menuButton = useRef<HTMLButtonElement>(null)
  const menuCloseButton = useRef<HTMLButtonElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const history = useRef<HTMLDivElement>(null)
  const nearBottom = useRef(true)
  const wasBusy = useRef(false)
  const ended = chat.stage === 'ended'
  const mic = useMicrophone(!preview && chat.connected && chat.accepting && !ended, chat.busy, text => {
    setDraft(text)
    input.current?.focus()
  })
  const inputDisabled = chat.busy || mic.busy || ended || !chat.connected || !chat.accepting
  const latestAssistant = [...chat.messages].reverse().find(message => message.role === 'assistant')?.id
  const providerInMessage = chat.messages.at(-1)?.role === 'assistant'

  useEffect(() => {
    const mobile = window.matchMedia?.('(max-width: 820px)')
    if (!mobile) return
    const syncMenu = () => setMenuOpen(!mobile.matches)
    mobile.addEventListener('change', syncMenu)
    return () => mobile.removeEventListener('change', syncMenu)
  }, [])

  useEffect(() => {
    const updateViewport = () => { stopSidebarResize(); setViewportWidth(window.innerWidth) }
    window.addEventListener('resize', updateViewport)
    return () => window.removeEventListener('resize', updateViewport)
  }, [])

  function resizeSidebar(width: number) {
    setSidebarWidth(Math.max(sidebarMin, Math.min(sidebarMax, width)))
  }

  function startSidebarResize(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return
    event.preventDefault()
    event.currentTarget.focus()
    event.currentTarget.setPointerCapture?.(event.pointerId)
    sidebarDrag.current = { pointerId: event.pointerId, startX: event.clientX, startWidth: visibleSidebarWidth }
    setResizingSidebar(true)
  }

  function stopSidebarResize() {
    sidebarDrag.current = null
    setResizingSidebar(false)
  }

  useEffect(() => {
    if (menuOpen && window.matchMedia?.('(max-width: 820px)').matches) menuCloseButton.current?.focus()
  }, [menuOpen])

  function closeMenu() {
    stopSidebarResize()
    setMenuOpen(false)
    menuButton.current?.focus()
  }

  useEffect(() => {
    if (wasBusy.current && !chat.busy && !ended) input.current?.focus()
    wasBusy.current = chat.busy
  }, [chat.busy, ended])
  useEffect(() => {
    if (!history.current) return
    if (nearBottom.current) {
      history.current.scrollTop = history.current.scrollHeight
      setShowLatest(false)
    } else if (chat.messages.length) setShowLatest(true)
  }, [chat.messages])
  useEffect(() => {
    if (!ended || !history.current) return
    if (nearBottom.current) {
      history.current.scrollTop = history.current.scrollHeight
      setShowLatest(false)
    } else setShowLatest(true)
  }, [ended])

  function scrollLatest() {
    if (history.current) history.current.scrollTop = history.current.scrollHeight
    nearBottom.current = true
    setShowLatest(false)
  }

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (composing.current || mic.busy) return
    if (chat.send(draft, scenario)) { setDraft(''); scrollLatest() }
  }
  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey) return
    // keyCode 229 covers IME Enter behavior in browsers where isComposing is false.
    if (composing.current || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return
    event.preventDefault()
    submit()
  }

  return <div className={`app-shell ${menuOpen ? 'menu-open' : 'menu-closed'} ${resizingSidebar ? 'sidebar-resizing' : ''}`} style={{ '--sidebar-width': `${visibleSidebarWidth}px` } as CSSProperties}>
    {menuOpen && <button className="sidebar-scrim" aria-label="메뉴 닫기" onClick={closeMenu} />}
    <aside id="conversation-sidebar" className="sidebar" aria-label="대화 및 연결 상태" inert={!menuOpen} onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); closeMenu() } }}>
      <div className="sidebar-header"><div className="brand"><span className="brand-mark">AI</span><span>AI Waifu<span className="brand-sub">편하게 이야기하는 공간</span></span></div>
        <button ref={menuCloseButton} className="menu-button" aria-label="사이드바 닫기" title="사이드바 닫기" onClick={closeMenu}><Icon name="close" /></button></div>
      <div className="sidebar-section"><span className="sidebar-label">지금의 대화</span><div className="nav-current"><Icon name="chat" /><span>대화</span><span className="nav-dot" /></div>
        <p className="session-note">{preview ? '새로고침하면 예시 기록이 사라져요.' : '화면 기록은 이 창에만 남아요. 서버 문맥은 재시작 전까지 유지돼요.'}</p></div>
      <details className="connections">
        <summary><span>연결 상태</span><span className="connection-summary">{preview ? '미리보기' : '최근 요청'} <Icon name="chevron" /></span></summary>
        <p className="muted small">{preview ? '실제 서비스는 연결하지 않아요.' : `대화 서버: ${chat.connected ? '연결됨' : '연결 확인 필요'}. 아래는 마지막 요청 결과이며 지금도 연결됐다는 뜻은 아니에요.`}</p>
        <ul>{services.map(([id, name, description]) => {
          const status = chat.services[id]
          const stale = !chat.connected && status.turn_id !== null
          const detail = `${status.turn_id ? `${status.turn_id}턴 · ` : ''}${observationDetail(id, status)}`
          return <li key={id} title={preview ? description : detail} aria-label={`${name}: ${preview ? '미연결' : stale ? '확인 불가 · 이전 결과' : observationLabel(id, status)}`}>
            <span className={`service-dot status-${preview || stale ? 'unknown' : status.state}`} />
            <div><strong>{name}</strong><span>{description}</span>{!preview && <span className="service-detail">{stale ? '이전 결과 · ' : ''}{detail}</span>}</div>
            <span className="service-state">{preview ? '미연결' : stale ? '확인 불가' : observationLabel(id, status)}</span>
          </li>
        })}</ul>
      </details>
      {preview && <details className="preview-settings">
        <summary>미리보기 설정 <Icon name="chevron" /></summary>
        <label htmlFor="scenario">다음 전송의 예시 동작</label>
        <select id="scenario" value={scenario} disabled={chat.busy || ended} onChange={event => setScenario(event.target.value as Scenario)}>
          <option value="normal">정상 흐름</option><option value="tts_error">음성 합성 오류</option><option value="vts_error">캐릭터 연결 오류</option>
        </select>
        <p>답변은 예시이며 음성은 재생하지 않아요.</p>
      </details>}
      <p className="sidebar-foot">내 컴퓨터에서 이어지는 대화</p>
    </aside>
    {menuOpen && <div className="sidebar-resizer" role="separator" aria-label="사이드바 너비 조절" aria-orientation="vertical" aria-controls="conversation-sidebar"
      aria-valuemin={sidebarMin} aria-valuemax={sidebarMax} aria-valuenow={visibleSidebarWidth} aria-valuetext={`${visibleSidebarWidth}px`} tabIndex={0}
      title="드래그 또는 좌우 방향키로 너비 조절" onPointerDown={startSidebarResize}
      onPointerMove={event => { const drag = sidebarDrag.current; if (drag && drag.pointerId === event.pointerId) resizeSidebar(drag.startWidth + event.clientX - drag.startX) }}
      onPointerUp={event => { stopSidebarResize(); if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId) }}
      onPointerCancel={stopSidebarResize} onLostPointerCapture={stopSidebarResize}
      onKeyDown={event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
        event.preventDefault()
        resizeSidebar(event.key === 'Home' ? sidebarMin : event.key === 'End' ? sidebarMax : visibleSidebarWidth + (event.key === 'ArrowRight' ? 10 : -10))
      }} />}

    <main className="main-panel">
      <header className="topbar">
        <button ref={menuButton} className="menu-button" aria-label={menuOpen ? '메뉴 접기' : '메뉴 열기'} title={menuOpen ? '메뉴 접기' : '메뉴 열기'} aria-controls="conversation-sidebar" aria-expanded={menuOpen} onClick={() => menuOpen ? closeMenu() : setMenuOpen(true)}><Icon name="sidebar" /></button>
        <span className={`character-avatar ${chat.stage === 'speaking' ? 'is-speaking' : ''}`} aria-hidden="true">AI</span>
        <div className="character-heading"><h1>AI 친구</h1><span className={`stage-badge ${chat.busy ? 'is-busy' : ''}`} role="status">{chat.busy && <span className="pulse-dot" />}{!preview && !chat.connected ? '서버 연결 확인 필요' : stageLabels[chat.stage]}{chat.busy && preview && ' · 예시'}</span></div>
        <button className="end-button" onClick={() => { mic.cancel(); chat.end() }} disabled={ended || chat.ending || !chat.connected || !chat.accepting}><Icon name="stop" />{chat.ending ? '답변 후 종료' : ended ? '종료됨' : '대화 종료'}</button>
      </header>
      <div className="mode-note"><Icon name="info" /><span><strong>{preview ? '화면 미리보기' : '로컬 대화'}</strong>{preview ? ' · 실제 서비스와 연결하지 않아요.' : ' · 음성과 캐릭터는 Python을 실행한 컴퓨터에서 작동해요.'}</span></div>

      <section className="conversation-panel" aria-label="대화 공간">
        <div className="history-wrap"><div className="history" ref={history} onScroll={() => { const el = history.current; if (el) { nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; setShowLatest(!nearBottom.current) } }}>
          {chat.messages.length === 0 && !ended ? <div className="welcome">
            <div className="welcome-avatar" aria-hidden="true">AI</div>
            <span className="welcome-caption">작은 이야기부터 천천히</span>
            <h2>오늘은 어떤 하루였나요?</h2>
            <p>기뻤던 일도, 조금 지쳤던 순간도.<br />마음에 남은 이야기를 들려주세요.</p>
            <div className="suggestions" aria-label="시작 문장 예시">{suggestions.map((text, index) => <button key={text} disabled={mic.busy} onClick={() => { setDraft(text); input.current?.focus() }}><span>{['오늘 있었던 일', '기분 좋은 소식', '내일의 작은 계획'][index]}</span><Icon name="arrow" /></button>)}</div>
          </div> : null}
          <div className="messages" role="log" aria-label="대화 기록" aria-live="polite" aria-relevant="additions text">
            {chat.messages.map(message => <article key={message.id} className={`message ${message.role}`}>
              {message.role === 'assistant' && <span className={`message-avatar ${chat.stage === 'speaking' && message.id === latestAssistant ? 'is-speaking' : ''}`} aria-hidden="true">AI</span>}
              <div className="message-content"><div className="message-name">{message.role === 'user' ? '나' : 'AI 친구'}{message.role === 'assistant' && preview && <span>예시 답변</span>}</div>
                <div className="message-bubble">{message.text || <span className="muted">한국어 자막을 준비하고 있어요…</span>}</div>
                {message.japanese && <details className="japanese"><summary>원문 보기 <Icon name="chevron" /></summary><p lang="ja">{message.japanese}</p></details>}
                {message.role === 'assistant' && message.id === latestAssistant && providerInMessage && !preview && chat.subtitleProvider && <ProviderInfo provider={chat.subtitleProvider} connected={chat.connected} />}
              </div>
            </article>)}
            {chat.busy && chat.messages.at(-1)?.role === 'user' && <div className="thinking" aria-label={progressText[chat.stage] || '답변 준비 중'}><span className="message-avatar" aria-hidden="true">AI</span><span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span><span>{progressText[chat.stage] || '답변 준비 중'}</span></div>}
          </div>
          {ended && <div className="ended-note"><Icon name="spark" /><h2>잠시 쉬어 가도 괜찮아요.</h2><p>이 대화는 여기까지예요. 기록은 이 창에 남아 있어요.</p>{preview ? <button className="text-button" onClick={() => { chat.restart?.(); setDraft(''); setTimeout(() => input.current?.focus(), 0) }}>새 미리보기 시작 <Icon name="arrow" /></button> : <p>새 대화는 API 서버를 재시작한 뒤 화면을 새로고침해 주세요.</p>}</div>}
        </div>{showLatest && <button className="latest-button" onClick={scrollLatest}>최신 메시지 ↓</button>}</div>

        <div className="bottom-panel">
          {chat.warning && <div className="warning" role="alert"><Icon name="info" /><p>{chat.warning}</p><button aria-label="오류 안내 닫기" onClick={chat.dismissWarning}><Icon name="close" /></button></div>}
          {chat.ending && <p className="ending-notice" role="status">{preview ? '진행 중인 예시 답변이 끝나면 대화를 종료해요.' : '현재 음성 재생을 마친 뒤 대화를 종료해요.'}</p>}
          {!preview && chat.subtitleProvider && !providerInMessage && <ProviderInfo provider={chat.subtitleProvider} connected={chat.connected} />}
          <form className={`composer ${inputDisabled ? 'composer-disabled' : ''}`} onSubmit={submit}>
            <label className="sr-only" htmlFor="message-input">한국어 메시지</label>
            <textarea id="message-input" ref={input} value={draft} disabled={inputDisabled} maxLength={2000} rows={2} placeholder={ended ? '종료된 대화예요.' : chat.busy ? '답변을 준비하고 있어요…' : '편하게 이야기해 주세요…'} onChange={event => setDraft(event.target.value)} onCompositionStart={() => { composing.current = true }} onCompositionEnd={() => { composing.current = false }} onKeyDown={keyDown} aria-describedby="input-help" />
            <div className="composer-toolbar"><span className="mic-group"><button type="button" className="mic-button"
              disabled={preview || (mic.phase !== 'recording' && (inputDisabled || !!draft.trim()))}
              onClick={() => mic.phase === 'recording' ? mic.stop() : void mic.start()}
              aria-label={preview ? '음성 입력 — 준비 중' : mic.phase === 'recording' ? '녹음 종료' : '음성 입력 시작'}
              title="최대 20초 녹음 후 내용을 확인하고 전송합니다. 입력창이 비어 있을 때 시작할 수 있습니다."><Icon name={mic.phase === 'recording' ? 'stop' : 'mic'} /></button>
              <span>{preview ? '음성 입력 준비 중' : mic.phase === 'recording' ? '녹음 중 · 최대 20초' : mic.phase === 'transcribing' ? '음성 인식 중' : mic.phase === 'permission' ? '마이크 허용 대기' : '음성 입력'}</span>
              {mic.busy && <button type="button" className="text-button" onClick={mic.cancel}>녹음 취소</button>}
              </span><span className="composer-actions"><span className="character-count">{draft.length.toLocaleString()} / 2,000</span><button type="submit" className="send-button" disabled={inputDisabled || !draft.trim()}><span>전송</span><Icon name="arrow" /></button></span></div>
          </form>
          {!preview && mic.notice && <p className="muted small" role="status">{mic.notice}</p>}
          {!preview && chat.elapsedMs !== null && <p className="muted small">처리 시간 {(chat.elapsedMs / 1000).toFixed(2)}초 · 서버 접수부터 재생 종료까지 · 재생 함수 {chat.audioPlayed ? '성공' : '미완료'}</p>}
          <div className="composer-footer"><span id="input-help"><kbd>Enter</kbd> 전송 <span className="footer-separator">·</span> <kbd>Shift + Enter</kbd> 줄바꿈</span><span>{preview ? '이야기는 이 창에서만 머물러요.' : '자막 번역에는 Gemini가 사용될 수 있어요.'}</span></div>
        </div>
      </section>
    </main>
  </div>
}
