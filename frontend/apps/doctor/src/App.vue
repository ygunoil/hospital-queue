<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  API_BASE,
  createReconnectingWs,
  fetchQueue,
  type QueueState,
} from '@hospital/shared'

const state = ref<QueueState | null>(null)
const loading = ref(false)
const wsConnected = ref(false)
let disposeWs: (() => void) | null = null

const waitingCount = computed(() => state.value?.waiting.length ?? 0)
const urgentCount = computed(
  () => state.value?.waiting.filter((p) => p.priority === 'urgent').length ?? 0,
)

const tipIndex = ref(0)
let tipTimer: ReturnType<typeof setInterval> | null = null

const DOCTOR_TIPS = [
  '按自己的节奏接诊即可，不必赶时间，大屏与患者端会自动同步。',
  '需要喝水、交班或处理急症时，可随时「暂停叫号」，患者会看到提示。',
  '候诊患者已按优先规则排序，您只需从上到下呼叫。',
  '若当前患者未到场，可使用「跳过当前」，不会打乱整体队列。',
  '今日辛苦了，适当休息几秒再继续，有助于保持专注。',
]

const comfortTitle = computed(() => {
  if (!state.value) return '正在加载工作台…'
  const s = state.value
  if (s.calling_paused) return '叫号已暂停，您可以稍作停顿'
  if (s.current?.status === 'in_consultation') {
    return `正在接诊 ${s.current.name}，完成后即可呼叫下一位`
  }
  if (s.current) return `已呼叫 ${s.current.ticket_number}，等待患者前往诊室`
  if (waitingCount.value === 0) return '当前暂无候诊，可以稍作休息'
  if (waitingCount.value >= 8) return '今日候诊较多，不必着急，按序即可'
  if (urgentCount.value > 0) return `队列中有 ${urgentCount.value} 位优先患者，已排在前面`
  return '一切就绪，按您的节奏呼叫即可'
})

const comfortDesc = computed(() => {
  if (!state.value) return ''
  const s = state.value
  if (s.calling_paused) {
    return '恢复叫号后，大屏与患者手机会同步更新。暂停期间患者被告知「请稍候」，无需您额外说明。'
  }
  if (s.current) {
    return '患者端会收到提醒，候诊大屏也会播报。若患者未及时到达，可跳过再呼叫下一位。'
  }
  if (waitingCount.value === 0) {
    return '新的患者加入队列后，本页与等候人数会自动更新。'
  }
  const estMin = Math.max(waitingCount.value * 8, 8)
  return `目前约 ${waitingCount.value} 人在等候，粗估还需约 ${estMin} 分钟清队（仅供参考）。`
})

const activeTip = computed(() => DOCTOR_TIPS[tipIndex.value % DOCTOR_TIPS.length])

async function refresh() {
  state.value = await fetchQueue()
}

function applyPayload(payload: Record<string, unknown>) {
  if (payload.state) state.value = payload.state as QueueState
}

async function post(path: string) {
  loading.value = true
  try {
    const res = await fetch(`${API_BASE}${path}`, { method: 'POST' })
    const data = await res.json()
    if (data.state) state.value = data.state
    else if (data.called !== undefined) state.value = data.state
    else state.value = data
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await refresh()
  tipTimer = setInterval(() => {
    tipIndex.value = (tipIndex.value + 1) % DOCTOR_TIPS.length
  }, 8000)
  disposeWs = createReconnectingWs((type, payload) => {
    if (type === 'connected') applyPayload(payload)
    if (['patient_called', 'queue_updated', 'calling_paused', 'priority_applied'].includes(type)) {
      applyPayload(payload)
    }
  }, (c) => { wsConnected.value = c })
})

onUnmounted(() => {
  disposeWs?.()
  if (tipTimer) clearInterval(tipTimer)
})
</script>

<template>
  <div class="page">
    <div class="bg-glow" aria-hidden="true" />
    <div class="bg-grid" aria-hidden="true" />

    <header class="header">
      <div class="brand">
        <span class="logo">叫号</span>
        <div class="brand-text">
          <h1>医生控制台</h1>
          <p v-if="state" class="meta">
            {{ state.department }} · {{ state.room }} · {{ state.doctor_name }}
          </p>
        </div>
      </div>
      <div class="header-right">
        <div class="stat-pill">
          <span class="stat-label">等候</span>
          <span class="stat-value">{{ waitingCount }}</span>
        </div>
        <span :class="['status', wsConnected ? 'online' : 'offline']">
          <i class="dot" />
          {{ wsConnected ? '已连接' : '连接中' }}
        </span>
      </div>
    </header>

    <main v-if="state" class="main">
      <section class="panel comfort-panel">
        <div class="comfort-top">
          <span class="comfort-live" aria-hidden="true" />
          <h2 class="comfort-title">{{ comfortTitle }}</h2>
        </div>
        <p class="comfort-desc">{{ comfortDesc }}</p>
        <p class="comfort-tip">
          <span class="tip-icon">i</span>
          <Transition name="tip-fade" mode="out-in">
            <span :key="tipIndex" class="tip-text">{{ activeTip }}</span>
          </Transition>
        </p>
      </section>

      <section
        class="panel current-panel"
        :class="{ paused: state.calling_paused, active: !!state.current }"
      >
        <div class="panel-head">
          <h2>
            <span class="pulse-dot" />
            当前呼叫
          </h2>
          <span v-if="state.calling_paused" class="chip warn">已暂停</span>
        </div>

        <div v-if="state.current" class="patient-hero">
          <div class="ticket">{{ state.current.ticket_number }}</div>
          <div class="info">
            <div class="name">{{ state.current.name }}</div>
            <div v-if="state.current.name_en" class="name-en">{{ state.current.name_en }}</div>
          </div>
          <span v-if="state.current.priority === 'urgent'" class="chip urgent">优先</span>
        </div>
        <div v-else class="empty-hero">
          <span class="idle-ring" />
          <p>暂无正在呼叫的患者</p>
          <span class="hint">准备好后点击「呼叫下一位」，不必连续操作</span>
        </div>
      </section>

      <section class="panel actions-panel">
        <button
          class="btn-call"
          :disabled="loading || state.calling_paused"
          @click="post('/api/queue/call-next')"
        >
          <span class="btn-glow" aria-hidden="true" />
          <span class="btn-title">{{ loading ? '处理中…' : '呼叫下一位' }}</span>
          <span class="btn-sub">按序呼叫 · 无需着急</span>
        </button>
        <button class="btn-secondary" :disabled="loading" @click="post('/api/queue/skip')">
          跳过当前
        </button>
        <button
          class="btn-secondary"
          :class="{ active: state.calling_paused }"
          :disabled="loading"
          @click="post(state.calling_paused ? '/api/queue/resume' : '/api/queue/pause?paused=true')"
        >
          {{ state.calling_paused ? '恢复叫号' : '暂停叫号' }}
        </button>
      </section>

      <section class="panel queue-panel">
        <div class="panel-head">
          <h2>等候队列</h2>
          <span class="count">{{ waitingCount }} 人</span>
        </div>

        <ul v-if="state.waiting.length" class="queue-grid">
          <li
            v-for="(p, i) in state.waiting"
            :key="p.id"
            :class="{ urgent: p.priority === 'urgent' }"
            :style="{ '--i': i }"
          >
            <span class="rank">{{ i + 1 }}</span>
            <span class="ticket-sm">{{ p.ticket_number }}</span>
            <span class="name-sm">{{ p.name }}</span>
            <span v-if="p.priority === 'urgent'" class="chip urgent">优先</span>
            <span v-else class="chip muted">等候</span>
          </li>
        </ul>
        <p v-else class="queue-empty">暂无等候患者</p>
      </section>
    </main>

    <div v-else class="loading-page">
      <span class="idle-ring" />
      加载中…
    </div>
  </div>
</template>

<style scoped>
.page {
  position: relative;
  height: 100%;
  max-width: 1000px;
  margin: 0 auto;
  padding: 14px 18px 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.bg-glow,
.bg-grid {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.bg-glow {
  background:
    radial-gradient(ellipse 55% 40% at 8% 15%, rgba(30, 111, 217, 0.08), transparent),
    radial-gradient(ellipse 45% 35% at 92% 85%, rgba(255, 200, 50, 0.06), transparent);
  animation: drift 24s ease-in-out infinite alternate;
}

.bg-grid {
  background-image:
    linear-gradient(rgba(15, 23, 42, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.04) 1px, transparent 1px);
  background-size: 40px 40px;
  mask-image: radial-gradient(ellipse 85% 75% at center, black 30%, transparent);
}

@keyframes drift {
  to { transform: translate(2%, 1%) scale(1.03); }
}

.header,
.main,
.loading-page {
  position: relative;
  z-index: 1;
}

/* —— 顶栏 —— */
.header {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e2e8f0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.logo {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, #1e8cff, #0d4a9e);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.05em;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 14px rgba(30, 111, 217, 0.28);
}

.header h1 {
  font-size: 1.2rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: 0.04em;
}

.meta {
  margin-top: 2px;
  font-size: 0.8rem;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.stat-pill {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 6px 14px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}

.stat-label { font-size: 0.75rem; color: #64748b; }
.stat-value {
  font-size: 1.2rem;
  font-weight: 700;
  color: #1e6fd9;
  font-variant-numeric: tabular-nums;
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  padding: 5px 11px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.status.online {
  background: #ecfdf5;
  color: #047857;
  border-color: #a7f3d0;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.status.online .dot {
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
  animation: pulse-dot 1.2s ease-in-out infinite;
}

@keyframes pulse-dot {
  50% { opacity: 0.45; transform: scale(0.85); }
}

/* —— 主区域 —— */
.main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.comfort-panel {
  flex-shrink: 0;
  padding: 12px 14px;
  background: linear-gradient(135deg, #eff6ff 0%, #fff 60%);
  border-color: #bfdbfe;
}

.comfort-top {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.comfort-live {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  margin-top: 5px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.45);
  animation: live-pulse 2s ease-out infinite;
}

@keyframes live-pulse {
  0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.45); }
  70% { box-shadow: 0 0 0 8px rgba(34, 197, 94, 0); }
  100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
}

.comfort-title {
  flex: 1;
  font-size: 0.92rem;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.4;
}

.comfort-desc {
  margin-top: 6px;
  font-size: 0.78rem;
  color: #475569;
  line-height: 1.45;
}

.comfort-tip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #dbeafe;
  font-size: 0.74rem;
  color: #64748b;
  line-height: 1.45;
}

.comfort-panel .tip-icon {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #e0f2fe;
  color: #1e6fd9;
  font-size: 0.65rem;
  font-weight: 700;
  font-style: normal;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
}

.comfort-panel .tip-text {
  flex: 1;
  min-width: 0;
}

.tip-fade-enter-active,
.tip-fade-leave-active {
  transition: opacity 0.35s ease;
}
.tip-fade-enter-from,
.tip-fade-leave-to {
  opacity: 0;
}

.panel {
  background: #fff;
  border-radius: 16px;
  border: 1px solid #e8eef4;
  box-shadow: 0 4px 24px rgba(15, 23, 42, 0.06);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.panel-head h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  font-weight: 600;
  color: #64748b;
  letter-spacing: 0.08em;
}

.panel-head .pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.45);
  animation: pulse-dot 1.2s ease-in-out infinite;
}

.count {
  font-size: 0.78rem;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}

/* 当前呼叫 */
.current-panel {
  flex-shrink: 0;
  padding: 12px 16px;
  transition: border-color 0.3s, box-shadow 0.3s;
}

.current-panel.active {
  border-color: #fcd34d;
  box-shadow:
    0 0 0 1px rgba(252, 211, 77, 0.5),
    0 8px 28px rgba(255, 193, 7, 0.15);
}

.current-panel.paused {
  border-color: #fcd34d;
  background: linear-gradient(180deg, #fffbeb 0%, #fff 50%);
}

.patient-hero {
  display: flex;
  align-items: center;
  gap: 16px;
}

.ticket {
  font-size: clamp(1.8rem, 4.5vh, 2.6rem);
  font-weight: 800;
  color: #d97706;
  letter-spacing: 0.08em;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.info { flex: 1; min-width: 0; }

.name {
  font-size: clamp(1rem, 2.5vh, 1.4rem);
  font-weight: 700;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.name-en {
  margin-top: 2px;
  font-size: 0.8rem;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 0 2px;
  gap: 6px;
}

.empty-hero p { font-size: 0.95rem; color: #64748b; }
.hint { font-size: 0.75rem; color: #94a3b8; }

.idle-ring {
  width: 36px;
  height: 36px;
  border: 2px solid #e2e8f0;
  border-top-color: #1e6fd9;
  border-radius: 50%;
  animation: spin 1.5s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 操作按钮 */
.actions-panel {
  flex-shrink: 0;
  padding: 8px 12px;
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 10px;
  align-items: stretch;
}

.btn-call {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  padding: 12px 14px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #1e8cff 0%, #1e6fd9 50%, #1558b8 100%);
  color: #fff;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  box-shadow: 0 6px 22px rgba(30, 111, 217, 0.35);
}

.btn-glow {
  position: absolute;
  inset: -50%;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.35), transparent 55%);
  animation: btn-shine 3s ease-in-out infinite;
}

@keyframes btn-shine {
  0%, 100% { transform: translate(-20%, -20%); opacity: 0.4; }
  50% { transform: translate(20%, 20%); opacity: 0.8; }
}

.btn-call:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 10px 28px rgba(30, 111, 217, 0.45);
}

.btn-call:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none;
  filter: grayscale(0.4);
}

.btn-title {
  position: relative;
  z-index: 1;
  font-size: 1.02rem;
  font-weight: 800;
  letter-spacing: 0.06em;
}

.btn-sub {
  position: relative;
  z-index: 1;
  font-size: 0.65rem;
  opacity: 0.75;
  letter-spacing: 0.12em;
}

.btn-secondary {
  padding: 12px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #f8fafc;
  color: #334155;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.btn-secondary:hover:not(:disabled) {
  background: #f1f5f9;
  border-color: #cbd5e1;
}

.btn-secondary.active {
  background: #fffbeb;
  border-color: #fcd34d;
  color: #92400e;
}

.btn-secondary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.chip {
  flex-shrink: 0;
  font-size: 0.65rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 6px;
  letter-spacing: 0.04em;
}

.chip.urgent {
  background: #fef2f2;
  color: #dc2626;
  border: 1px solid #fecaca;
}

.chip.warn {
  background: #fffbeb;
  color: #b45309;
  border: 1px solid #fde68a;
}

.chip.muted {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

/* 等候队列 */
.queue-panel {
  flex: 1;
  min-height: 0;
  padding: 8px 12px 10px;
  display: flex;
  flex-direction: column;
}

.queue-grid {
  list-style: none;
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: repeat(5, minmax(0, 1fr));
  gap: 6px;
  overflow: hidden;
}

.queue-grid li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  min-height: 0;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #eef2f6;
  animation: fade-in 0.4s ease backwards;
  animation-delay: calc(var(--i, 0) * 0.04s);
  transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(6px); }
}

.queue-grid li:hover {
  background: #f1f5f9;
  border-color: #dbeafe;
  box-shadow: 0 2px 8px rgba(30, 111, 217, 0.08);
}

.queue-grid li.urgent {
  background: #fff5f5;
  border-color: #fecaca;
  box-shadow: 0 2px 10px rgba(220, 38, 38, 0.08);
}

.rank {
  width: 1.4em;
  text-align: center;
  font-size: 0.72rem;
  font-weight: 600;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}

.ticket-sm {
  min-width: 3.2em;
  font-size: 0.82rem;
  font-weight: 700;
  color: #1e6fd9;
  font-variant-numeric: tabular-nums;
}

.name-sm {
  flex: 1;
  min-width: 0;
  font-size: 0.82rem;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 0.88rem;
}

.loading-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #64748b;
}
</style>
