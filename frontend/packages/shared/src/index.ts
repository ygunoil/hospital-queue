export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
export const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'

export type Patient = {
  id: string
  ticket_number: string
  name: string
  name_en: string
  department: string
  room: string
  status: string
  priority: string
  priority_reason?: string | null
}

export type QueueState = {
  department: string
  room: string
  doctor_name: string
  calling_paused: boolean
  current: Patient | null
  waiting: Patient[]
  recently_called: Patient[]
  demo_patient_id: string
}

export async function fetchQueue(): Promise<QueueState> {
  const res = await fetch(`${API_BASE}/api/queue`)
  if (!res.ok) throw new Error('获取队列失败')
  return res.json()
}

export async function fetchPatient(id: string) {
  const res = await fetch(`${API_BASE}/api/patients/${id}`)
  if (!res.ok) throw new Error('获取患者信息失败')
  return res.json()
}

export type WsHandler = (type: string, payload: Record<string, unknown>) => void

export function createReconnectingWs(onMessage: WsHandler, onState?: (connected: boolean) => void) {
  let ws: WebSocket | null = null
  let retry = 0
  let stopped = false
  let pingTimer: ReturnType<typeof setInterval> | null = null

  const connect = () => {
    if (stopped) return
    ws = new WebSocket(WS_URL)
    ws.onopen = () => {
      retry = 0
      onState?.(true)
      pingTimer = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send('ping'), 25000)
    }
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        onMessage(msg.type, msg.payload || {})
      } catch {
        /* ignore */
      }
    }
    ws.onclose = () => {
      onState?.(false)
      if (pingTimer) clearInterval(pingTimer)
      if (!stopped) {
        const delay = Math.min(1000 * 2 ** retry, 10000)
        retry += 1
        setTimeout(connect, delay)
      }
    }
    ws.onerror = () => ws?.close()
  }

  connect()
  return () => {
    stopped = true
    if (pingTimer) clearInterval(pingTimer)
    ws?.close()
  }
}

export function speakBilingual(
  ticket: string,
  name: string,
  nameEn: string,
  room: string,
  onEnd?: () => void,
) {
  const synth = window.speechSynthesis
  if (!synth) {
    onEnd?.()
    return
  }
  synth.cancel()
  const zh = new SpeechSynthesisUtterance(`请 ${ticket} 号 ${name}，到 ${room} 就诊`)
  zh.lang = 'zh-CN'
  zh.rate = 0.9
  const en = new SpeechSynthesisUtterance(
    `Number ${ticket}, ${nameEn}, please proceed to ${room}`,
  )
  en.lang = 'en-US'
  en.rate = 0.9
  zh.onend = () => setTimeout(() => synth.speak(en), 500)
  en.onend = () => onEnd?.()
  synth.speak(zh)
}
