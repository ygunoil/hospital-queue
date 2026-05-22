<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  createReconnectingWs,
  fetchQueue,
  primeSpeechSynthesis,
  speakBilingual,
  unlockDisplayAudio,
  type Patient,
  type QueueState,
} from '@hospital/shared'

const state = ref<QueueState | null>(null)
const highlight = ref(false)
const showOverlay = ref(false)
const overlayPatient = ref<Patient | null>(null)
const now = ref(new Date())
let disposeWs: (() => void) | null = null
let clockTimer: ReturnType<typeof setInterval> | null = null
let overlayTimer: ReturnType<typeof setTimeout> | null = null
let flashTimer: ReturnType<typeof setTimeout> | null = null
let lastAnnouncedId = ''
let lastAnnouncedAt = 0
let skipWatchAnnounce = true

const waitingList = computed(() => state.value?.waiting ?? [])
const waitingCount = computed(() => state.value?.waiting.length ?? 0)
const recentCalled = computed(() => state.value?.recently_called ?? [])

const currentDisplay = computed(() => state.value?.current ?? null)

const clockTime = computed(() =>
  now.value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
)
const clockDate = computed(() =>
  now.value.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }),
)

function clearCallEffects() {
  highlight.value = false
  showOverlay.value = false
  overlayPatient.value = null
  if (flashTimer) clearTimeout(flashTimer)
  if (overlayTimer) clearTimeout(overlayTimer)
}

function runCallEffects(p: Patient) {
  overlayPatient.value = p
  highlight.value = true
  showOverlay.value = true
  if (flashTimer) clearTimeout(flashTimer)
  if (overlayTimer) clearTimeout(overlayTimer)
  // 三遍播报较长，超时兜底关闭特效
  const fallbackMs = 120_000
  flashTimer = setTimeout(clearCallEffects, fallbackMs)
  overlayTimer = setTimeout(clearCallEffects, fallbackMs)
}

function announceCall(p: Patient) {
  const ts = Date.now()
  if (p.id === lastAnnouncedId && ts - lastAnnouncedAt < 800) return
  lastAnnouncedId = p.id
  lastAnnouncedAt = ts
  runCallEffects(p)
  speakBilingual(p.ticket_number, p.name, p.name_en, p.room, clearCallEffects, 3)
}

function handleWs(type: string, payload: Record<string, unknown>) {
  if (payload.state) state.value = payload.state as QueueState
  if (type === 'patient_called' && payload.patient) {
    announceCall(payload.patient as Patient)
  }
}

watch(
  () => state.value?.current?.id ?? null,
  (newId, oldId) => {
    if (skipWatchAnnounce) return
    if (!newId || newId === oldId) return
    const p = state.value?.current
    if (p?.status === 'called') announceCall(p)
  },
)

onMounted(async () => {
  primeSpeechSynthesis()
  unlockDisplayAudio()
  // 部分浏览器仍要求一次交互才能播语音，静默监听首次点击以兜底（无弹窗）
  document.addEventListener('pointerdown', unlockDisplayAudio, { once: true, capture: true })
  state.value = await fetchQueue()
  skipWatchAnnounce = false
  disposeWs = createReconnectingWs(handleWs)
  clockTimer = setInterval(() => { now.value = new Date() }, 1000)
})

onUnmounted(() => {
  disposeWs?.()
  if (clockTimer) clearInterval(clockTimer)
  if (overlayTimer) clearTimeout(overlayTimer)
  if (flashTimer) clearTimeout(flashTimer)
})
</script>

<template>
  <div class="display-root">
  <div
    class="screen"
    :class="{ paused: state?.calling_paused, 'screen-calling': highlight }"
  >
    <div class="bg-grid" aria-hidden="true" />
    <div class="bg-glow" aria-hidden="true" />

    <header class="top">
      <div class="top-left">
        <div class="dept">{{ state?.department ?? '—' }}</div>
        <div class="meta">
          <span class="room">{{ state?.room }}</span>
          <span v-if="state?.doctor_name" class="doctor">{{ state.doctor_name }}</span>
        </div>
      </div>
      <div class="top-right">
        <div class="stat">
          <span class="stat-label">等候</span>
          <span class="stat-num">{{ waitingCount }}</span>
          <span class="stat-unit">人</span>
        </div>
        <div class="clock-block">
          <div class="clock">{{ clockTime }}</div>
          <div class="date">{{ clockDate }}</div>
        </div>
      </div>
    </header>

    <section class="now" :class="{ flash: highlight }">
      <p class="label">
        <span class="pulse-dot" />
        正在呼叫 · Now Calling
      </p>
      <template v-if="currentDisplay">
        <div class="ticket">{{ currentDisplay.ticket_number }}</div>
        <div class="name-row">
          <span class="name-cn">{{ currentDisplay.name }}</span>
          <span class="name-en">{{ currentDisplay.name_en }}</span>
        </div>
        <div class="goto">
          <span class="goto-icon">→</span>
          请至 {{ currentDisplay.room }} 就诊
        </div>
      </template>
      <div v-else class="idle">
        <span class="idle-ring" />
        请留意屏幕与广播
      </div>
    </section>

    <section class="waiting">
      <h2>
        等候队列 · Waiting
        <span class="en">{{ waitingList.length }} 人</span>
      </h2>
      <TransitionGroup name="queue" tag="ul" class="queue-list">
        <li
          v-for="(p, i) in waitingList"
          :key="p.id"
          :class="{ urgent: p.priority === 'urgent' }"
          :style="{ '--delay': `${i * 0.06}s` }"
        >
          <span class="idx">{{ i + 1 }}</span>
          <span class="no">{{ p.ticket_number }}</span>
          <span class="nm">{{ p.name }}</span>
          <span v-if="p.priority === 'urgent'" class="pri">优先</span>
        </li>
      </TransitionGroup>
      <p v-if="waitingList.length === 0" class="empty-queue">暂无等候患者</p>
    </section>

    <div v-if="recentCalled.length" class="recent-wrap">
      <span class="recent-title">最近呼叫</span>
      <div class="recent-track">
        <div class="recent-inner">
          <span v-for="p in recentCalled" :key="p.id" class="chip">
            {{ p.ticket_number }} · {{ p.name }}
          </span>
          <span v-for="p in recentCalled" :key="`dup-${p.id}`" class="chip">
            {{ p.ticket_number }} · {{ p.name }}
          </span>
        </div>
      </div>
    </div>

    <footer v-if="state?.calling_paused" class="banner">
      <span class="banner-icon">⏸</span>
      叫号暂停 · Calling Paused
    </footer>

  </div>

  <Teleport to="body">
    <Transition name="overlay-fade">
      <div
        v-if="showOverlay && overlayPatient"
        class="call-overlay"
        aria-live="assertive"
      >
        <div class="ripple r1" />
        <div class="ripple r2" />
        <p class="overlay-label">请就诊 · Please Proceed</p>
        <div class="overlay-ticket">{{ overlayPatient.ticket_number }}</div>
        <div class="overlay-name">{{ overlayPatient.name }}</div>
        <div class="overlay-room">{{ overlayPatient.room }}</div>
      </div>
    </Transition>
  </Teleport>
  </div>
</template>

<style scoped>
.display-root {
  height: 100%;
}

.screen {
  position: relative;
  height: 100vh;
  max-height: 100vh;
  background: #050d18;
  color: #fff;
  padding: 1.2vh 2.5vw 1vh;
  display: grid;
  grid-template-rows: auto minmax(0, 0.85fr) minmax(0, 1.15fr) auto;
  gap: 1vh;
  overflow: hidden;
  font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
  transition: box-shadow 0.3s;
}

.screen-calling {
  box-shadow: inset 0 0 80px rgba(255, 215, 0, 0.35);
  animation: screen-pulse 1.2s ease-in-out infinite;
}

@keyframes screen-pulse {
  50% { box-shadow: inset 0 0 120px rgba(255, 215, 0, 0.55); }
}

.bg-grid,
.bg-glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.bg-glow {
  background:
    radial-gradient(ellipse 70% 45% at 15% 35%, rgba(0, 180, 255, 0.18), transparent),
    radial-gradient(ellipse 55% 40% at 85% 65%, rgba(255, 215, 0, 0.1), transparent);
  animation: drift 22s ease-in-out infinite alternate;
}

.bg-grid {
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: linear-gradient(180deg, black 0%, black 70%, transparent 100%);
}

@keyframes drift {
  to { transform: translate(2%, 1.5%) scale(1.04); }
}

.top {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 2vw;
  margin-bottom: 0;
  padding-bottom: 0.8vh;
  border-bottom: 1px solid rgba(126, 200, 255, 0.25);
}

.dept {
  font-size: clamp(32px, 3.5vw, 48px);
  font-weight: 800;
  letter-spacing: 0.04em;
}

.meta {
  margin-top: 0.6vh;
  font-size: clamp(22px, 2.2vw, 32px);
  color: #7ec8ff;
  display: flex;
  gap: 1.5vw;
  flex-wrap: wrap;
}

.doctor::before {
  content: '·';
  margin-right: 0.5vw;
  opacity: 0.6;
}

.top-right {
  display: flex;
  align-items: center;
  gap: 2.5vw;
}

.stat {
  display: flex;
  align-items: baseline;
  gap: 0.4em;
  padding: 0.6em 1em;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(126, 200, 255, 0.35);
  border-radius: 12px;
  backdrop-filter: blur(8px);
}

.stat-label { font-size: clamp(18px, 1.8vw, 26px); color: #9ecfff; }
.stat-num {
  font-size: clamp(36px, 4vw, 52px);
  font-weight: 800;
  color: #ffd700;
  font-variant-numeric: tabular-nums;
}
.stat-unit { font-size: clamp(18px, 1.8vw, 26px); color: #9ecfff; }

.clock-block { text-align: right; }
.clock {
  font-size: clamp(36px, 4vw, 56px);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: #e8f4ff;
  letter-spacing: 0.06em;
}
.date {
  font-size: clamp(16px, 1.5vw, 22px);
  color: #6a9ec8;
  margin-top: 0.3vh;
}

.now {
  position: relative;
  z-index: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(12px);
  background: rgba(255, 255, 255, 0.07);
  border-radius: 16px;
  padding: 1.5vh 2vw;
  border: 1px solid rgba(126, 200, 255, 0.35);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
  transition: border-color 0.35s, box-shadow 0.35s, background 0.35s;
}

.now.flash {
  border-color: #ffd700;
  box-shadow:
    0 0 60px rgba(255, 215, 0, 0.55),
    0 0 100px rgba(255, 180, 0, 0.25),
    0 8px 32px rgba(0, 0, 0, 0.4);
  background: rgba(255, 215, 0, 0.15);
  animation: now-flash 0.8s ease-in-out infinite alternate;
}

@keyframes now-flash {
  from { transform: scale(1); }
  to { transform: scale(1.01); }
}

.label {
  font-size: clamp(28px, 3vw, 40px);
  color: #9ecfff;
  margin-bottom: 1vh;
  display: flex;
  align-items: center;
  gap: 16px;
  letter-spacing: 0.08em;
}

.pulse-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #4ade80;
  box-shadow: 0 0 12px #4ade80;
  animation: pulse-dot 1.2s ease-in-out infinite;
}

@keyframes pulse-dot {
  50% { opacity: 0.4; transform: scale(0.85); }
}

.ticket {
  font-size: clamp(64px, 9vw, 120px);
  font-weight: 800;
  color: #ffd700;
  letter-spacing: 0.08em;
  line-height: 1.05;
  font-variant-numeric: tabular-nums;
}

.now.flash .ticket {
  animation: pop 0.65s ease-out, glow 1.6s ease-in-out 0.65s infinite;
}

@keyframes pop {
  0% { transform: scale(0.82); opacity: 0.4; }
  55% { transform: scale(1.1); }
  100% { transform: scale(1); opacity: 1; }
}

@keyframes glow {
  50% { text-shadow: 0 0 48px rgba(255, 215, 0, 0.85), 0 0 80px rgba(255, 180, 0, 0.4); }
}

.name-row { margin-top: 2vh; text-align: center; }
.name-cn {
  font-size: clamp(40px, 5.5vw, 72px);
  font-weight: 700;
  display: block;
}
.name-en {
  font-size: clamp(28px, 3.5vw, 44px);
  color: #b8d4ff;
  display: block;
  margin-top: 0.5vh;
  letter-spacing: 0.02em;
}

.goto {
  font-size: clamp(28px, 3.2vw, 44px);
  margin-top: 1vh;
  color: #7ec8ff;
  display: flex;
  align-items: center;
  gap: 16px;
}

.goto-icon {
  display: inline-flex;
  width: 1.2em;
  height: 1.2em;
  align-items: center;
  justify-content: center;
  background: rgba(126, 200, 255, 0.2);
  border-radius: 50%;
  font-weight: 700;
  animation: nudge 1s ease-in-out infinite;
}

@keyframes nudge {
  50% { transform: translateX(6px); }
}

.idle {
  font-size: clamp(44px, 5vw, 60px);
  color: #6a8aaa;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3vh;
}

.idle-ring {
  width: 80px;
  height: 80px;
  border: 3px solid rgba(126, 200, 255, 0.3);
  border-top-color: #7ec8ff;
  border-radius: 50%;
  animation: spin 2s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.waiting {
  position: relative;
  z-index: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  margin-top: 0;
}

.waiting h2 {
  font-size: clamp(24px, 2.5vw, 36px);
  margin-bottom: 0.8vh;
  flex-shrink: 0;
  color: #9ecfff;
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.waiting .en {
  font-size: 0.65em;
  opacity: 0.75;
  padding: 4px 12px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 6px;
}

.queue-list {
  list-style: none;
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: repeat(5, minmax(0, 1fr));
  gap: 6px 12px;
  align-content: stretch;
}

.queue-list li {
  display: flex;
  align-items: center;
  gap: 0.8vw;
  font-size: clamp(20px, 2vw, 32px);
  padding: 0.4vh 1vw;
  min-height: 0;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  animation: slideIn 0.5s ease backwards;
  animation-delay: var(--delay, 0s);
}

@keyframes slideIn {
  from { opacity: 0; transform: translateX(-20px); }
}

.idx {
  width: 1.4em;
  text-align: center;
  font-weight: 700;
  color: #6a9ec8;
  font-variant-numeric: tabular-nums;
}

.queue-list .no {
  font-weight: 700;
  min-width: 4.5em;
  color: #ffd700;
  font-variant-numeric: tabular-nums;
}

.queue-list .nm {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue-list li.urgent {
  border-left: 5px solid #ff4757;
  background: rgba(255, 71, 87, 0.12);
  box-shadow: 0 0 28px rgba(255, 71, 87, 0.2);
  animation: slideIn 0.5s ease backwards, urgentPulse 2.2s ease-in-out infinite;
  animation-delay: var(--delay, 0s), 0s;
}

@keyframes urgentPulse {
  50% { box-shadow: 0 0 36px rgba(255, 71, 87, 0.35); }
}

.pri {
  margin-left: auto;
  font-size: 0.55em;
  background: linear-gradient(135deg, #ff4757, #c0392b);
  padding: 6px 16px;
  border-radius: 8px;
  font-weight: 700;
  letter-spacing: 0.1em;
}

.empty-queue {
  font-size: clamp(28px, 2.5vw, 36px);
  color: #6a8aaa;
  padding: 2vh 0;
}

.queue-enter-active,
.queue-leave-active {
  transition: all 0.35s ease;
}
.queue-enter-from,
.queue-leave-to {
  opacity: 0;
  transform: translateX(-16px);
}
.queue-move {
  transition: transform 0.35s ease;
}

.recent-wrap {
  position: relative;
  z-index: 1;
  margin-top: 0;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 1.5vw;
  padding: 1vh 0;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.recent-title {
  flex-shrink: 0;
  font-size: clamp(20px, 2vw, 28px);
  color: #6a9ec8;
  white-space: nowrap;
}

.recent-track {
  flex: 1;
  overflow: hidden;
  mask-image: linear-gradient(90deg, transparent, black 8%, black 92%, transparent);
}

.recent-inner {
  display: flex;
  gap: 2vw;
  width: max-content;
  animation: scroll 28s linear infinite;
}

@keyframes scroll {
  to { transform: translateX(-50%); }
}

.chip {
  flex-shrink: 0;
  font-size: clamp(22px, 2.2vw, 30px);
  padding: 8px 20px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(126, 200, 255, 0.25);
  border-radius: 999px;
  color: #b8d4ff;
}

.banner {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 50;
  background: linear-gradient(90deg, #b45309, #d97706, #b45309);
  background-size: 200% 100%;
  animation: banner-shine 3s linear infinite;
  text-align: center;
  font-size: clamp(36px, 4vw, 52px);
  font-weight: 700;
  padding: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  box-shadow: 0 -8px 32px rgba(217, 119, 6, 0.4);
}

@keyframes banner-shine {
  to { background-position: 200% 0; }
}

.banner-icon { font-size: 1.1em; }

.screen.paused::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 40;
  pointer-events: none;
  background: radial-gradient(ellipse at center, transparent 40%, rgba(180, 40, 40, 0.12));
}

.paused .now {
  opacity: 0.55;
  filter: grayscale(0.3);
}

.call-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at center, rgba(12, 40, 80, 0.96), rgba(5, 10, 20, 0.98));
}

.ripple {
  position: absolute;
  width: min(50vmin, 420px);
  height: min(50vmin, 420px);
  border: 3px solid rgba(255, 215, 0, 0.55);
  border-radius: 50%;
  pointer-events: none;
}

.r1 { animation: ripple 1.4s ease-out infinite; }
.r2 { animation: ripple 1.4s ease-out 0.5s infinite; }

@keyframes ripple {
  from { transform: scale(0.25); opacity: 1; }
  to { transform: scale(2.2); opacity: 0; }
}

.overlay-label {
  font-size: clamp(32px, 3.5vw, 48px);
  color: #9ecfff;
  letter-spacing: 0.2em;
  margin-bottom: 3vh;
  z-index: 1;
}

.overlay-ticket {
  font-size: clamp(120px, 18vw, 200px);
  font-weight: 800;
  color: #ffd700;
  letter-spacing: 0.1em;
  line-height: 1;
  z-index: 1;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 60px rgba(255, 215, 0, 0.5);
  animation: pop 0.5s ease-out;
}

.overlay-name {
  font-size: clamp(56px, 8vw, 96px);
  font-weight: 700;
  margin-top: 3vh;
  z-index: 1;
}

.overlay-room {
  font-size: clamp(40px, 4.5vw, 60px);
  color: #7ec8ff;
  margin-top: 2vh;
  z-index: 1;
}

.overlay-fade-enter-active,
.overlay-fade-leave-active {
  transition: opacity 0.45s ease;
}
.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
}
</style>
