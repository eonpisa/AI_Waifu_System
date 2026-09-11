import type { CSSProperties } from 'react'

type IconName = 'spark' | 'chat' | 'arrow' | 'mic' | 'stop' | 'chevron' | 'sound' | 'close' | 'info'
const paths: Record<IconName, string> = {
  spark: 'M12 3 14.5 9.5 21 12 14.5 14.5 12 21 9.5 14.5 3 12 9.5 9.5Z',
  chat: 'M20 11.5a8 8 0 0 1-8 8H4l1.3-4A8 8 0 1 1 20 11.5Z',
  arrow: 'M5 12h14m-6-6 6 6-6 6',
  mic: 'M9 5a3 3 0 0 1 6 0v6a3 3 0 0 1-6 0Zm-3 5v1a6 6 0 0 0 12 0v-1m-6 7v4m-3 0h6',
  stop: 'M7 4h10a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Z',
  chevron: 'm9 5 7 7-7 7',
  sound: 'M4 9h4l5-5v16l-5-5H4Zm12-1a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14',
  close: 'm6 6 12 12M6 18 18 6',
  info: 'M12 8h.01M12 11v6m9-5a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
}
export function Icon({ name, className = '' }: { name: IconName; className?: string }) {
  return <svg className={`icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}
export function Wave({ active = false }: { active?: boolean }) {
  return <span className={`wave ${active ? 'wave-active' : ''}`} aria-hidden="true">
    {[9, 16, 24, 14, 29, 20, 11, 23, 16].map((height, index) => <i key={index} style={{ height, '--delay': `${index * -0.13}s` } as CSSProperties} />)}
  </span>
}
