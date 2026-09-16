// Last observed operations, never a promise that a server is still running.
export const serviceNames = ['ollama', 'gemini', 'sbv2', 'vts'] as const
export type ServiceName = typeof serviceNames[number]
export type Observation = { state: 'unknown' | 'ok' | 'warning' | 'error'; code: string; turn_id: number | null }
export type Services = Record<ServiceName, Observation>
export type SubtitleProvider = { provider: 'gemini' | 'qwen' | 'none'; model: string; fallback_reason: string; turn_id: number | null }
const codes: Record<ServiceName, Record<string, [Observation['state'], string, string]>> = {
  ollama: { response_received: ['ok', '응답 확인', '응답 수신 확인 · 내용 품질 판정과 별개'], request_failed: ['error', '요청 실패', '대화·번역 서버 요청 실패'] },
  gemini: { subtitle_accepted: ['ok', '자막 채택', '검증된 한국어 자막 사용'], api_key_missing: ['error', '키 미설정', 'API 서버의 환경변수 설정 필요'], translation_failed: ['error', '번역 실패', 'Gemini 자막을 채택하지 못함'] },
  sbv2: { synthesis_succeeded: ['ok', '합성 성공', '음성 파일 생성 성공 · 청취 판정과 별개'], synthesis_failed: ['error', '합성 실패', '음성 파일을 생성하지 못함'] },
  vts: {
    parameters_applied: ['ok', '제어 응답', '인증·표정 파라미터 응답 확인'],
    model_not_calibrated: ['warning', '일부 제한', '표정 적용 · 모델 립싱크 보정 필요'],
    mouth_reset_failed: ['warning', '복원 실패', '입 닫기 응답을 확인하지 못함'],
    authentication_failed: ['error', '인증 실패', 'VTube Studio 플러그인 인증 필요'],
    parameter_rejected: ['error', '적용 실패', '표정 파라미터 적용 거절'],
    timeout: ['error', '응답 지연', 'VTube Studio 요청 시간 초과'],
    connection_failed: ['error', '연결 실패', 'VTube Studio 연결 확인 필요'],
    response_error: ['error', '응답 오류', 'VTube Studio 응답 확인 실패'],
    stop_event_required: ['error', '제어 실패', '표정 작업 시작 실패'],
    worker_error: ['error', '제어 실패', '표정 작업 오류'],
    worker_start_failed: ['error', '시작 실패', '표정 작업 시작 실패'],
  },
}
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function turn(value: unknown) { return Number.isSafeInteger(value) && (value as number) > 0 ? value as number : null }
export function unknownServices(): Services {
  return Object.fromEntries(serviceNames.map(name => [name, { state: 'unknown', code: 'not_checked', turn_id: null }])) as Services
}
export function readObservation(name: ServiceName, value: unknown): Observation {
  if (!object(value)) return { state: 'unknown', code: 'not_checked', turn_id: null }
  const code = typeof value.code === 'string' ? value.code : ''
  const entry = Object.hasOwn(codes[name], code) ? codes[name][code] : undefined
  return { state: entry?.[0] || 'unknown', code: entry ? code : 'not_checked', turn_id: turn(value.turn_id) }
}
export function readServices(value: unknown): Services {
  return Object.fromEntries(serviceNames.map(name => [name, readObservation(name, object(value) ? value[name] : null)])) as Services
}
export function observationLabel(name: ServiceName, value: Observation) {
  return codes[name][value.code]?.[1] || '미확인'
}
export function observationDetail(name: ServiceName, value: Observation) {
  return codes[name][value.code]?.[2] || '아직 요청 결과 없음'
}
const reasons = new Set(['none', 'translation_failed', 'gemini_api_key_missing', 'gemini_request_timeout',
  'gemini_request_error', 'gemini_response_error', 'gemini_json_parse_error'])
const validations = ['empty_translation', 'japanese_character', 'hanja_or_chinese_character', 'english_word',
  'chinese_punctuation', 'annotation_or_markdown', 'missing_korean_text', 'missing_required_term',
  'incomplete_translation', 'request_timeout', 'request_error', 'json_parse_error']
validations.forEach(code => { reasons.add(code); reasons.add(`qwen_${code}`) })
export function readSubtitleProvider(value: unknown): SubtitleProvider | null {
  if (!object(value) || !['gemini', 'qwen', 'none'].includes(String(value.provider))) return null
  const provider = value.provider as SubtitleProvider['provider']
  const pattern = provider === 'gemini' ? /^gemini-[A-Za-z0-9._:-]{1,70}$/ : /^qwen[A-Za-z0-9._:-]{1,70}$/
  const model = typeof value.model === 'string' && pattern.test(value.model) ? value.model : 'custom'
  const parts = typeof value.fallback_reason === 'string' ? value.fallback_reason.split(';') : []
  const reason = parts.length > 0 && parts.length <= 2 && parts.every(code => reasons.has(code) || /^gemini_http_[1-5][0-9]{2}$/.test(code))
    ? parts.join(';') : 'translation_failed'
  return { provider, model: provider === 'none' ? 'none' : model, fallback_reason: reason, turn_id: turn(value.turn_id) }
}
export function fallbackLabel(reason: string) {
  if (reason === 'none') return '폴백 없음'
  if (reason.startsWith('gemini_api_key_missing')) return 'Gemini 키 미설정'
  if (reason.startsWith('gemini_request_timeout')) return 'Gemini 응답 시간 초과'
  if (/^gemini_http_(401|403)(;|$)/.test(reason)) return 'Gemini 인증·권한 오류'
  if (reason.startsWith('gemini_http_429')) return 'Gemini 사용 한도 도달'
  if (reason.startsWith('gemini_http_')) return 'Gemini 서버 요청 실패'
  if (reason.startsWith('gemini_request_error')) return 'Gemini 연결 실패'
  return '번역 응답 검증 실패'
}
