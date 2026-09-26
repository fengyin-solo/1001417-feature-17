<template>
  <section class="page" data-module="material">
    <header class="page-head">
      <div>
        <h2>养护材料管理</h2>
        <p class="page-desc">维护养护材料，围绕材料编号、材料名称、规格型号、结存数量做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记养护材料</button>
        <button class="btn" type="button" @click="exportRows">导出养护材料清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form v-if="showCreate" class="create-panel" @submit.prevent="submitCreate">
      <label v-for="field in createFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input
          v-model="createForm[field]"
          :placeholder="field === '结存数量' ? '必填，须大于 0' : `填写${field}`"
        />
      </label>
      <button class="btn primary" type="submit">提交登记</button>
      <button class="btn ghost" type="button" @click="closeCreate">取消</button>
      <span v-if="createMessage" class="error-text">{{ createMessage }}</span>
    </form>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>材料编号</span>
        <input v-model="filters.keyword" placeholder="按材料编号检索" />
      </label>
      <label class="filter-item">
        <span>材料状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          :class="{ 'row-shortage': statusOf(row) === '临近不足' }"
        >
          <td v-for="column in columns" :key="column">
            <span
              v-if="column === '材料状态'"
              class="status-tag"
              :class="{ 'status-shortage': statusOf(row) === '临近不足' }"
            >
              {{ statusOf(row) || '—' }}
            </span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            <p>{{ emptyText }}</p>
            <button class="btn" type="button" @click="reload">重试</button>
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条养护材料记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/material'
const columns = ["材料编号", "材料名称", "规格型号", "结存数量", "储备下限", "计量单位", "存放场地", "保管人员", "材料状态"]
const actions = ["冻结材料", "解冻材料", "登记耗尽"]
const statuses = ["正常可用", "临近不足", "已冻结", "已耗尽"]
const createFields = ["材料编号", "材料名称", "规格型号", "结存数量", "储备下限", "计量单位", "存放场地", "保管人员"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const loadFailed = ref(false)
const filters = ref({ keyword: '', status: '' })
const stats = ref([
  { label: '可用材料', value: 0 },
  { label: '储备不足材料', value: 0 },
  { label: '已冻结材料', value: 0 },
])
const showCreate = ref(false)
const createMessage = ref('')
const createForm = ref<Record<string, string>>({})

const hasFilter = computed(() => Boolean(filters.value.keyword || filters.value.status))
const emptyText = computed(() => {
  if (loadFailed.value) return '养护材料列表读取失败，请检查服务后重试'
  if (hasFilter.value) return '未找到符合条件的养护材料，可调整条件后重试'
  return '暂无养护材料数据，可先登记养护材料，或重试读取'
})

function statusOf(row: Row): string {
  return String(row['材料状态'] ?? row.status ?? '')
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = {}
  createMessage.value = ''
  showCreate.value = true
}

function closeCreate() {
  showCreate.value = false
  createMessage.value = ''
}

async function submitCreate() {
  createMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      createMessage.value = String(payload?.message ?? payload?.detail ?? '养护材料登记失败，请检查填写内容')
      return
    }
    closeCreate()
    await reload()
  } catch (error) {
    createMessage.value = error instanceof Error ? error.message : '养护材料登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      errorMessage.value = String(payload?.message ?? payload?.detail ?? '养护材料动作未生效，请稍后重试')
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '养护材料操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  loadFailed.value = false
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/summary`),
    ])
    if (!listResponse.ok || !summaryResponse.ok) {
      throw new Error('养护材料列表读取失败')
    }
    const payload = await listResponse.json()
    const summary = await summaryResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    stats.value = [
      { label: '可用材料', value: Number(summary['可用材料'] ?? 0) },
      { label: '储备不足材料', value: Number(summary['储备不足材料'] ?? 0) },
      { label: '已冻结材料', value: Number(summary['已冻结材料'] ?? 0) },
    ]
  } catch (error) {
    rows.value = []
    total.value = 0
    loadFailed.value = true
    errorMessage.value = error instanceof Error ? error.message : '养护材料列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.create-panel {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-end;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
}
.filter-item select {
  min-width: 120px;
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.row-shortage {
  background: #fff7ed;
}
.status-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  background: #eef2f7;
  font-size: 12px;
}
.status-shortage {
  background: #fde68a;
  color: #92400e;
  font-weight: 600;
}
.empty-state p {
  margin: 8px 0;
}
</style>
