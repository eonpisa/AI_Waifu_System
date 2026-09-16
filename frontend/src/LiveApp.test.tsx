import { StrictMode } from 'react'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'

class Socket {
  static instances: Socket[] = []
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  constructor() { Socket.instances.push(this) }
  emit(type: string, seq: number, data: object) {
    act(() => this.onmessage?.({ data: JSON.stringify({ type, seq, turn_id: 1, elapsed_ms: 2000, data }) }))
  }
}
beforeEach(() => {
  Socket.instances = []
  vi.stubGlobal('WebSocket', Socket)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status: 202, ok: true }))
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('connects the default screen through HTTP/WS, keeps IME protection, and returns focus after a real-format result', async () => {
  const audio = vi.spyOn(HTMLMediaElement.prototype, 'play')
  const storage = vi.spyOn(Storage.prototype, 'setItem')
  render(<StrictMode><App /></StrictMode>)
  expect(screen.getByRole('textbox')).toBeDisabled()
  expect(screen.queryByText('화면 미리보기')).not.toBeInTheDocument()
  expect(screen.queryByText('미리보기 설정')).not.toBeInTheDocument()
  expect(screen.getAllByText('미확인')).toHaveLength(4)
  const socket = Socket.instances.at(-1)!
  expect(Socket.instances[0].close).toHaveBeenCalled()
  socket.emit('state', 0, { busy: false, accepting: true, stage: 'idle' })
  const input = screen.getByRole('textbox')
  expect(input).toBeEnabled()
  fireEvent.compositionStart(input)
  fireEvent.change(input, { target: { value: '안녕' } })
  fireEvent.keyDown(input, { key: 'Enter', isComposing: true })
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.compositionEnd(input)
  await act(async () => { fireEvent.keyDown(input, { key: 'Enter' }) })
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(input).toBeDisabled()
  socket.emit('reply_ready', 1, { japanese_reply: 'こんにちは。' })
  socket.emit('subtitle_ready', 2, { korean_subtitle: '안녕하세요.' })
  expect(within(screen.getByRole('log')).getByText('안녕하세요.')).toBeVisible()
  socket.emit('turn_finished', 3, { stage: 'idle', result: {
    japanese_reply: 'こんにちは。', korean_subtitle: '안녕하세요.', audio_played: true, errors: [],
  } })
  expect(input).toBeEnabled()
  expect(input).toHaveFocus()
  expect(screen.getByText(/처리 시간 2.00초/)).toBeVisible()
  expect(audio).not.toHaveBeenCalled()
  expect(storage).not.toHaveBeenCalled()
})

it('shows connection loss and disables input without claiming the audio stopped', () => {
  render(<App />)
  const socket = Socket.instances.at(-1)!
  socket.emit('state', 0, { busy: false, accepting: true, stage: 'idle' })
  act(() => socket.onclose?.())
  expect(screen.getByRole('textbox')).toBeDisabled()
  expect(screen.getByRole('alert')).toHaveTextContent('진행 중인 음성은 서버에서 계속될 수 있어요')
  expect(screen.getByRole('button', { name: '대화 종료' })).toBeDisabled()
})

it('uses server end semantics without a misleading local restart button', async () => {
  render(<App />)
  const socket = Socket.instances.at(-1)!
  socket.emit('state', 0, { busy: false, accepting: true, stage: 'idle' })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '대화 종료' })) })
  socket.emit('state', 1, { busy: false, accepting: false, stage: 'ended' })
  expect(screen.queryByRole('button', { name: /새 미리보기 시작/ })).not.toBeInTheDocument()
  expect(screen.getByText(/새 대화는 API 서버를 재시작/)).toBeVisible()
  expect(screen.getByRole('textbox')).toBeDisabled()
})

it('shows adopted provider, fallback reason and nonfatal VTS failure, then marks evidence stale on disconnect', () => {
  render(<App />)
  const socket = Socket.instances.at(-1)!
  socket.emit('state', 0, { busy: false, accepting: true, stage: 'idle' })
  socket.emit('service_status', 1, { service: 'gemini', code: 'api_key_missing' })
  socket.emit('subtitle_provider', 2, { provider: 'qwen', model: 'qwen3.5:9b', fallback_reason: 'gemini_api_key_missing' })
  socket.emit('service_status', 3, { service: 'sbv2', code: 'synthesis_succeeded' })
  socket.emit('service_status', 4, { service: 'vts', code: 'authentication_failed' })
  socket.emit('turn_finished', 5, { stage: 'idle', result: { korean_subtitle: '안녕', audio_played: true, errors: [] } })
  expect(screen.getByRole('textbox')).toBeEnabled()
  expect(screen.getByRole('listitem', { name: 'VTube Studio: 인증 실패' })).toBeVisible()
  expect(screen.getByRole('listitem', { name: 'SBV2: 합성 성공' })).toBeVisible()
  const provider = screen.getByLabelText('자막 번역 정보')
  expect(provider).toHaveTextContent('Qwen 대체 자막 채택')
  expect(provider).toHaveTextContent('모델: qwen3.5:9b')
  expect(provider).toHaveTextContent('Gemini 키 미설정')
  expect(provider).toHaveTextContent('gemini_api_key_missing')
  expect(screen.getByText(/재생 함수 성공/)).toBeVisible()
  act(() => socket.onclose?.())
  expect(screen.getByRole('listitem', { name: 'SBV2: 확인 불가 · 이전 결과' })).toBeVisible()
  expect(provider).toHaveTextContent('이전 결과')
  expect(screen.getByRole('textbox')).toBeDisabled()
})

it('shows Gemini success and distinguishes total subtitle failure without exposing private fields', () => {
  render(<App />)
  const socket = Socket.instances.at(-1)!
  socket.emit('state', 0, { busy: false, accepting: true, stage: 'idle' })
  socket.emit('service_status', 1, { service: 'gemini', code: 'subtitle_accepted' })
  socket.emit('subtitle_provider', 2, { provider: 'gemini', model: 'gemini-3.5-flash-lite', fallback_reason: 'none', headers: 'PRIVATE_MARKER' })
  expect(screen.getByLabelText('자막 번역 정보')).toHaveTextContent('Gemini 자막 채택')
  expect(screen.getByLabelText('자막 번역 정보')).toHaveTextContent('모델: gemini-3.5-flash-lite')
  expect(screen.getByLabelText('자막 번역 정보')).toHaveTextContent('폴백 없음')
  expect(screen.getByRole('listitem', { name: 'Gemini: 자막 채택' })).toBeVisible()
  socket.emit('subtitle_provider', 3, { provider: 'none', model: 'PRIVATE_MARKER', fallback_reason: 'gemini_request_timeout;qwen_request_error' })
  expect(screen.getByLabelText('자막 번역 정보')).toHaveTextContent('자막 번역 실패')
  expect(screen.getByLabelText('자막 번역 정보')).not.toHaveTextContent('Qwen 대체 자막 채택')
  expect(document.body).not.toHaveTextContent('PRIVATE_MARKER')
})
