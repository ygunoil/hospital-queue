<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
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
  disposeWs = createReconnectingWs((type, payload) => {
    if (type === 'connected') applyPayload(payload)
    if (['patient_called', 'queue_updated', 'calling_paused', 'priority_applied'].includes(type)) {
      applyPayload(payload)
    }
  }, (c) => { wsConnected.value = c })
})

onUnmounted(() => disposeWs?.())
</script>

<template>
  <div class="layout">
    <header class="header">
      <div>
        <h1>医生叫号控制台</h1>
        <p class="sub">{{ state?.department }} · {{ state?.room }} · {{ state?.doctor_name }}</p>
      </div>
      <span :class="['badge', wsConnected ? 'on' : 'off']">
        {{ wsConnected ? '实时已连接' : '重连中…' }}
      </span>
    </header>

    <section class="current" v-if="state">
      <h2>当前就诊</h2>
      <div v-if="state.current" class="current-card">
        <span class="num">{{ state.current.ticket_number }}</span>
        <span>{{ state.current.name }}</span>
        <span class="tag" v-if="state.current.priority === 'urgent'">优先</span>
      </div>
      <p v-else class="empty">暂无叫号，请点击下方按钮呼叫下一位</p>
      <p v-if="state.calling_paused" class="paused">⏸ 叫号已暂停</p>
    </section>

    <section class="actions">
      <button class="btn primary" :disabled="loading || state?.calling_paused" @click="post('/api/queue/call-next')">
        呼叫下一位
      </button>
      <button class="btn" :disabled="loading" @click="post('/api/queue/skip')">跳过当前</button>
      <button
        class="btn warn"
        :disabled="loading"
        @click="post(state?.calling_paused ? '/api/queue/resume' : '/api/queue/pause?paused=true')"
      >
        {{ state?.calling_paused ? '恢复叫号' : '暂停叫号' }}
      </button>
    </section>

    <section class="queue" v-if="state">
      <h2>等候队列（{{ state.waiting.length }} 人）</h2>
      <table>
        <thead>
          <tr><th>序号</th><th>号码</th><th>姓名</th><th>状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="(p, i) in state.waiting" :key="p.id" :class="{ urgent: p.priority === 'urgent' }">
            <td>{{ i + 1 }}</td>
            <td><strong>{{ p.ticket_number }}</strong></td>
            <td>{{ p.name }} <small v-if="p.name_en">/ {{ p.name_en }}</small></td>
            <td>
              <span v-if="p.priority === 'urgent'" class="tag">优先</span>
              <span v-else>等候</span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.layout { max-width: 960px; margin: 0 auto; padding: 24px; }
.header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.header h1 { font-size: 1.75rem; }
.sub { color: #5a6b7d; margin-top: 4px; }
.badge { padding: 6px 12px; border-radius: 20px; font-size: 0.85rem; }
.badge.on { background: #d4edda; color: #155724; }
.badge.off { background: #fff3cd; color: #856404; }
.current { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.current-card { display: flex; align-items: center; gap: 16px; font-size: 1.25rem; }
.num { font-size: 2rem; font-weight: 700; color: #0d6efd; }
.tag { background: #dc3545; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; }
.empty, .paused { color: #6c757d; margin-top: 8px; }
.paused { color: #856404; font-weight: 600; }
.actions { display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
.btn { padding: 12px 24px; border: none; border-radius: 8px; font-size: 1rem; cursor: pointer; background: #e9ecef; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.primary { background: #0d6efd; color: #fff; }
.btn.warn { background: #ffc107; color: #212529; }
.queue { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
.queue h2 { margin-bottom: 12px; font-size: 1.1rem; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid #eee; }
tr.urgent { background: #fff5f5; }
small { color: #888; }
</style>
