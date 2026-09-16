import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ConversationClient, API_BASE, EVENTS_URL } from './conversationClient'

class Socket {
  static instances: Socket[] = []
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  constructor(public url: string) { Socket.instances.push(this) }
  emit(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) }) }
}
const initial = { busy: false, accepting: true, stage: 'idle', turn_id: null, seq: 0, last_result: null }
const result = { japanese_reply: 'こんにちは。', korean_subtitle: '안녕하세요.', status: 'completed', audio_played: true, errors: [] }
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done }); return { resolve, promise } }
function response(status: number, data: unknown = {}) { return { status, ok: status >= 200 && status < 300, json: async () => data } as Response }
async function settle() { for (let i = 0; i < 10; i++) await Promise.resolve() }

describe('real single-session API client', () => {
  let client: ConversationClient
  let socket: Socket
  let fetchMock: ReturnType<typeof vi.fn>
  function event(type: string, seq: number, data: object, turn_id: number | null = 1) {
    socket.emit({ type, seq, turn_id, elapsed_ms: 1234, data })
  }
  function ready(data = initial) { event('state', data.seq, data, data.turn_id) }
  beforeEach(() => {
    vi.useFakeTimers()
    Socket.instances = []
    vi.stubGlobal('WebSocket', Socket)
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    client = new ConversationClient()
    client.start()
    socket = Socket.instances[0]
  })
  afterEach(() => { client.stop(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('waits for initial WS state before POST; duplicate calls send once and no credentials', () => {
    expect(client.send('안녕')).toBe(false)
    expect(socket.url).toBe(EVENTS_URL)
    ready()
    fetchMock.mockReturnValue(new Promise(() => {}))
    expect(client.send('안녕')).toBe(true)
    expect(client.send('겹친 입력')).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_BASE}/api/turn`)
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST', body: '{"text":"안녕"}', credentials: 'omit', headers: { 'Content-Type': 'application/json' } })
  })
  it('renders real events and unlocks only after completion, despite early HTTP acceptance', async () => {
    ready(); fetchMock.mockResolvedValue(response(202)); client.send('안녕'); await settle()
    expect(client.getSnapshot().busy).toBe(true)
    event('stage_changed', 1, { stage: 'generating' })
    event('reply_ready', 2, { japanese_reply: 'こんにちは。' })
    event('subtitle_ready', 3, { korean_subtitle: '안녕하세요.' })
    event('stage_changed', 4, { stage: 'speaking' })
    expect(client.getSnapshot()).toMatchObject({ stage: 'speaking', subtitle: '안녕하세요.', busy: true })
    event('turn_finished', 5, { stage: 'idle', result })
    expect(client.getSnapshot()).toMatchObject({ busy: false, elapsedMs: 1234, audioPlayed: true })
    expect(client.getSnapshot().messages).toHaveLength(2)
  })
  it('handles completion before POST response without re-locking or duplicating messages', async () => {
    ready(); const post = deferred<Response>(); fetchMock.mockReturnValue(post.promise)
    client.send('안녕')
    event('turn_finished', 2, { stage: 'idle', result })
    expect(client.send('아직 접수 응답 대기')).toBe(false)
    post.resolve(response(202)); await settle()
    expect(client.getSnapshot().busy).toBe(false)
    event('reply_ready', 1, { japanese_reply: '오래된 이벤트' })
    event('turn_finished', 2, { stage: 'idle', result })
    expect(client.getSnapshot().messages).toHaveLength(2)
    expect(client.getSnapshot().messages[1].japanese).toBe('こんにちは。')
    expect(client.send('다음')).toBe(true)
  })
  it('honors a busy/ended initial server session without reconstructing its old messages', () => {
    ready({ ...initial, busy: true, stage: 'speaking' })
    expect(client.send('안녕')).toBe(false)
    event('state', 1, { ...initial, accepting: false, stage: 'ended' })
    expect(client.send('안녕')).toBe(false)
    expect(client.getSnapshot().messages).toEqual([])
  })
  it.each([409, 422])('resynchronizes a rejected %s request and never displays raw error bodies', async status => {
    ready()
    fetchMock.mockResolvedValueOnce(response(status, { secret: 'DO_NOT_SHOW' }))
      .mockResolvedValueOnce(response(200, initial))
    client.send('안녕'); await settle()
    expect(client.getSnapshot().busy).toBe(false)
    expect(client.getSnapshot().warning).toContain('접수되지')
    expect(JSON.stringify(client.getSnapshot())).not.toContain('DO_NOT_SHOW')
    expect(fetchMock.mock.calls[1][0]).toBe(`${API_BASE}/api/state`)
    expect(client.send('다시')).toBe(true)
  })
  it('does not let a late HTTP state snapshot overwrite a newer WS completion', async () => {
    ready(); const state = deferred<Response>()
    fetchMock.mockResolvedValueOnce(response(409)).mockReturnValueOnce(state.promise)
    client.send('안녕'); await settle()
    event('turn_finished', 5, { stage: 'idle', result })
    state.resolve(response(200, { ...initial, busy: true, stage: 'speaking', seq: 3 })); await settle()
    expect(client.getSnapshot()).toMatchObject({ stage: 'idle', busy: false })
  })
  it('keeps Japanese text and returns to input after subtitle/TTS failure', async () => {
    ready(); fetchMock.mockResolvedValue(response(202)); client.send('안녕'); await settle()
    event('notice', 1, { code: 'synthesis_failed', message: 'DO_NOT_SHOW' })
    event('turn_finished', 2, { stage: 'idle', result: { ...result, korean_subtitle: null, audio_played: false, errors: ['subtitle_failed', 'synthesis_failed'] } })
    expect(client.getSnapshot()).toMatchObject({ busy: false, subtitle: '', audioPlayed: false })
    expect(client.getSnapshot().messages[1]).toMatchObject({ japanese: 'こんにちは。', text: '한국어 자막을 만들지 못했어요.' })
    expect(client.getSnapshot().warning).not.toContain('DO_NOT_SHOW')
    expect(client.send('다음 이야기')).toBe(true)
  })
  it('ends naturally and never sends reset/cancel requests', async () => {
    ready(); fetchMock.mockResolvedValue(response(202)); client.send('안녕'); await settle()
    client.end(); client.end()
    event('state', 1, { ...initial, busy: true, accepting: false, stage: 'speaking' })
    expect(client.getSnapshot().ending).toBe(true)
    event('turn_finished', 2, { stage: 'ended', result })
    expect(client.getSnapshot()).toMatchObject({ stage: 'ended', busy: false, ending: false })
    expect(client.send('다시')).toBe(false)
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual([`${API_BASE}/api/turn`, `${API_BASE}/api/end`])
  })
  it('locks on disconnect without retry or cancelling server audio', () => {
    ready(); fetchMock.mockReturnValue(new Promise(() => {})); client.send('안녕')
    socket.onclose?.()
    expect(client.getSnapshot().connected).toBe(false)
    expect(client.send('재전송')).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(client.getSnapshot().warning).toContain('자동 재전송하지')
  })
  it('treats uncertain HTTP acceptance as disconnected and never exposes exception text', async () => {
    ready(); fetchMock.mockRejectedValue(new Error('DO_NOT_SHOW')); client.send('안녕'); await settle()
    expect(client.getSnapshot().connected).toBe(false)
    expect(client.getSnapshot().warning).not.toContain('DO_NOT_SHOW')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it('times out an unresponsive initial WS and rejects malformed data safely', () => {
    vi.advanceTimersByTime(10000)
    expect(socket.close).toHaveBeenCalled()
    expect(client.send('안녕')).toBe(false)
    client.start(); socket = Socket.instances.at(-1)!
    socket.emit({ type: 'state', seq: 0, data: { busy: 'wrong' } })
    expect(client.getSnapshot().connected).toBe(false)
  })
  it('cleans up handlers, timers, and in-flight HTTP on unmount, with no end request', () => {
    ready(); fetchMock.mockReturnValue(new Promise(() => {})); client.send('안녕')
    const signal = fetchMock.mock.calls[0][1].signal as AbortSignal
    client.stop()
    expect(signal.aborted).toBe(true)
    expect(socket.close).toHaveBeenCalled()
    expect(socket.onmessage).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it('retains only observed service evidence, updates recovery, and clears a prior subtitle provider on the next turn', async () => {
    ready()
    expect(Object.values(client.getSnapshot().services).every(item => item.state === 'unknown')).toBe(true)
    event('service_status', 1, { service: 'gemini', code: 'api_key_missing', state: 'error' })
    event('subtitle_provider', 2, { provider: 'qwen', model: 'qwen3.5:9b', fallback_reason: 'gemini_api_key_missing' })
    event('service_status', 3, { service: 'vts', code: 'connection_failed', state: 'error' })
    event('turn_finished', 4, { stage: 'idle', result })
    expect(client.getSnapshot().services.vts).toMatchObject({ state: 'error', turn_id: 1 })
    expect(client.getSnapshot().audioPlayed).toBe(true)
    expect(client.getSnapshot().subtitleProvider?.provider).toBe('qwen')
    fetchMock.mockResolvedValue(response(202)); client.send('다음'); await settle()
    expect(client.getSnapshot().subtitleProvider).toBeNull()
    // No unobserved inference that VTS/SBV2 recovered merely because a turn started.
    expect(client.getSnapshot().services.vts.state).toBe('error')
    expect(client.getSnapshot().services.sbv2.state).toBe('unknown')
    event('service_status', 5, { service: 'gemini', code: 'subtitle_accepted', state: 'ok' }, 2)
    event('subtitle_provider', 6, { provider: 'gemini', model: 'gemini-3.5-flash-lite', fallback_reason: 'none' }, 2)
    event('service_status', 7, { service: 'vts', code: 'parameters_applied', state: 'ok' }, 2)
    event('service_status', 3, { service: 'vts', code: 'connection_failed', state: 'error' })
    expect(client.getSnapshot().services.vts).toMatchObject({ state: 'ok', turn_id: 2 })
    expect(client.getSnapshot().subtitleProvider).toMatchObject({ provider: 'gemini', fallback_reason: 'none', turn_id: 2 })
    socket.onclose?.()
    expect(client.getSnapshot().connected).toBe(false)
    expect(client.send('중복')).toBe(false)
  })
  it('restores only safe metadata from the initial snapshot and never raw provider fields', () => {
    event('state', 0, { ...initial, services: {
      ollama: { state: 'ok', code: 'PRIVATE_MARKER', token: 'PRIVATE_MARKER' },
      sbv2: { state: 'ok', code: 'synthesis_succeeded', turn_id: 3, headers: 'PRIVATE_MARKER' },
    }, subtitle_provider: { provider: 'qwen', model: '/PRIVATE_MARKER/model', fallback_reason: 'PRIVATE_MARKER', turn_id: 3 } })
    expect(client.getSnapshot().services.ollama.state).toBe('unknown')
    expect(client.getSnapshot().services.sbv2).toMatchObject({ state: 'ok', turn_id: 3 })
    expect(client.getSnapshot().subtitleProvider).toEqual({ provider: 'qwen', model: 'custom', fallback_reason: 'translation_failed', turn_id: 3 })
    expect(JSON.stringify(client.getSnapshot())).not.toContain('PRIVATE_MARKER')
    expect(client.getSnapshot().messages).toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()
    event('subtitle_provider', 1, { provider: 'PRIVATE_MARKER', model: 'PRIVATE_MARKER' })
    expect(client.getSnapshot().subtitleProvider).toBeNull()
  })
  it('clears provider information when a turn is submitted by another subscriber', () => {
    ready()
    event('subtitle_provider', 1, { provider: 'gemini', model: 'gemini-3.5-flash-lite', fallback_reason: 'none' })
    event('stage_changed', 2, { stage: 'queued' }, 2)
    expect(client.getSnapshot().subtitleProvider).toBeNull()
  })
})
