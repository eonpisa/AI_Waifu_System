// Stage 3: deterministic screen preview. No HTTP, WebSocket, audio or storage.
export type Stage = 'idle' | 'translating_input' | 'generating' | 'translating_subtitle' | 'synthesizing' | 'speaking' | 'ended'
export type Scenario = 'normal' | 'tts_error' | 'vts_error'
export type MockEvent =
  | { type: 'stage'; stage: Stage }
  | { type: 'reply'; japanese: string }
  | { type: 'subtitle'; korean: string }
  | { type: 'warning'; message: string }
  | { type: 'finished' }

export const stageLabels: Record<Stage, string> = {
  idle: '입력 대기', translating_input: '입력 번역 중', generating: '응답 생성 중',
  translating_subtitle: '자막 번역 중', synthesizing: '음성 합성 중',
  speaking: '말하는 중', ended: '대화 종료',
}

export function startMockTurn(scenario: Scenario, emit: (event: MockEvent) => void): () => void {
  const events: [number, MockEvent][] = [
    [450, { type: 'stage', stage: 'generating' }],
    [1200, { type: 'reply', japanese: '話してくれてありがとうございます。今日はどんな一日でしたか？' }],
    [1200, { type: 'stage', stage: 'translating_subtitle' }],
    [1850, { type: 'subtitle', korean: '이야기해 줘서 고마워요. 오늘은 어떤 하루였나요?' }],
    [1850, { type: 'stage', stage: 'synthesizing' }],
  ]
  if (scenario === 'tts_error') {
    events.push([2600, { type: 'warning', message: '음성을 만들지 못했어요. 자막은 볼 수 있고, 다음 이야기도 이어갈 수 있어요. (오류 예시)' }])
  } else {
    events.push([2600, { type: 'stage', stage: 'speaking' }])
    if (scenario === 'vts_error') {
      events.push([2600, { type: 'warning', message: '캐릭터에 연결하지 못했어요. 표정 없이 대화는 계속할 수 있어요. (오류 예시)' }])
    }
  }
  events.push([scenario === 'tts_error' ? 2800 : 4200, { type: 'finished' }])
  const timers = events.map(([delay, event]) => window.setTimeout(() => emit(event), delay))
  return () => timers.forEach(window.clearTimeout)
}
