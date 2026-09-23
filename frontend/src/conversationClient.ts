// Single-session browser boundary. Secrets, audio and model calls stay in Python.
import type { Message } from './useConversationPreview'
import type { Stage } from './mockConversation'
import { readObservation, readServices, readSubtitleProvider, serviceNames, unknownServices } from './serviceStatus'
import type { Services, ServiceName, SubtitleProvider } from './serviceStatus'

export const API_BASE = 'http://127.0.0.1:8000'
export const EVENTS_URL = 'ws://127.0.0.1:8000/api/events'
export const errors: Record<string, string> = {
  input_translation_failed: '입력 번역에 실패했어요. 서버 상태를 확인한 뒤 다시 입력해 주세요.',
  ambiguous_input: '뜻을 확인하기 어려워요. 조금 더 구체적으로 입력해 주세요.',
  japanese_reply_failed: '일본어 답변 검증에 실패했어요. 다음 이야기를 입력할 수 있어요.',
  subtitle_failed: '한국어 자막을 만들지 못했어요. 일본어 원문을 확인해 주세요.',
  synthesis_failed: '음성을 만들지 못했어요. 자막은 계속 확인할 수 있어요.',
  playback_failed: '음성을 재생하지 못했어요. 오디오 장치를 확인해 주세요.',
  empty_tts_text: '읽을 문장이 없어 음성을 재생하지 않았어요.',
  turn_failed: '이번 대화를 처리하지 못했어요. 다음 이야기를 입력할 수 있어요.',
}
const stages = new Set<Stage>(['idle', 'queued', 'transcribing_audio', 'translating_input', 'generating',
  'translating_subtitle', 'synthesizing', 'speaking', 'ended'])
type ObjectData = Record<string, unknown>
function object(value: unknown): value is ObjectData {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function isStage(value: unknown): value is Stage { return stages.has(value as Stage) }
function text(value: unknown) { return typeof value === 'string' ? value : '' }

export type ConversationState = {
  messages: Message[]; stage: Stage; subtitle: string; warning: string;
  connected: boolean; busy: boolean; ending: boolean; accepting: boolean;
  elapsedMs: number | null; audioPlayed: boolean | null;
  services: Services; subtitleProvider: SubtitleProvider | null;
}

export class ConversationClient {
  private state: ConversationState = { messages: [], stage: 'idle', subtitle: '', warning: '',
    connected: false, busy: false, ending: false, accepting: false, elapsedMs: null, audioPlayed: null,
    services: unknownServices(), subtitleProvider: null }
  private listeners = new Set<() => void>()
  private socket?: WebSocket
  private requests = new Set<AbortController>()
  private stopped = true
  private seq = -1
  private pending = false
  private userId = 0
  private connectTimer?: ReturnType<typeof setTimeout>

  getSnapshot = () => this.state
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private update(patch: Partial<ConversationState>) {
    if (this.stopped) return
    this.state = { ...this.state, ...patch }
    this.listeners.forEach(listener => listener())
  }
  start = () => {
    this.stopped = false
    this.seq = -1
    const socket = new WebSocket(EVENTS_URL)
    this.socket = socket
    this.connectTimer = setTimeout(() => this.disconnect(), 10000)
    socket.onmessage = event => {
      if (this.stopped || this.socket !== socket) return
      try { this.receive(JSON.parse(event.data)) } catch { this.disconnect() }
    }
    socket.onerror = () => { if (this.socket === socket) this.disconnect() }
    socket.onclose = () => { if (this.socket === socket) this.disconnect() }
  }
  stop = () => {
    this.stopped = true
    clearTimeout(this.connectTimer)
    this.requests.forEach(request => request.abort())
    this.requests.clear()
    const socket = this.socket
    this.socket = undefined
    if (socket) { socket.onclose = null; socket.onerror = null; socket.onmessage = null; socket.close() }
  }
  private disconnect() {
    this.update({ connected: false, accepting: false,
      warning: 'API 연결을 확인할 수 없어요. 자동 재전송하지 않습니다. 서버를 확인하고 화면을 새로고침해 주세요. 진행 중인 음성은 서버에서 계속될 수 있어요.' })
    this.stop()
  }
  private applyState(data: ObjectData) {
    if (typeof data.busy !== 'boolean' || typeof data.accepting !== 'boolean' || !isStage(data.stage)) {
      throw new Error('invalid state')
    }
    this.update({ stage: data.stage, busy: data.busy || this.pending, accepting: data.accepting,
      ending: !data.accepting && data.busy, services: readServices(data.services),
      subtitleProvider: readSubtitleProvider(data.subtitle_provider) })
  }
  private reply(turn: number, patch: Partial<Message>) {
    const id = `${turn}-assistant`
    const exists = this.state.messages.some(message => message.id === id)
    this.update({ messages: exists
      ? this.state.messages.map(message => message.id === id ? { ...message, ...patch } : message)
      : [...this.state.messages, { id, role: 'assistant', text: '', ...patch }] })
  }
  private receive(value: unknown) {
    if (!object(value) || !Number.isSafeInteger(value.seq) || !object(value.data)) throw new Error('invalid event')
    const seq = value.seq as number
    if (seq <= this.seq) return
    if (this.seq < 0 && value.type !== 'state') throw new Error('missing initial state')
    const data = value.data
    if (value.type === 'state') {
      this.applyState(data)
      clearTimeout(this.connectTimer)
      this.update({ connected: true })
      // Initial state synchronizes the lock only; it never reconstructs prior chat.
    } else {
      if (!Number.isSafeInteger(value.turn_id) || (value.turn_id as number) < 1) throw new Error('invalid turn')
      const turn = value.turn_id as number
      if (value.type === 'stage_changed') {
        if (!isStage(data.stage)) throw new Error('invalid stage')
        this.update({ stage: data.stage, busy: true,
          ...(data.stage === 'queued' ? { subtitleProvider: null } : {}) })
      } else if (value.type === 'service_status') {
        if (serviceNames.includes(data.service as ServiceName)) {
          const name = data.service as ServiceName
          this.update({ services: { ...this.state.services, [name]: readObservation(name, { ...data, turn_id: turn }) } })
        }
      } else if (value.type === 'subtitle_provider') {
        this.update({ subtitleProvider: readSubtitleProvider({ ...data, turn_id: turn }) })
      } else if (value.type === 'reply_ready') {
        this.reply(turn, { japanese: text(data.japanese_reply) })
      } else if (value.type === 'subtitle_ready') {
        const subtitle = text(data.korean_subtitle)
        this.update({ subtitle })
        this.reply(turn, { text: subtitle || '한국어 자막을 만들지 못했어요.' })
      } else if (value.type === 'notice') {
        this.update({ warning: errors[text(data.code)] || errors.turn_failed })
      } else if (value.type === 'turn_finished') {
        if (!object(data.result) || !['idle', 'ended'].includes(text(data.stage))) throw new Error('invalid result')
        const result = data.result
        const subtitle = text(result.korean_subtitle)
        if (text(result.japanese_reply)) this.reply(turn, {
          japanese: text(result.japanese_reply), text: subtitle || '한국어 자막을 만들지 못했어요.',
        })
        const codes = Array.isArray(result.errors) ? result.errors : []
        this.update({ stage: data.stage as Stage, busy: this.pending, ending: false,
          accepting: data.stage === 'idle', subtitle,
          audioPlayed: typeof result.audio_played === 'boolean' ? result.audio_played : null,
          elapsedMs: typeof value.elapsed_ms === 'number' && Number.isFinite(value.elapsed_ms) ? value.elapsed_ms : null,
          ...(codes.length ? { warning: codes.map(code => errors[text(code)] || errors.turn_failed).join(' ') } : {}) })
      }
    }
    this.seq = seq
  }
  private async request(path: string, body?: object, method = 'POST'): Promise<Response> {
    const controller = new AbortController()
    this.requests.add(controller)
    const timer = setTimeout(() => controller.abort(), 10000)
    try {
      return await fetch(`${API_BASE}${path}`, { method, signal: controller.signal,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined, credentials: 'omit', cache: 'no-store' })
    } finally { clearTimeout(timer); this.requests.delete(controller) }
  }
  send = (input: string): boolean => {
    if (!input.trim() || [...input].length > 2000 || !this.state.connected || !this.state.accepting || this.state.busy || this.pending) return false
    this.pending = true // Reserve synchronously, before HTTP or React re-render.
    this.update({ busy: true, stage: 'queued', subtitle: '', warning: '', elapsedMs: null, audioPlayed: null, subtitleProvider: null,
      messages: [...this.state.messages, { id: `local-${++this.userId}`, role: 'user', text: input.trim() }] })
    void this.submit(input.trim())
    return true
  }
  private async submit(input: string) {
    try {
      const response = await this.request('/api/turn', { text: input })
      if (this.stopped) return
      if (response.status === 202) {
        this.pending = false
        // Completion events can arrive before the HTTP response.
        this.update({ busy: this.state.stage !== 'idle' && this.state.stage !== 'ended' })
      } else if ([409, 422].includes(response.status)) {
        this.pending = false
        this.update({ warning: response.status === 409
          ? '이번 입력은 접수되지 않았어요. 서버가 처리 중이거나 대화가 종료됐어요.'
          : '이번 입력은 접수되지 않았어요. 1~2000자의 내용을 입력해 주세요.' })
        const snapshot = await this.request('/api/state', undefined, 'GET')
        if (this.stopped) return
        if (!snapshot.ok) throw new Error('state unavailable')
        const data: unknown = await snapshot.json()
        if (!object(data) || !Number.isSafeInteger(data.seq)) throw new Error('invalid state')
        if ((data.seq as number) >= this.seq) { this.applyState(data); this.seq = data.seq as number }
        else this.update({ busy: !['idle', 'ended'].includes(this.state.stage) })
      } else throw new Error('unknown acceptance')
    } catch { if (!this.stopped) this.disconnect() }
  }
  end = () => {
    if (!this.state.connected || this.state.ending || !this.state.accepting) return
    this.update({ ending: true, accepting: false })
    void this.request('/api/end').then(response => {
      if (!response.ok) throw new Error('end unavailable')
      // Authoritative state arrives on the already-connected WebSocket.
    }).catch(() => { if (!this.stopped) this.disconnect() })
  }
  dismissWarning = () => this.update({ warning: '' })
}
