<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  API_BASE,
  createReconnectingWs,
  fetchPatient,
  type Patient,
  type QueueState,
} from '@hospital/shared'

const DEMO_ID = 'p005'
const info = ref<{
  patient: Patient
  ahead_count: number
  estimated_wait_minutes: number
  position: number
  state: QueueState
} | null>(null)
const calledAlert = ref(false)
const showPriority = ref(false)
const reason = ref('')
const priorityResult = ref<{
  approved?: boolean
  assessment?: { summary_zh?: string }
} | null>(null)

const assessmentSummary = computed(() => priorityResult.value?.assessment?.summary_zh ?? '')
const resultApproved = computed(() => !!priorityResult.value?.approved)
const resultStatusText = computed(() =>
  resultApproved.value ? '已通过' : '未自动通过',
)
const submitting = ref(false)
const tipIndex = ref(0)
let disposeWs: (() => void) | null = null
let tipTimer: ReturnType<typeof setInterval> | null = null

const COMFORT_TIPS = [
  '候诊期间可在附近休息，不必一直盯着屏幕。',
  '听到叫号或收到本页提醒后，再前往诊室即可。',
  '预估时间仅供参考，医生会尽量按序接诊。',
  '如有不适加重，请点击下方「申请紧急优先」或联系分诊台。',
  '请提前准备好证件、既往检查单，轮到您时更从容。',
]

const statusBadge = computed(() => {
  if (!info.value) return '候诊中'
  if (info.value.state.calling_paused) return '叫号暂停'
  const s = info.value.patient.status
  if (s === 'called') return '已叫号'
  if (s === 'in_consultation') return '就诊中'
  return '候诊中'
})

const comfortTitle = computed(() => {
  if (!info.value) return '正在为您查询候诊信息…'
  const { patient, ahead_count, estimated_wait_minutes, state } = info.value
  if (state.calling_paused) {
    return '叫号暂时暂停，请您稍候'
  }
  if (patient.status === 'called') {
    return '已经叫到您了，请尽快前往诊室'
  }
  if (patient.status === 'in_consultation') {
    return '您正在就诊中，请配合医生'
  }
  if (ahead_count === 0) {
    return '马上就要轮到您了'
  }
  if (ahead_count <= 2) {
    return '很快就要轮到您，请做好准备'
  }
  if (estimated_wait_minutes <= 15) {
    return '预计不久后将叫到您，请放松心情'
  }
  if (estimated_wait_minutes > 30) {
    return '当前候诊人数较多，感谢您的耐心'
  }
  return '您已在队列中，请安心等候'
})

const comfortDesc = computed(() => {
  if (!info.value) return ''
  const { patient, ahead_count, estimated_wait_minutes, state } = info.value
  if (state.calling_paused) {
    return '医生可能正在处理急症或临时事务，恢复叫号后大屏与本页会同步更新，无需重新取号。'
  }
  if (patient.status === 'called') {
    return `请携带好随身物品，前往 ${patient.room}。若未及时到达，可联系分诊台说明情况。`
  }
  if (patient.status === 'in_consultation') {
    return '叫号大屏将显示您的就诊状态，家属可在候诊区等候。'
  }
  if (ahead_count === 0) {
    return '请留意候诊大屏与手机震动提醒，准备好就诊材料，避免过号。'
  }
  const waitHint =
    estimated_wait_minutes > 0
      ? `大约还需 ${estimated_wait_minutes} 分钟（估算值，实际以现场为准）。`
      : ''
  return `您前面还有 ${ahead_count} 位患者，${waitHint}请在候诊区休息，我们会按顺序叫号。`
})

const queueProgress = computed(() => {
  if (!info.value) return 0
  const total = info.value.state.waiting.length
  if (total <= 0) return 100
  const ahead = info.value.ahead_count
  return Math.min(100, Math.max(8, Math.round(((total - ahead) / total) * 100)))
})

const showQueueProgress = computed(() => {
  if (!info.value) return false
  const { patient, state } = info.value
  return (
    !state.calling_paused
    && patient.status === 'waiting'
    && info.value.state.waiting.length > 0
  )
})

const activeTip = computed(() => COMFORT_TIPS[tipIndex.value % COMFORT_TIPS.length])

const waitEstimateLabel = computed(() => {
  if (!info.value) return ''
  const m = info.value.estimated_wait_minutes
  if (m <= 0) return '即将轮到'
  if (m < 60) return `约 ${m} 分钟`
  return `约 ${Math.round(m / 60)} 小时`
})

async function refresh() {
  info.value = await fetchPatient(DEMO_ID)
}

function onCalled(p: Patient) {
  if (p.id !== DEMO_ID) return
  calledAlert.value = true
  if (navigator.vibrate) navigator.vibrate([200, 100, 200, 100, 400])
}

async function submitPriority() {
  if (!reason.value.trim()) return
  submitting.value = true
  try {
    const res = await fetch(`${API_BASE}/api/priority/request`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_id: DEMO_ID, reason: reason.value.trim() }),
    })
    priorityResult.value = await res.json()
    showPriority.value = false
    reason.value = ''
    await refresh()
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await refresh()
  tipTimer = setInterval(() => {
    tipIndex.value = (tipIndex.value + 1) % COMFORT_TIPS.length
  }, 7000)
  disposeWs = createReconnectingWs((type, payload) => {
    if (payload.state && info.value) {
      info.value.state = payload.state as QueueState
    }
    if (type === 'patient_called' && payload.patient) {
      onCalled(payload.patient as Patient)
    }
    if (['patient_called', 'queue_updated', 'calling_paused', 'priority_applied'].includes(type)) {
      refresh()
    }
  })
})

onUnmounted(() => {
  disposeWs?.()
  if (tipTimer) clearInterval(tipTimer)
})
</script>

<template>
  <div class="page">
    <header class="header">
      <div class="header-badge" :class="{ warn: info?.state.calling_paused }">
        {{ statusBadge }}
      </div>
      <h1>我的候诊</h1>
      <p v-if="info" class="meta">
        {{ info.state.department }} · {{ info.patient.room }}
      </p>
    </header>

    <template v-if="info">
      <section v-if="info.state.calling_paused" class="banner-paused">
        <span class="banner-dot" />
        叫号暂停中，请稍候，恢复后将继续按序叫号
      </section>

      <section class="card comfort-card">
        <div class="comfort-pulse" aria-hidden="true" />
        <h2 class="comfort-title">{{ comfortTitle }}</h2>
        <p class="comfort-desc">{{ comfortDesc }}</p>
        <div v-if="showQueueProgress" class="progress-block">
          <div class="progress-meta">
            <span>候诊进度</span>
            <span>前面 {{ info.ahead_count }} 人 · 全队列 {{ info.state.waiting.length }} 人</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: `${queueProgress}%` }" />
          </div>
        </div>
        <p class="comfort-tip">
          <span class="tip-icon" aria-hidden="true">i</span>
          <Transition name="tip-fade" mode="out-in">
            <span :key="tipIndex" class="tip-text">{{ activeTip }}</span>
          </Transition>
        </p>
      </section>

      <section class="card ticket-card">
        <p class="label">我的号码</p>
        <div class="ticket-num">{{ info.patient.ticket_number }}</div>
        <p class="patient-name">{{ info.patient.name }}</p>
        <p v-if="info.patient.name_en" class="patient-name-en">{{ info.patient.name_en }}</p>
        <p class="ticket-hint">叫号时将震动提醒，也可留意候诊大屏</p>
      </section>

      <section class="stats-row">
        <div class="stat-card">
          <span class="stat-value">{{ info.ahead_count }}</span>
          <span class="stat-label">前面还有（人）</span>
          <span class="stat-note">{{ info.ahead_count === 0 ? '即将轮到' : '请耐心等候' }}</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ waitEstimateLabel }}</span>
          <span class="stat-label">预估等待</span>
          <span class="stat-note">仅供参考</span>
        </div>
      </section>

      <section v-if="info.patient.priority === 'urgent'" class="card notice urgent">
        <span class="notice-icon">✓</span>
        <div>
          <p class="notice-title">已获批优先候诊</p>
          <p v-if="info.patient.priority_reason" class="notice-desc">
            {{ info.patient.priority_reason }}
          </p>
        </div>
      </section>

      <section
        v-if="priorityResult"
        class="card result-card"
        :class="resultApproved ? 'approved' : 'rejected'"
      >
        <div class="result-header">
          <div class="result-icon" aria-hidden="true">
            {{ resultApproved ? '✓' : '!' }}
          </div>
          <div class="result-head-text">
            <p class="result-label">优先申请结果</p>
            <span class="result-badge">{{ resultStatusText }}</span>
          </div>
        </div>
        <p v-if="assessmentSummary" class="result-summary">{{ assessmentSummary }}</p>
        <p v-if="!resultApproved" class="result-tip">
          请留意叫号屏幕；如有不适加重，请立即联系分诊台。
        </p>
      </section>
    </template>

    <button type="button" class="fab" @click="showPriority = true">
      申请紧急优先
    </button>

    <p class="demo-note">演示：李婷婷 · A016</p>

    <!-- 叫号弹窗 -->
    <Transition name="fade">
      <div v-if="calledAlert" class="overlay" @click="calledAlert = false">
        <div class="alert-card" @click.stop>
          <div class="alert-ring" />
          <p class="alert-tag">请尽快就诊</p>
          <h2 class="alert-title">轮到您了</h2>
          <p class="alert-ticket">{{ info?.patient.ticket_number }}</p>
          <p class="alert-room">请前往 {{ info?.patient.room }}</p>
          <p class="alert-en">Please proceed to {{ info?.patient.room }}</p>
          <button type="button" class="alert-btn" @click="calledAlert = false">知道了</button>
        </div>
      </div>
    </Transition>

    <!-- 优先申请 -->
    <Transition name="slide-up">
      <div v-if="showPriority" class="modal" @click.self="showPriority = false">
        <div class="sheet">
          <div class="sheet-handle" />
          <h3>紧急优先申请</h3>
          <p class="sheet-hint">
            请简要描述症状，系统将自动评估；非医疗理由（如赶时间、VIP）将被拒绝。
          </p>
          <textarea
            v-model="reason"
            rows="4"
            placeholder="例如：孕36周剧烈腹痛；胸闷气短半小时"
          />
          <div class="sheet-actions">
            <button type="button" class="btn-ghost" @click="showPriority = false">取消</button>
            <button
              type="button"
              class="btn-primary"
              :disabled="submitting || !reason.trim()"
              @click="submitPriority"
            >
              {{ submitting ? '评估中…' : '提交申请' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.page {
  max-width: 420px;
  margin: 0 auto;
  padding: 20px 18px 100px;
  min-height: 100vh;
}

/* 顶栏 */
.header {
  margin-bottom: 20px;
}

.header-badge {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 600;
  color: #1e6fd9;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  padding: 4px 10px;
  border-radius: 999px;
  letter-spacing: 0.06em;
  margin-bottom: 10px;
}

.header-badge.warn {
  color: #b45309;
  background: #fffbeb;
  border-color: #fde68a;
}

.banner-paused {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  margin-bottom: 14px;
  border-radius: 12px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  font-size: 0.85rem;
  color: #92400e;
  line-height: 1.45;
}

.banner-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f59e0b;
  animation: pulse-dot 1.2s ease-in-out infinite;
}

@keyframes pulse-dot {
  50% { opacity: 0.4; transform: scale(0.85); }
}

.comfort-card {
  position: relative;
  overflow: hidden;
  padding: 18px 18px 16px;
  background: linear-gradient(135deg, #eff6ff 0%, #fff 55%);
  border-color: #bfdbfe;
}

.comfort-pulse {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.5);
  animation: live-pulse 2s ease-out infinite;
}

@keyframes live-pulse {
  0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.45); }
  70% { box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }
  100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
}

.comfort-title {
  font-size: 1.05rem;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.4;
  padding-right: 20px;
}

.comfort-desc {
  margin-top: 8px;
  font-size: 0.86rem;
  color: #475569;
  line-height: 1.55;
}

.progress-block {
  margin-top: 14px;
}

.progress-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 0.72rem;
  color: #64748b;
  margin-bottom: 6px;
}

.progress-track {
  height: 8px;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #1e8cff, #1e6fd9);
  transition: width 0.6s ease;
}

.comfort-tip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed #dbeafe;
  font-size: 0.8rem;
  color: #64748b;
  line-height: 1.5;
}

.tip-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #e0f2fe;
  color: #1e6fd9;
  font-size: 0.7rem;
  font-weight: 700;
  font-style: normal;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
}

.tip-text {
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

.header h1 {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: 0.02em;
}

.meta {
  margin-top: 6px;
  font-size: 0.88rem;
  color: #64748b;
}

/* 卡片通用 */
.card {
  background: #fff;
  border-radius: 16px;
  border: 1px solid #e8eef4;
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.05);
  padding: 20px;
  margin-bottom: 14px;
}

/* 票号主卡 */
.ticket-card {
  text-align: center;
  padding: 28px 20px 24px;
  background: linear-gradient(180deg, #fff 0%, #f8fafc 100%);
}

.ticket-card .label {
  font-size: 0.82rem;
  color: #94a3b8;
  letter-spacing: 0.1em;
}

.ticket-num {
  margin-top: 8px;
  font-size: 3.25rem;
  font-weight: 800;
  color: #1e6fd9;
  letter-spacing: 0.06em;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.patient-name {
  margin-top: 10px;
  font-size: 1.2rem;
  font-weight: 600;
  color: #0f172a;
}

.patient-name-en {
  margin-top: 4px;
  font-size: 0.88rem;
  color: #64748b;
}

.ticket-hint {
  margin-top: 14px;
  font-size: 0.78rem;
  color: #94a3b8;
}

/* 统计 */
.stats-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 14px;
}

.stat-card {
  background: #fff;
  border: 1px solid #e8eef4;
  border-radius: 14px;
  padding: 18px 14px;
  text-align: center;
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.04);
}

.stat-value {
  display: block;
  font-size: 1.85rem;
  font-weight: 700;
  color: #0f172a;
  font-variant-numeric: tabular-nums;
}

.stat-label {
  display: block;
  margin-top: 6px;
  font-size: 0.75rem;
  color: #94a3b8;
  line-height: 1.35;
}

.stat-note {
  display: block;
  margin-top: 4px;
  font-size: 0.68rem;
  color: #cbd5e1;
}

/* 提示条 */
.notice {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.notice.urgent {
  background: #fffbeb;
  border-color: #fde68a;
}

.notice-icon {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #dcfce7;
  color: #16a34a;
  font-size: 0.9rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.notice-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #0f172a;
}

.notice-desc {
  margin-top: 4px;
  font-size: 0.82rem;
  color: #64748b;
  line-height: 1.45;
}

/* 优先申请结果 */
.result-card {
  padding: 16px 18px;
  display: block;
}

.result-card.approved {
  background: linear-gradient(180deg, #f0fdf4 0%, #fff 55%);
  border-color: #bbf7d0;
}

.result-card.rejected {
  background: linear-gradient(180deg, #f8fafc 0%, #fff 55%);
  border-color: #e2e8f0;
}

.result-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.result-icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  font-weight: 800;
}

.result-card.approved .result-icon {
  background: #dcfce7;
  color: #16a34a;
}

.result-card.rejected .result-icon {
  background: #f1f5f9;
  color: #64748b;
}

.result-head-text {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.result-label {
  font-size: 0.95rem;
  font-weight: 600;
  color: #0f172a;
  white-space: nowrap;
}

.result-badge {
  flex-shrink: 0;
  font-size: 0.78rem;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 999px;
  letter-spacing: 0.04em;
}

.result-card.approved .result-badge {
  background: #16a34a;
  color: #fff;
}

.result-card.rejected .result-badge {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.result-summary {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(15, 23, 42, 0.06);
  font-size: 0.88rem;
  color: #475569;
  line-height: 1.55;
  word-break: break-word;
}

.result-card.approved .result-summary {
  border-top-color: #bbf7d0;
  color: #166534;
}

.result-tip {
  margin-top: 8px;
  font-size: 0.78rem;
  color: #94a3b8;
  line-height: 1.45;
}

/* 底部按钮 */
.fab {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  width: calc(100% - 36px);
  max-width: 384px;
  padding: 15px 20px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: #fff;
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(220, 38, 38, 0.28);
  transition: transform 0.15s, box-shadow 0.15s;
}

.fab:active {
  transform: translateX(-50%) scale(0.98);
}

.demo-note {
  text-align: center;
  font-size: 0.72rem;
  color: #cbd5e1;
  margin-top: 20px;
}

/* 叫号全屏 */
.overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(6px);
}

.alert-card {
  position: relative;
  width: 100%;
  max-width: 340px;
  text-align: center;
  background: #fff;
  border-radius: 20px;
  padding: 36px 28px 28px;
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.2);
}

.alert-ring {
  width: 56px;
  height: 56px;
  margin: 0 auto 16px;
  border: 3px solid #1e6fd9;
  border-radius: 50%;
  animation: ring-pulse 1.2s ease-in-out infinite;
}

@keyframes ring-pulse {
  50% { transform: scale(1.08); opacity: 0.7; }
}

.alert-tag {
  font-size: 0.78rem;
  font-weight: 600;
  color: #1e6fd9;
  letter-spacing: 0.12em;
}

.alert-title {
  font-size: 1.75rem;
  font-weight: 800;
  color: #0f172a;
  margin-top: 8px;
}

.alert-ticket {
  font-size: 2.5rem;
  font-weight: 800;
  color: #d97706;
  margin-top: 12px;
  letter-spacing: 0.06em;
}

.alert-room {
  margin-top: 12px;
  font-size: 1.05rem;
  color: #334155;
  font-weight: 500;
}

.alert-en {
  margin-top: 6px;
  font-size: 0.85rem;
  color: #94a3b8;
}

.alert-btn {
  margin-top: 24px;
  width: 100%;
  padding: 14px;
  border: none;
  border-radius: 12px;
  background: #1e6fd9;
  color: #fff;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
}

/* 申请弹层 */
.modal {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  background: rgba(15, 23, 42, 0.4);
  backdrop-filter: blur(4px);
}

.sheet {
  width: 100%;
  max-width: 420px;
  background: #fff;
  border-radius: 20px 20px 0 0;
  padding: 12px 20px 28px;
  padding-bottom: calc(28px + env(safe-area-inset-bottom, 0px));
  box-shadow: 0 -8px 40px rgba(15, 23, 42, 0.12);
}

.sheet-handle {
  width: 40px;
  height: 4px;
  margin: 0 auto 16px;
  background: #e2e8f0;
  border-radius: 2px;
}

.sheet h3 {
  font-size: 1.1rem;
  font-weight: 700;
  color: #0f172a;
}

.sheet-hint {
  margin-top: 8px;
  font-size: 0.82rem;
  color: #64748b;
  line-height: 1.5;
}

.sheet textarea {
  width: 100%;
  margin: 16px 0;
  padding: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  font-size: 1rem;
  font-family: inherit;
  color: #0f172a;
  background: #f8fafc;
  resize: none;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.sheet textarea:focus {
  border-color: #93c5fd;
  box-shadow: 0 0 0 3px rgba(30, 111, 217, 0.15);
  background: #fff;
}

.sheet-actions {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 10px;
}

.btn-ghost,
.btn-primary {
  padding: 13px;
  border-radius: 12px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  border: none;
}

.btn-ghost {
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #e2e8f0;
}

.btn-primary {
  background: linear-gradient(135deg, #1e8cff, #1e6fd9);
  color: #fff;
  box-shadow: 0 4px 14px rgba(30, 111, 217, 0.3);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  box-shadow: none;
}

/* 过渡 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: opacity 0.25s ease;
}
.slide-up-enter-active .sheet,
.slide-up-leave-active .sheet {
  transition: transform 0.28s ease;
}
.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
}
.slide-up-enter-from .sheet,
.slide-up-leave-to .sheet {
  transform: translateY(100%);
}
</style>
