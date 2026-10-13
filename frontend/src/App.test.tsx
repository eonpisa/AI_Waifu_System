import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

function send(text = '오늘 학교에서 시험을 봤어.') {
  fireEvent.change(screen.getByRole('textbox', { name: '한국어 메시지' }), { target: { value: text } })
  fireEvent.click(screen.getByRole('button', { name: '전송' }))
}
function advance(ms = 4500) { act(() => vi.advanceTimersByTime(ms)) }
function choose(scenario: string) {
  fireEvent.click(screen.getByText('미리보기 설정'))
  fireEvent.change(screen.getByLabelText('다음 전송의 예시 동작'), { target: { value: scenario } })
}

describe('single-session screen preview', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

  it('clearly identifies mock mode and never reports a service as connected', () => {
    render(<App preview />)
    expect(screen.getByText('화면 미리보기')).toBeVisible()
    expect(screen.getAllByText('미연결')).toHaveLength(4)
    expect(screen.getByRole('button', { name: '음성 입력 — 준비 중' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '전송' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('입력 대기')
  })

  it('fills a suggestion without automatically sending it', () => {
    render(<App preview />)
    fireEvent.click(screen.getByRole('button', { name: /오늘 있었던 일/ }))
    expect(screen.getByRole('textbox')).toHaveValue('오늘 학교에서 시험을 봤어.')
    expect(screen.getByRole('textbox')).toHaveFocus()
    expect(screen.getByRole('log')).toBeEmptyDOMElement()
  })

  it('keeps the menu optional and leaves the conversation available', () => {
    render(<App preview />)
    fireEvent.click(screen.getByRole('button', { name: '메뉴 접기' }))
    expect(screen.getByRole('button', { name: '메뉴 열기' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('textbox', { name: '한국어 메시지' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: '메뉴 열기' }))
    expect(screen.getByRole('button', { name: '메뉴 접기' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('closes from inside the sidebar and restores focus to the reopen button', () => {
    render(<App preview />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '작성 중인 메시지' } })
    fireEvent.click(screen.getByRole('button', { name: '사이드바 닫기' }))
    const openButton = screen.getByRole('button', { name: '메뉴 열기' })
    expect(openButton).toHaveFocus()
    expect(openButton).toHaveAttribute('aria-controls', 'conversation-sidebar')
    expect(screen.getByRole('complementary')).toHaveAttribute('inert')
    expect(screen.getByRole('textbox')).toHaveValue('작성 중인 메시지')
    fireEvent.click(openButton)
    expect(screen.getByRole('complementary')).not.toHaveAttribute('inert')
    fireEvent.keyDown(screen.getByRole('button', { name: '사이드바 닫기' }), { key: 'Escape' })
    expect(screen.getByRole('button', { name: '메뉴 열기' })).toHaveFocus()
  })

  it('opens the narrow-screen menu with an accessible close button', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
    render(<App preview />)
    fireEvent.click(screen.getByRole('button', { name: '메뉴 열기' }))
    expect(screen.getByRole('button', { name: '사이드바 닫기' })).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: '메뉴 닫기' }))
    expect(screen.getByRole('button', { name: '메뉴 열기' })).toHaveFocus()
  })

  it('resizes with keyboard within limits and preserves width when reopened', () => {
    vi.stubGlobal('innerWidth', 1600)
    render(<App preview />)
    const handle = screen.getByRole('separator', { name: '사이드바 너비 조절' })
    expect(handle).toHaveAttribute('aria-valuenow', '400')
    fireEvent.keyDown(handle, { key: 'ArrowRight' })
    expect(handle).toHaveAttribute('aria-valuenow', '410')
    fireEvent.keyDown(handle, { key: 'End' })
    fireEvent.keyDown(handle, { key: 'ArrowRight' })
    expect(handle).toHaveAttribute('aria-valuenow', '880')
    fireEvent.keyDown(handle, { key: 'Home' })
    fireEvent.keyDown(handle, { key: 'ArrowLeft' })
    expect(handle).toHaveAttribute('aria-valuenow', '400')
    fireEvent.click(screen.getByRole('button', { name: '메뉴 접기' }))
    expect(screen.queryByRole('separator')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '메뉴 열기' }))
    expect(screen.getByRole('separator')).toHaveAttribute('aria-valuenow', '400')
  })

  it('drags the sidebar edge and stops resizing on release or cancellation', () => {
    vi.stubGlobal('PointerEvent', MouseEvent)
    render(<App preview />)
    const handle = screen.getByRole('separator')
    fireEvent.pointerDown(handle, { button: 0, clientX: 400 })
    fireEvent.pointerMove(handle, { clientX: 460 })
    expect(handle).toHaveAttribute('aria-valuenow', '460')
    expect(document.querySelector('.app-shell')).toHaveStyle('--sidebar-width: 460px')
    fireEvent.pointerUp(handle)
    fireEvent.pointerMove(handle, { clientX: 400 })
    expect(handle).toHaveAttribute('aria-valuenow', '460')
    fireEvent.pointerDown(handle, { button: 0, clientX: 460 })
    fireEvent.pointerMove(handle, { clientX: 0 })
    expect(handle).toHaveAttribute('aria-valuenow', '400')
    fireEvent.pointerCancel(handle)
    fireEvent.pointerMove(handle, { clientX: 450 })
    expect(handle).toHaveAttribute('aria-valuenow', '400')
    expect(document.querySelector('.app-shell')).not.toHaveClass('sidebar-resizing')
  })

  it('limits the sidebar to keep the conversation visible when the viewport shrinks', () => {
    render(<App preview />)
    const handle = screen.getByRole('separator')
    fireEvent.keyDown(handle, { key: 'End' })
    vi.stubGlobal('innerWidth', 850)
    fireEvent(window, new Event('resize'))
    expect(handle).toHaveAttribute('aria-valuenow', '370')
    vi.stubGlobal('innerWidth', 320)
    fireEvent(window, new Event('resize'))
    expect(handle).toHaveAttribute('aria-valuemax', '288')
    expect(handle).toHaveAttribute('aria-valuenow', '288')
  })

  it('rejects whitespace and a forged over-limit submission', () => {
    render(<App preview />)
    send('   \n ')
    expect(screen.getByRole('log')).toBeEmptyDOMElement()
    send('가'.repeat(2001))
    expect(screen.getByRole('log')).toBeEmptyDOMElement()
    expect(screen.getByRole('textbox')).toHaveAttribute('maxlength', '2000')
  })

  it('walks through every stage, shows subtitles, and returns focus to input', () => {
    render(<App preview />)
    send()
    expect(screen.getByRole('status')).toHaveTextContent('입력 번역 중')
    expect(screen.getByRole('textbox')).toBeDisabled()
    expect(screen.getByRole('button', { name: '전송' })).toBeDisabled()
    advance(450)
    expect(screen.getByRole('status')).toHaveTextContent('응답 생성 중')
    advance(750)
    expect(screen.getByRole('status')).toHaveTextContent('자막 번역 중')
    expect(screen.getByText('예시 답변')).toBeVisible()
    advance(650)
    expect(screen.getByRole('status')).toHaveTextContent('음성 합성 중')
    expect(screen.getAllByText('이야기해 줘서 고마워요. 오늘은 어떤 하루였나요?')).toHaveLength(1)
    fireEvent.click(screen.getByText('원문 보기'))
    expect(screen.getByText('話してくれてありがとうございます。今日はどんな一日でしたか？')).toBeVisible()
    advance(750)
    expect(screen.getByRole('status')).toHaveTextContent('말하는 중')
    expect(document.querySelector('.character-avatar')).toHaveClass('is-speaking')
    expect(document.querySelector('.wave-active')).not.toBeInTheDocument()
    advance(1600)
    expect(screen.getByRole('status')).toHaveTextContent('입력 대기')
    expect(screen.getByRole('textbox')).toBeEnabled()
    expect(screen.getByRole('textbox')).toHaveFocus()
    expect(within(screen.getByRole('log')).getAllByRole('article')).toHaveLength(2)
  })

  it('does not jump away from older messages when a new reply arrives', () => {
    render(<App preview />)
    send('첫 이야기')
    advance()
    send('두 번째 이야기')
    const history = document.querySelector('.history') as HTMLDivElement
    Object.defineProperty(history, 'scrollHeight', { configurable: true, value: 1200 })
    Object.defineProperty(history, 'clientHeight', { configurable: true, value: 300 })
    history.scrollTop = 0
    fireEvent.scroll(history)
    advance(1850)
    expect(history.scrollTop).toBe(0)
    fireEvent.click(screen.getByRole('button', { name: '최신 메시지 ↓' }))
    expect(history.scrollTop).toBe(1200)
    expect(screen.queryByRole('button', { name: '최신 메시지 ↓' })).not.toBeInTheDocument()
  })

  it('rejects a second form submission while a turn is running', () => {
    render(<App preview />)
    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: '첫 발화' } })
    const form = textarea.closest('form')!
    act(() => { fireEvent.submit(form); fireEvent.submit(form) })
    advance()
    expect(within(screen.getByRole('log')).getAllByRole('article')).toHaveLength(2)
  })

  it('does not send Enter during Korean composition, then sends completed text once', () => {
    render(<App preview />)
    const textarea = screen.getByRole('textbox')
    fireEvent.compositionStart(textarea)
    fireEvent.change(textarea, { target: { value: '안녕' } })
    fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter' })
    expect(screen.getByRole('log')).toBeEmptyDOMElement()
    fireEvent.compositionEnd(textarea, { data: '녕' })
    expect(textarea).toHaveValue('안녕')
    fireEvent.keyDown(textarea, { key: 'Enter', code: 'Enter' })
    expect(within(screen.getByRole('log')).getByText('안녕')).toBeVisible()
    expect(textarea).toHaveValue('')
  })

  it('honors native isComposing and keyCode 229 guards', () => {
    render(<App preview />)
    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: '한글' } })
    fireEvent.keyDown(textarea, { key: 'Enter', isComposing: true })
    fireEvent.keyDown(textarea, { key: 'Enter', keyCode: 229 })
    expect(screen.getByRole('log')).toBeEmptyDOMElement()
  })

  it('Shift+Enter inserts a newline without sending', async () => {
    vi.useRealTimers()
    const user = userEvent.setup()
    render(<App preview />)
    await user.type(screen.getByRole('textbox'), '첫 줄{Shift>}{Enter}{/Shift}둘째 줄')
    expect(screen.getByRole('textbox')).toHaveValue('첫 줄\n둘째 줄')
    expect(screen.getByRole('log')).toBeEmptyDOMElement()
  })

  it('keeps the subtitle after synthesis failure and accepts the next turn', () => {
    render(<App preview />)
    choose('tts_error')
    send()
    advance()
    expect(screen.getByRole('alert')).toHaveTextContent('음성을 만들지 못했어요')
    expect(screen.getByRole('textbox')).toBeEnabled()
    expect(screen.getAllByText('이야기해 줘서 고마워요. 오늘은 어떤 하루였나요?')).toHaveLength(1)
    fireEvent.change(screen.getByLabelText('다음 전송의 예시 동작'), { target: { value: 'normal' } })
    send('다음 이야기')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    advance()
    expect(within(screen.getByRole('log')).getAllByRole('article')).toHaveLength(4)
  })

  it('allows the simulated speaking phase despite a VTS error', () => {
    render(<App preview />)
    choose('vts_error')
    send()
    advance(2600)
    expect(screen.getByRole('alert')).toHaveTextContent('캐릭터에 연결하지 못했어요')
    expect(screen.getByRole('status')).toHaveTextContent('말하는 중')
    fireEvent.click(screen.getByRole('button', { name: '오류 안내 닫기' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    advance()
    expect(screen.getByRole('status')).toHaveTextContent('입력 대기')
  })

  it('ends only after the current mock turn finishes and preserves its history', () => {
    render(<App preview />)
    send()
    const history = document.querySelector('.history') as HTMLDivElement
    Object.defineProperty(history, 'scrollHeight', { configurable: true, value: 900 })
    fireEvent.click(screen.getByRole('button', { name: '대화 종료' }))
    expect(screen.getByText('진행 중인 예시 답변이 끝나면 대화를 종료해요.')).toBeVisible()
    advance()
    expect(screen.getByRole('status')).toHaveTextContent('대화 종료')
    expect(screen.getByRole('textbox')).toBeDisabled()
    expect(within(screen.getByRole('log')).getAllByRole('article')).toHaveLength(2)
    expect(history.scrollTop).toBe(900)
    fireEvent.click(screen.getByRole('button', { name: /새 미리보기 시작/ }))
    advance(0)
    expect(screen.getByRole('log')).toBeEmptyDOMElement()
    expect(screen.getByRole('textbox')).toBeEnabled()
  })

  it('ends an idle session without starting any mock tasks', () => {
    render(<App preview />)
    fireEvent.click(screen.getByRole('button', { name: '대화 종료' }))
    expect(screen.getByRole('status')).toHaveTextContent('대화 종료')
    expect(screen.getByRole('textbox')).toBeDisabled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('clears all pending mock events on unmount', () => {
    const view = render(<App preview />)
    send()
    expect(vi.getTimerCount()).toBeGreaterThan(0)
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('never calls API, audio, or storage and renders markup as plain text', () => {
    const network = vi.fn(() => { throw new Error('unexpected API request') })
    const socket = vi.fn(() => { throw new Error('unexpected WebSocket') })
    const audio = vi.spyOn(HTMLMediaElement.prototype, 'play')
    const storage = vi.spyOn(Storage.prototype, 'setItem')
    vi.stubGlobal('fetch', network)
    vi.stubGlobal('WebSocket', socket)
    render(<App preview />)
    const text = '<img src="x" onerror="alert(1)">'
    send(text)
    advance()
    expect(within(screen.getByRole('log')).getByText(text)).toBeVisible()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(network).not.toHaveBeenCalled()
    expect(socket).not.toHaveBeenCalled()
    expect(audio).not.toHaveBeenCalled()
    expect(storage).not.toHaveBeenCalled()
  })
})
