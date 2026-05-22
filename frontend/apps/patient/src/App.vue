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
const submitting = ref(false)
let disposeWs: (() => void) | null = null

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
    await refresh()
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await refresh()
  disposeWs = createReconnectingWs((type, payload) => {
    if (payload.state) {
      if (info.value) info.value.state = payload.state as QueueState
    }
    if (type === 'patient_called' && payload.patient) {
      onCalled(payload.patient as Patient)
      refresh()
    }
    if (type === 'priority_applied') refresh()
  })
})

onUnmounted(() => disposeWs?.())
</script>

<template>
  <div class="page">
    <div v-if="calledAlert" class="overlay" @click="calledAlert = false">
      <div class="alert-box">
        <div class="pulse">🔔</div>
        <h2>请您就诊！</h2>
        <p>号码 {{ info?.patient.ticket_number }} 已被呼叫</p>
        <p class="en">Please proceed to {{ info?.patient.room }}</p>
        <button @click.stop="calledAlert = false">知道了</button>
      </div>
    </div>

    <header>
      <h1>我的候诊</h1>
      <p>{{ info?.state.department }} · {{ info?.patient.room }}</p>
    </header>

    <section class="card ticket" v-if="info">
      <p class="label">我的号码</p>
      <div class="num">{{ info.patient.ticket_number }}</div>
      <p class="name">{{ info.patient.name }}</p>
    </section>

    <section class="card stats" v-if="info">
      <div class="stat">
        <span class="val">{{ info.ahead_count }}</span>
        <span class="lbl">前面还有（人）</span>
      </div>
      <div class="stat">
        <span class="val">~{{ info.estimated_wait_minutes }}</span>
        <span class="lbl">预估等待（分钟）</span>
      </div>
    </section>

    <section class="card" v-if="info?.patient.priority === 'urgent'">
      <p class="urgent-badge">✓ 已获批优先候诊</p>
      <p class="hint" v-if="info.patient.priority_reason">{{ info.patient.priority_reason }}</p>
    </section>

    <section class="card" v-if="priorityResult">
      <h3>优先申请结果</h3>
      <p><strong>{{ priorityResult.approved ? '已通过' : '未自动通过' }}</strong></p>
      <p class="hint">{{ assessmentSummary }}</p>
    </section>

    <button class="fab" @click="showPriority = true">申请紧急优先</button>

    <div v-if="showPriority" class="modal">
      <div class="modal-inner">
        <h3>紧急优先申请</h3>
        <p class="hint">请用一句话描述症状（系统将 AI 评估，非医疗理由将被拒绝）</p>
        <textarea v-model="reason" rows="4" placeholder="例：孕36周剧烈腹痛；或：胸闷气短半小时" />
        <div class="modal-actions">
          <button @click="showPriority = false">取消</button>
          <button class="primary" :disabled="submitting" @click="submitPriority">
            {{ submitting ? '评估中…' : '提交' }}
          </button>
        </div>
      </div>
    </div>

    <p class="demo-note">演示视角：患者 李婷婷 (A016)</p>
  </div>
</template>

<style scoped>
.page { max-width: 420px; margin: 0 auto; padding: 16px 16px 80px; min-height: 100vh; }
header { margin-bottom: 20px; }
header h1 { font-size: 1.5rem; }
header p { color: #666; font-size: 0.9rem; }
.card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 12px;
  box-shadow: 0 2px 12px rgba(0,0,0,.06);
}
.ticket { text-align: center; }
.ticket .label { color: #888; font-size: 0.9rem; }
.ticket .num { font-size: 3rem; font-weight: 800; color: #0d6efd; }
.ticket .name { font-size: 1.25rem; margin-top: 4px; }
.stats { display: flex; gap: 16px; }
.stat { flex: 1; text-align: center; }
.stat .val { display: block; font-size: 2rem; font-weight: 700; color: #212529; }
.stat .lbl { font-size: 0.8rem; color: #888; }
.fab {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  width: calc(100% - 32px); max-width: 388px;
  padding: 14px; border: none; border-radius: 12px;
  background: #dc3545; color: #fff; font-size: 1rem; font-weight: 600;
  cursor: pointer; box-shadow: 0 4px 16px rgba(220,53,69,.4);
}
.modal {
  position: fixed; inset: 0; background: rgba(0,0,0,.5);
  display: flex; align-items: flex-end; z-index: 100;
}
.modal-inner {
  background: #fff; width: 100%; max-width: 420px; margin: 0 auto;
  border-radius: 16px 16px 0 0; padding: 20px;
}
.modal-inner h3 { margin-bottom: 8px; }
.modal-inner textarea {
  width: 100%; margin: 12px 0; padding: 12px;
  border: 1px solid #ddd; border-radius: 8px; font-size: 1rem;
}
.modal-actions { display: flex; gap: 12px; }
.modal-actions button { flex: 1; padding: 12px; border-radius: 8px; border: 1px solid #ddd; background: #fff; }
.modal-actions .primary { background: #0d6efd; color: #fff; border: none; }
.hint { font-size: 0.85rem; color: #666; }
.urgent-badge { color: #dc3545; font-weight: 600; }
.overlay {
  position: fixed; inset: 0; background: rgba(13, 110, 253, 0.92);
  z-index: 200; display: flex; align-items: center; justify-content: center;
  animation: fadeIn 0.2s;
}
.alert-box { text-align: center; color: #fff; padding: 24px; }
.alert-box h2 { font-size: 2rem; margin: 16px 0; }
.alert-box .en { opacity: 0.9; margin-top: 8px; }
.alert-box button {
  margin-top: 24px; padding: 12px 32px; border: 2px solid #fff;
  background: transparent; color: #fff; border-radius: 24px; font-size: 1rem;
}
.pulse { font-size: 4rem; animation: pulse 0.8s infinite; }
@keyframes pulse { 50% { transform: scale(1.15); } }
@keyframes fadeIn { from { opacity: 0; } }
.demo-note { text-align: center; font-size: 0.75rem; color: #aaa; margin-top: 16px; }
</style>
