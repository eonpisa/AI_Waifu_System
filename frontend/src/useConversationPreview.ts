import { useEffect, useRef, useState } from 'react'
import { startMockTurn } from './mockConversation'
import type { Scenario, Stage } from './mockConversation'

export type Message = { id: string; role: 'user' | 'assistant'; text: string; japanese?: string }

export function useConversationPreview() {
  const [messages, setMessages] = useState<Message[]>([])
  const [stage, setStage] = useState<Stage>('idle')
  const [subtitle, setSubtitle] = useState('')
  const [warning, setWarning] = useState('')
  const [ending, setEnding] = useState(false)
  const active = useRef(false)
  const ended = useRef(false)
  const finishRequested = useRef(false)
  const turn = useRef(0)
  const cleanup = useRef<(() => void) | undefined>(undefined)

  useEffect(() => () => cleanup.current?.(), [])

  function send(text: string, scenario: Scenario): boolean {
    if (!text.trim() || text.length > 2000 || active.current || ended.current) return false
    active.current = true
    const id = ++turn.current
    setWarning('')
    setSubtitle('')
    setStage('translating_input')
    setMessages(previous => [...previous, { id: `${id}-user`, role: 'user', text: text.trim() }])
    cleanup.current = startMockTurn(scenario, event => {
      if (event.type === 'stage') setStage(event.stage)
      if (event.type === 'warning') setWarning(event.message)
      if (event.type === 'reply') {
        setMessages(previous => [...previous, { id: `${id}-assistant`, role: 'assistant', text: '', japanese: event.japanese }])
      }
      if (event.type === 'subtitle') {
        setSubtitle(event.korean)
        setMessages(previous => previous.map(message => message.id === `${id}-assistant` ? { ...message, text: event.korean } : message))
      }
      if (event.type === 'finished') {
        active.current = false
        ended.current = finishRequested.current
        setStage(ended.current ? 'ended' : 'idle')
        setEnding(false)
        cleanup.current = undefined
      }
    })
    return true
  }

  function end() {
    // Same natural-finish semantics as the single-session Python API.
    finishRequested.current = true
    if (active.current) setEnding(true)
    else { ended.current = true; setStage('ended') }
  }

  function restart() {
    if (active.current) return
    ended.current = false
    finishRequested.current = false
    setMessages([])
    setStage('idle')
    setSubtitle('')
    setWarning('')
    setEnding(false)
  }

  return { messages, stage, subtitle, warning, ending, send, end, restart,
    busy: stage !== 'idle' && stage !== 'ended', dismissWarning: () => setWarning('') }
}
