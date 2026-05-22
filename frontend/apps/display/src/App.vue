<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  createReconnectingWs,
  fetchQueue,
  speakBilingual,
  type Patient,
  type QueueState,
} from '@hospital/shared'

const state = ref<QueueState | null>(null)
const highlight = ref(false)
const lastCalledId = ref<string | null>(null)
let disposeWs: (() => void) | null = null

const topFive = computed(() => state.value?.waiting.slice(0, 5) ?? [])

const currentDisplay = computed(() => {
  const c = state.value?.current
  if (!c) return null
  return c
})

function triggerCallTts(p: Patient) {
  speakBilingual(p.ticket_number, p.name, p.name_en, p.room)
  highlight.value = true
  setTimeout(() => { highlight.value = false }, 4000)
}

function handleWs(type: string, payload: Record<string, unknown>) {
  if (payload.state) state.value = payload.state as QueueState
  if (type === 'patient_called' && payload.patient) {
    const p = payload.patient as Patient
    if (p.id !== lastCalledId.value) {
      lastCalledId.value = p.id
      triggerCallTts(p)
    }
  }
}

onMounted(async () => {
  state.value = await fetchQueue()
  disposeWs = createReconnectingWs(handleWs)
})

onUnmounted(() => disposeWs?.())
</script>

<template>
  <div class="screen" :class="{ paused: state?.calling_paused }">
    <header class="top">
      <div class="dept">{{ state?.department }}</div>
      <div class="room">{{ state?.room }}</div>
      <div class="clock">{{ new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</div>
    </header>

    <section class="now" :class="{ flash: highlight }">
      <p class="label">正在呼叫 · Now Calling</p>
      <template v-if="currentDisplay">
        <div class="ticket">{{ currentDisplay.ticket_number }}</div>
        <div class="name-row">
          <span class="name-cn">{{ currentDisplay.name }}</span>
          <span class="name-en">{{ currentDisplay.name_en }}</span>
        </div>
        <div class="goto">请至 {{ currentDisplay.room }} 就诊</div>
      </template>
      <div v-else class="idle">请留意屏幕与广播</div>
    </section>

    <section class="waiting">
      <h2>等候队列 · Waiting <span class="en">(Top 5)</span></h2>
      <ul>
        <li v-for="(p, i) in topFive" :key="p.id" :class="{ urgent: p.priority === 'urgent' }">
          <span class="idx">{{ i + 1 }}</span>
          <span class="no">{{ p.ticket_number }}</span>
          <span class="nm">{{ p.name }}</span>
          <span v-if="p.priority === 'urgent'" class="pri">优先</span>
        </li>
      </ul>
    </section>

    <footer v-if="state?.calling_paused" class="banner">叫号暂停 · Calling Paused</footer>
  </div>
</template>

<style scoped>
.screen {
  min-height: 100vh;
  background: linear-gradient(180deg, #0a1628 0%, #122a4a 100%);
  color: #fff;
  padding: 2vh 3vw;
  display: flex;
  flex-direction: column;
}
.top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: clamp(28px, 3vw, 40px);
  opacity: 0.9;
  margin-bottom: 2vh;
}
.dept { font-weight: 700; }
.room { color: #7ec8ff; }
.now {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(255,255,255,.06);
  border-radius: 16px;
  padding: 4vh;
  border: 4px solid transparent;
  transition: border-color 0.3s, box-shadow 0.3s;
}
.now.flash {
  border-color: #ffd700;
  box-shadow: 0 0 40px rgba(255, 215, 0, 0.5);
  background: rgba(255, 215, 0, 0.12);
}
.label { font-size: 48px; color: #9ecfff; margin-bottom: 2vh; }
.ticket {
  font-size: clamp(96px, 14vw, 160px);
  font-weight: 800;
  color: #ffd700;
  letter-spacing: 0.05em;
  line-height: 1.1;
}
.name-row { margin-top: 2vh; text-align: center; }
.name-cn { font-size: clamp(56px, 8vw, 88px); font-weight: 700; display: block; }
.name-en { font-size: clamp(40px, 5vw, 56px); color: #b8d4ff; display: block; margin-top: 1vh; }
.goto { font-size: 52px; margin-top: 3vh; color: #7ec8ff; }
.idle { font-size: 56px; color: #6a8aaa; }
.waiting { margin-top: 3vh; }
.waiting h2 { font-size: 40px; margin-bottom: 2vh; color: #9ecfff; }
.waiting .en { font-size: 32px; opacity: 0.8; }
.waiting ul { list-style: none; }
.waiting li {
  display: flex;
  align-items: center;
  gap: 2vw;
  font-size: 48px;
  padding: 1.2vh 0;
  border-bottom: 1px solid rgba(255,255,255,.15);
}
.waiting .no { font-weight: 700; min-width: 120px; color: #ffd700; }
.waiting .urgent { color: #ff8a8a; }
.pri { font-size: 32px; background: #dc3545; padding: 4px 12px; border-radius: 6px; }
.banner {
  position: fixed; bottom: 0; left: 0; right: 0;
  background: #856404; text-align: center;
  font-size: 48px; padding: 16px;
}
.paused .now { opacity: 0.6; }
</style>
