import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE } from './conversationClient'

type Phase = 'idle' | 'permission' | 'recording' | 'transcribing'
const errors: Record<string, string> = {
  model_not_configured: '음성 인식 모델이 준비되지 않았어요. 키보드로 입력해 주세요.',
  model_missing: '음성 인식 모델을 찾지 못했어요. 키보드로 입력해 주세요.',
  dependency_missing: '음성 인식 기능을 사용할 수 없어요. 키보드로 입력해 주세요.',
  no_speech: '말소리를 찾지 못했어요. 다시 녹음해 주세요.',
  audio_too_large: '녹음 용량이 너무 커요. 짧게 다시 말해 주세요.',
  audio_too_long: '녹음이 너무 길어요. 짧게 다시 말해 주세요.',
  busy: '서버가 처리 중이에요. 처리가 끝난 뒤 다시 녹음해 주세요.',
  session_ended: '대화가 종료됐어요.',
}
const fallback = '음성을 인식하지 못했어요. 다시 녹음하거나 키보드로 입력해 주세요.'

export function useMicrophone(available: boolean, turnBusy: boolean, onText: (text: string) => void) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [notice, setNotice] = useState('')
  const state = useRef<Phase>('idle')
  const generation = useRef(0)
  const stream = useRef<MediaStream | null>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const request = useRef<AbortController | null>(null)
  const receiveText = useRef(onText)
  receiveText.current = onText
  const transition = useCallback((value: Phase) => { state.current = value; setPhase(value) }, [])
  const release = useCallback(() => {
    clearTimeout(timer.current)
    stream.current?.getTracks().forEach(track => track.stop())
    stream.current = null
  }, [])
  const cancel = useCallback(() => {
    generation.current++
    const current = recorder.current
    recorder.current = null
    if (current) {
      current.ondataavailable = null; current.onstop = null; current.onerror = null
      try { if (current.state !== 'inactive') current.stop() } catch { /* Release tracks below regardless. */ }
    }
    release()
    request.current?.abort(); request.current = null
    transition('idle')
  }, [release, transition])
  useEffect(() => () => cancel(), [cancel])
  useEffect(() => {
    if (!available || (turnBusy && ['permission', 'recording'].includes(state.current))) cancel()
  }, [available, turnBusy, cancel])

  async function start() {
    if (!available || turnBusy || state.current !== 'idle') return
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setNotice('이 브라우저에서 녹음할 수 없어요. 키보드로 입력해 주세요.'); return
    }
    const mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus']
      .find(type => MediaRecorder.isTypeSupported(type))
    if (!mime) { setNotice('지원되는 녹음 형식이 없어요. 키보드로 입력해 주세요.'); return }
    const id = ++generation.current
    setNotice(''); transition('permission')
    try {
      const input = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (id !== generation.current) { input.getTracks().forEach(track => track.stop()); return }
      stream.current = input
      const current = new MediaRecorder(input, { mimeType: mime })
      recorder.current = current
      const chunks: Blob[] = []
      let size = 0
      current.ondataavailable = event => {
        if (id !== generation.current) return
        size += event.data.size
        if (size > 20 * 1024 * 1024) { cancel(); setNotice(errors.audio_too_large); return }
        if (event.data.size) chunks.push(event.data)
      }
      current.onerror = () => { cancel(); setNotice(fallback) }
      current.onstop = async () => {
        release(); recorder.current = null
        if (id !== generation.current) return
        transition('transcribing')
        const controller = new AbortController()
        request.current = controller
        timer.current = setTimeout(() => controller.abort(), 60000)
        try {
          const response = await fetch(`${API_BASE}/api/transcribe`, {
            method: 'POST', body: new Blob(chunks, { type: mime }),
            headers: { 'Content-Type': mime }, signal: controller.signal,
            credentials: 'omit', cache: 'no-store',
          })
          const data: unknown = await response.json()
          if (id !== generation.current) return
          if (typeof data !== 'object' || data === null) throw new Error()
          const result = data as Record<string, unknown>
          if (!response.ok) { setNotice(errors[String(result.error)] || fallback); return }
          if (typeof result.text !== 'string' || !result.text.trim() || result.text.length > 2000) throw new Error()
          receiveText.current(result.text.trim())
          setNotice('인식한 내용을 확인하고 전송해 주세요.')
        } catch { if (id === generation.current) setNotice(fallback) }
        finally {
          if (id === generation.current) { clearTimeout(timer.current); request.current = null; transition('idle') }
        }
      }
      current.start(250)
      transition('recording')
      timer.current = setTimeout(() => { if (current.state === 'recording') current.stop() }, 20000)
    } catch (error) {
      if (id !== generation.current) return
      release(); transition('idle')
      setNotice(error instanceof DOMException && error.name === 'NotAllowedError'
        ? '마이크 권한이 허용되지 않았어요. 키보드는 계속 사용할 수 있어요.' : fallback)
    }
  }
  function stop() { if (recorder.current?.state === 'recording') recorder.current.stop() }
  return { phase, busy: phase !== 'idle', notice, start, stop, cancel }
}
