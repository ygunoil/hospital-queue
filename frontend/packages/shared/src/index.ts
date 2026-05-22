function devWsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/ws`
}

/** 开发模式走 Vite 代理（同源 /api、/ws），避免 8000 被其他程序占用 */
export const API_BASE =
  import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? '' : 'http://localhost:8000')

export const WS_URL =
  import.meta.env.VITE_WS_URL ?? (import.meta.env.DEV ? devWsUrl() : 'ws://localhost:8000/ws')

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

let voicesReady = false

function pickVoice(langPrefix: string): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis?.getVoices() ?? []
  return (
    voices.find((v) => v.lang.replace('_', '-').startsWith(langPrefix))
    ?? voices.find((v) => v.lang.startsWith(langPrefix.split('-')[0]))
  )
}

/** 预加载 TTS 音色（Chrome 需异步加载 voices） */
export function primeSpeechSynthesis(): void {
  const synth = window.speechSynthesis
  if (!synth) return
  const load = () => {
    if (synth.getVoices().length > 0) voicesReady = true
  }
  load()
  synth.onvoiceschanged = load
}

/** 短促提示音（需先 unlockDisplayAudio） */
export function playCallChime(): void {
  try {
    const ctx = getAudioContext()
    if (!ctx) return
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.frequency.value = 880
    osc.type = 'sine'
    gain.gain.setValueAtTime(0.22, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35)
    osc.start(ctx.currentTime)
    osc.stop(ctx.currentTime + 0.35)
  } catch {
    /* ignore */
  }
}

let audioCtx: AudioContext | null = null

function getAudioContext(): AudioContext | null {
  if (!audioCtx) {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!Ctx) return null
    audioCtx = new Ctx()
  }
  if (audioCtx.state === 'suspended') void audioCtx.resume()
  return audioCtx
}

/** 用户点击大屏后解锁语音与提示音（绕过浏览器自动播放限制） */
export function unlockDisplayAudio(): void {
  primeSpeechSynthesis()
  const ctx = getAudioContext()
  if (ctx?.state === 'suspended') void ctx.resume()
  const synth = window.speechSynthesis
  if (synth) {
    const u = new SpeechSynthesisUtterance(' ')
    u.volume = 0
    synth.speak(u)
    synth.cancel()
  }
}

export function speakBilingual(
  ticket: string,
  name: string,
  nameEn: string,
  room: string,
  onEnd?: () => void,
  repeat = 3,
) {
  const synth = window.speechSynthesis
  if (!synth) {
    onEnd?.()
    return
  }
  playCallChime()
  synth.cancel()

  const rounds = Math.max(1, repeat)
  let done = 0

  const speakOnce = () => {
    const zh = new SpeechSynthesisUtterance(`请 ${ticket} 号 ${name}，到 ${room} 就诊`)
    zh.lang = 'zh-CN'
    zh.rate = 0.9
    zh.volume = 1
    const zhVoice = pickVoice('zh')
    if (zhVoice) zh.voice = zhVoice

    const en = new SpeechSynthesisUtterance(
      `Number ${ticket}, ${nameEn}, please proceed to ${room}`,
    )
    en.lang = 'en-US'
    en.rate = 0.9
    en.volume = 1
    const enVoice = pickVoice('en')
    if (enVoice) en.voice = enVoice

    zh.onend = () => setTimeout(() => synth.speak(en), 500)
    en.onend = () => {
      done += 1
      if (done < rounds) {
        setTimeout(speakOnce, 700)
      } else {
        onEnd?.()
      }
    }
    synth.speak(zh)
  }

  const start = () => speakOnce()

  if (!voicesReady && synth.getVoices().length === 0) {
    synth.onvoiceschanged = () => {
      voicesReady = true
      start()
    }
    setTimeout(start, 120)
  } else {
    start()
  }
}
