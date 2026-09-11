import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { Icon, Wave } from './Icons'
import { stageLabels } from './mockConversation'
import type { Scenario } from './mockConversation'
import { useConversationPreview } from './useConversationPreview'

const services = [
  ['Ollama', '대화와 입력 번역'], ['Gemini', '한국어 자막'],
  ['SBV2', '일본어 음성'], ['VTube Studio', '표정과 입 움직임'],
]
const suggestions = ['오늘 학교에서 시험을 봤어.', '오늘은 기분이 정말 좋아!', '내일은 친구와 산책할 거야.']

export default function App() {
  const chat = useConversationPreview()
  const [draft, setDraft] = useState('')
  const [scenario, setScenario] = useState<Scenario>('normal')
  const composing = useRef(false)
  const input = useRef<HTMLTextAreaElement>(null)
  const history = useRef<HTMLDivElement>(null)
  const nearBottom = useRef(true)
  const wasBusy = useRef(false)
  const ended = chat.stage === 'ended'
  const inputDisabled = chat.busy || ended

  useEffect(() => {
    if (wasBusy.current && !chat.busy && !ended) input.current?.focus()
    wasBusy.current = chat.busy
  }, [chat.busy, ended])
  useEffect(() => {
    if (nearBottom.current && history.current) history.current.scrollTop = history.current.scrollHeight
  }, [chat.messages, chat.stage])

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (composing.current) return
    if (chat.send(draft, scenario)) { setDraft(''); nearBottom.current = true }
  }
  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey) return
    // keyCode 229 covers IME Enter behavior in browsers where isComposing is false.
    if (composing.current || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return
    event.preventDefault()
    submit()
  }

  return <div className="app-shell">
    <aside className="sidebar" aria-label="대화 및 연결 상태">
      <div className="brand"><span className="brand-mark"><Icon name="spark" /></span><span>AI WAIFU<span className="brand-sub">A little closer, every day.</span></span></div>
      <div className="workspace-label">MY SPACE <span>01</span></div>
      <div className="nav-current"><Icon name="chat" /><span>대화</span><span className="nav-dot" /></div>
      <div className="session-note"><span className="tiny-line" />지금 이 창의 이야기<span>새로고침하면 기록이 사라져요.</span></div>

      <section className="connections" aria-labelledby="connections-title">
        <div className="section-label"><h2 id="connections-title">연결 상태</h2><span className="small-tag">확인 전</span></div>
        <p className="muted small">실제 서비스 연결은 다음 단계예요.</p>
        <ul>{services.map(([name, description]) => <li key={name}>
          <span className="service-dot" /><div><strong>{name}</strong><span>{description}</span></div><span className="service-state">미연결</span>
        </li>)}</ul>
      </section>
      <div className="sidebar-bottom">
        <details className="preview-settings">
          <summary>미리보기 설정 <Icon name="chevron" /></summary>
          <label htmlFor="scenario">다음 전송의 예시 동작</label>
          <select id="scenario" value={scenario} disabled={chat.busy || ended} onChange={event => setScenario(event.target.value as Scenario)}>
            <option value="normal">정상 흐름</option><option value="tts_error">음성 합성 오류</option><option value="vts_error">캐릭터 연결 오류</option>
          </select>
          <p>답변은 고정된 예시이며, 음성은 재생하지 않아요.</p>
        </details>
        <div className="local-note"><span className="local-symbol">⌂</span> 나만의 작은 대화 공간</div>
      </div>
    </aside>

    <main className="main-panel">
      <header className="topbar">
        <div><div className="eyebrow">YOUR EVERYDAY COMPANION</div><h1>우리의 대화<span className="title-dot">.</span></h1></div>
        <button className="end-button" onClick={chat.end} disabled={ended || chat.ending}><Icon name="stop" />{chat.ending ? '이번 답변 후 종료' : ended ? '종료됨' : '대화 종료'}</button>
      </header>
      <div className="preview-banner"><Icon name="info" /><span><strong>화면 미리보기</strong><span className="banner-detail"> · 실제 AI·음성·캐릭터는 연결하지 않았어요.</span></span><span className="preview-pill">PREVIEW</span></div>

      <section className="conversation-panel" aria-label="대화 공간">
        <div className="conversation-heading"><span><span className="companion-dot" />당신의 AI 친구</span><span className={`stage-badge ${chat.busy ? 'is-busy' : ''}`} role="status">{chat.busy && <span className="pulse-dot" />}{stageLabels[chat.stage]}{chat.busy && ' · 예시'}</span></div>
        <div className="history" ref={history} onScroll={() => { const el = history.current; if (el) nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80 }}>
          {chat.messages.length === 0 && !ended ? <div className="welcome">
            <div className="welcome-art" aria-hidden="true"><span className="orbit orbit-one" /><span className="orbit orbit-two" /><span className="orb"><Icon name="spark" /></span><span className="satellite" /><span className="little-star">✧</span></div>
            <span className="welcome-caption">작은 이야기부터, 천천히</span>
            <h2>오늘은 어떤 하루였나요?</h2>
            <p>기뻤던 일도, 조금 지쳤던 순간도.<br />마음에 남은 이야기를 들려주세요.</p>
            <div className="suggestions" aria-label="시작 문장 예시">{suggestions.map((text, index) => <button key={text} onClick={() => { setDraft(text); input.current?.focus() }}><span>{['☀', '✧', '♧'][index]}</span>{['오늘 있었던 일', '기분 좋은 소식', '내일의 작은 계획'][index]}<Icon name="arrow" /></button>)}</div>
          </div> : null}
          <div className="messages" role="log" aria-label="대화 기록" aria-live="polite" aria-relevant="additions text">
            {chat.messages.map(message => <article key={message.id} className={`message ${message.role}`}>
              {message.role === 'assistant' && <span className="message-avatar"><Icon name="spark" /></span>}
              <div className="message-content"><div className="message-name">{message.role === 'user' ? '나' : 'AI 친구'}{message.role === 'assistant' && <span>예시 답변</span>}</div>
                <div className="message-bubble">{message.text || <span className="muted">한국어 자막을 준비하고 있어요…</span>}</div>
                {message.japanese && <details className="japanese"><summary>일본어 원문 <Icon name="chevron" /></summary><p lang="ja">{message.japanese}</p></details>}
              </div>
            </article>)}
            {chat.busy && !chat.messages.at(-1)?.japanese && <div className="thinking" aria-label="답변 준비 중"><span /><span /><span /></div>}
          </div>
          {ended && <div className="ended-note"><Icon name="spark" /><h2>잠시 쉬어 가도 괜찮아요.</h2><p>이 대화는 여기까지예요. 기록은 이 창에 남아 있어요.</p><button className="text-button" onClick={() => { chat.restart(); setDraft(''); setTimeout(() => input.current?.focus(), 0) }}>새 미리보기 시작 <Icon name="arrow" /></button></div>}
        </div>

        <div className="bottom-panel">
          {chat.warning && <div className="warning" role="alert"><Icon name="info" /><p>{chat.warning}</p><button aria-label="오류 안내 닫기" onClick={chat.dismissWarning}><Icon name="close" /></button></div>}
          {chat.ending && <p className="ending-notice" role="status">진행 중인 예시 답변이 끝나면 대화를 종료해요.</p>}
          <section className={`subtitle-panel ${chat.stage === 'speaking' ? 'subtitle-speaking' : ''}`} aria-labelledby="subtitle-title">
            <div className="subtitle-heading"><span id="subtitle-title"><Icon name="sound" />현재 한국어 자막</span><span>예시 · KO</span></div>
            <div className="subtitle-body"><p className={chat.subtitle ? '' : 'subtitle-empty'}>{chat.subtitle || '답변이 도착하면 이곳에 자막이 보여요.'}</p><Wave active={chat.stage === 'speaking'} /></div>
          </section>
          <form className={`composer ${inputDisabled ? 'composer-disabled' : ''}`} onSubmit={submit}>
            <label className="sr-only" htmlFor="message-input">한국어 메시지</label>
            <textarea id="message-input" ref={input} value={draft} disabled={inputDisabled} maxLength={2000} rows={2} placeholder={ended ? '종료된 대화예요.' : chat.busy ? '답변을 준비하고 있어요…' : '편하게 이야기해 주세요…'} onChange={event => setDraft(event.target.value)} onCompositionStart={() => { composing.current = true }} onCompositionEnd={() => { composing.current = false }} onKeyDown={keyDown} aria-describedby="input-help" />
            <div className="composer-toolbar"><span className="mic-group"><button type="button" className="mic-button" disabled aria-label="음성 입력 — 준비 중" title="음성 입력은 후속 단계에서 제공됩니다"><Icon name="mic" /></button><span>음성 입력 준비 중</span></span><span className="composer-actions"><span className="character-count">{draft.length.toLocaleString()} / 2,000</span><button type="submit" className="send-button" disabled={inputDisabled || !draft.trim()}><span>전송</span><Icon name="arrow" /></button></span></div>
          </form>
          <div className="composer-footer"><span id="input-help"><kbd>Enter</kbd> 전송 <span className="footer-separator">·</span> <kbd>Shift + Enter</kbd> 줄바꿈</span><span>이야기는 이 창에서만 머물러요.</span></div>
        </div>
      </section>
    </main>
  </div>
}
