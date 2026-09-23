import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useMicrophone } from './useMicrophone'

class Recorder {
  static isTypeSupported = () => true
  static current: Recorder
  state = 'inactive'
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor() { Recorder.current = this }
  start() { this.state = 'recording' }
  stop() {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['recording']) })
    this.onstop?.()
  }
}
let track: { stop: ReturnType<typeof vi.fn> }
beforeEach(() => {
  track = { stop: vi.fn() }
  vi.stubGlobal('MediaRecorder', Recorder)
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
    getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }),
  } })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ text: '오늘 학교에서 시험을 봤어.' }) }))
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('records only on request, releases the mic, and returns a draft without calling the turn endpoint', async () => {
  const onText = vi.fn()
  const { result } = renderHook(() => useMicrophone(true, false, onText))
  expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled()
  await act(async () => { await result.current.start() })
  expect(result.current.phase).toBe('recording')
  await act(async () => { result.current.stop() })
  expect(track.stop).toHaveBeenCalled()
  expect(onText).toHaveBeenCalledWith('오늘 학교에서 시험을 봤어.')
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/api/transcribe', expect.objectContaining({ method: 'POST', credentials: 'omit' }))
  expect(result.current.phase).toBe('idle')
})

it('keeps keyboard use available after denied permission and hides raw errors', async () => {
  vi.mocked(navigator.mediaDevices.getUserMedia).mockRejectedValue(new DOMException('PRIVATE', 'NotAllowedError'))
  const { result } = renderHook(() => useMicrophone(true, false, vi.fn()))
  await act(async () => { await result.current.start() })
  expect(result.current.busy).toBe(false)
  expect(result.current.notice).toContain('마이크 권한')
  expect(result.current.notice).not.toContain('PRIVATE')
  expect(fetch).not.toHaveBeenCalled()
})

it('cancels recording without uploading, and cleans up on disconnect', async () => {
  const { result, rerender } = renderHook(({ connected }) => useMicrophone(connected, false, vi.fn()), { initialProps: { connected: true } })
  await act(async () => { await result.current.start() })
  rerender({ connected: false })
  expect(track.stop).toHaveBeenCalled()
  expect(result.current.busy).toBe(false)
  expect(fetch).not.toHaveBeenCalled()
})

it('stops a late permission result after cancellation', async () => {
  let resolve!: (value: MediaStream) => void
  vi.mocked(navigator.mediaDevices.getUserMedia).mockReturnValue(new Promise(done => { resolve = done }))
  const { result } = renderHook(() => useMicrophone(true, false, vi.fn()))
  act(() => { void result.current.start() })
  act(() => result.current.cancel())
  await act(async () => resolve({ getTracks: () => [track] } as unknown as MediaStream))
  expect(track.stop).toHaveBeenCalled()
  expect(result.current.busy).toBe(false)
  expect(fetch).not.toHaveBeenCalled()
})

it('automatically stops at 20 seconds and rejects duplicate starts', async () => {
  vi.useFakeTimers()
  const { result } = renderHook(() => useMicrophone(true, false, vi.fn()))
  await act(async () => { await result.current.start(); await result.current.start() })
  expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(1)
  await act(async () => { await vi.advanceTimersByTimeAsync(20000) })
  expect(track.stop).toHaveBeenCalled()
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('handles model absence without adopting text or showing server diagnostics', async () => {
  vi.mocked(fetch).mockResolvedValue({ ok: false, json: async () => ({ error: 'model_not_configured', detail: 'PRIVATE' }) } as Response)
  const onText = vi.fn()
  const { result } = renderHook(() => useMicrophone(true, false, onText))
  await act(async () => { await result.current.start(); result.current.stop() })
  await waitFor(() => expect(result.current.busy).toBe(false))
  expect(onText).not.toHaveBeenCalled()
  expect(result.current.notice).toContain('모델이 준비되지')
  expect(result.current.notice).not.toContain('PRIVATE')
})

it('prevents recording while a conversation is running', async () => {
  const { result } = renderHook(() => useMicrophone(true, true, vi.fn()))
  await act(async () => { await result.current.start() })
  expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled()
})

it('aborts upload on unmount and never adopts its late result', async () => {
  let resolve!: (response: Response) => void
  vi.mocked(fetch).mockReturnValue(new Promise(done => { resolve = done }))
  const onText = vi.fn()
  const { result, unmount } = renderHook(() => useMicrophone(true, false, onText))
  await act(async () => { await result.current.start(); result.current.stop() })
  const options = vi.mocked(fetch).mock.calls[0][1]!
  unmount()
  expect(options.signal?.aborted).toBe(true)
  await act(async () => resolve({ ok: true, json: async () => ({ text: '늦은 결과' }) } as Response))
  expect(onText).not.toHaveBeenCalled()
})
