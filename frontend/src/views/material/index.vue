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
      <label class="filter-item checkbox">
        <input v-model="filters.lowOnly" type="checkbox" />
        <span>仅看储备不足</span>
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
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-low': row.low_stock }">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '材料状态'">
              <span>{{ row[column] ?? '—' }}</span>
              <span v-if="row.low_stock" class="tag low">储备不足</span>
            </template>
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
            <template v-if="loadError">
              <p class="error-text">{{ loadError }}</p>
              <button class="btn" type="button" @click="reload">重试</button>
            </template>
            <template v-else-if="hasFilter">
              <p>未找到符合条件的养护材料，可调整条件后重试</p>
              <button class="btn" type="button" @click="resetFilters">重置条件</button>
            </template>
            <template v-else>
              <p>暂无养护材料数据，可先登记养护材料</p>
              <button class="btn" type="button" @click="reload">刷新重试</button>
            </template>
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条养护材料记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="createVisible" class="modal-mask" @click.self="closeCreate">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>登记养护材料</h3>
        <label v-for="field in createFields" :key="field.name" class="filter-item">
          <span>{{ field.name }}</span>
          <input v-model="createForm[field.name]" :placeholder="field.placeholder" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn primary" type="submit">确认登记</button>
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/material'
const columns = ["材料编号", "材料名称", "规格型号", "结存数量", "储备下限", "计量单位", "存放场地", "保管人员", "材料状态"]
const actions = ["冻结材料", "解冻材料", "登记耗尽"]
const statuses = ["正常可用", "临近不足", "已冻结", "已耗尽"]
const createFields = [
  { name: '材料编号', placeholder: '必填，如 MATE-0004' },
  { name: '材料名称', placeholder: '必填' },
  { name: '规格型号', placeholder: '必填' },
  { name: '结存数量', placeholder: '需为大于 0 的数字' },
  { name: '储备下限', placeholder: '选填，结存低于该值会标记储备不足' },
  { name: '计量单位', placeholder: '选填' },
  { name: '存放场地', placeholder: '选填' },
  { name: '保管人员', placeholder: '选填' },
]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref([
  { label: '可用材料', value: 0 },
  { label: '储备不足材料', value: 0 },
  { label: '已冻结材料', value: 0 },
])
const errorMessage = ref('')
const loadError = ref('')
const filters = reactive({ keyword: '', status: '', lowOnly: false })
const createVisible = ref(false)
const createError = ref('')
const createForm = reactive<Record<string, string>>({})

const hasFilter = computed(() => Boolean(filters.keyword || filters.status || filters.lowOnly))

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  filters.lowOnly = false
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createError.value = ''
  for (const field of createFields) {
    createForm[field.name] = ''
  }
  createVisible.value = true
}

function closeCreate() {
  createVisible.value = false
}

async function submitCreate() {
  createError.value = ''
  const missing = ['材料编号', '材料名称', '规格型号'].filter((name) => !(createForm[name] ?? '').trim())
  if (missing.length) {
    createError.value = `缺少必填字段：${missing.join('、')}`
    return
  }
  const quantityText = (createForm['结存数量'] ?? '').trim()
  if (!quantityText) {
    createError.value = '结存数量不合规：不能为空，不能按正常可用入库'
    return
  }
  const quantity = Number(quantityText)
  if (!Number.isFinite(quantity) || quantity <= 0) {
    createError.value = `结存数量不合规：${quantityText} 不是大于 0 的数字，不能按正常可用入库`
    return
  }
  const limitText = (createForm['储备下限'] ?? '').trim()
  if (limitText && (!Number.isFinite(Number(limitText)) || Number(limitText) < 0)) {
    createError.value = `储备下限不合规：${limitText} 不是不小于 0 的数字`
    return
  }
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm } }),
    })
    const payload = (await response.json()) as { ok: boolean; message?: string }
    if (!response.ok || !payload.ok) {
      createError.value = payload.message || '养护材料登记失败，请稍后重试'
      return
    }
    createVisible.value = false
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '养护材料登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json()) as { ok: boolean; message?: string }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '养护材料动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '养护材料操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  loadError.value = ''
  const query = new URLSearchParams()
  if (filters.keyword) query.set('keyword', filters.keyword)
  if (filters.status) query.set('status', filters.status)
  if (filters.lowOnly) query.set('low_only', 'true')
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('养护材料列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    const summary = (payload.summary ?? {}) as Record<string, number>
    stats.value = stats.value.map((item) => ({ ...item, value: summary[item.label] ?? 0 }))
  } catch (error) {
    rows.value = []
    total.value = 0
    loadError.value = error instanceof Error ? error.message : '养护材料列表读取失败'
  }
}

onMounted(reload)
</script>
