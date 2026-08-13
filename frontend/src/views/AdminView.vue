<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { adminApi } from '@/api/admin'

const activeTab = ref<'overview' | 'ragas' | 'trace' | 'permissions' | 'badcase' | 'review'>('overview')

// ── Overview tab ──
const overviewStats = reactive({
  total_chunks: 0,
  total_documents: 0,
  total_feedback: 0,
  total_tickets: 0,
  total_sessions: 0,
  status: 'unknown',
  feedback_stats: {} as any,
})
const loadingOverview = ref(false)

async function loadOverview() {
  loadingOverview.value = true
  try {
    const res = await adminApi.stats()
    Object.assign(overviewStats, res.data)
  } catch (e: any) {
    console.error('加载概览失败:', e)
  } finally {
    loadingOverview.value = false
  }
}

// ── RAGAS evaluation tab ──
const ragasStatus = ref<any>({ status: 'idle', report: null })
const ragasLimit = ref(0)
const includeRagas = ref(true)
const loadingRagas = ref(false)
let ragasPoller: number | undefined

async function loadRagasStatus() {
  try {
    const res = await adminApi.ragasStatus()
    ragasStatus.value = res.data
    if (res.data.status !== 'running' && ragasPoller) {
      window.clearInterval(ragasPoller)
      ragasPoller = undefined
    }
  } catch (e: any) {
    console.error('加载 RAGAS 状态失败:', e)
  }
}

async function startRagas() {
  loadingRagas.value = true
  try {
    const res = await adminApi.runRagas(ragasLimit.value, includeRagas.value)
    ragasStatus.value = res.data
    if (!ragasPoller) ragasPoller = window.setInterval(loadRagasStatus, 1500)
  } catch (e: any) {
    alert('启动测试失败: ' + (e.userMessage || e.response?.data?.detail || e.message))
  } finally {
    loadingRagas.value = false
  }
}

// ── Trace tab ──
const traces = ref<any[]>([])
const traceFilterUser = ref('')
const loadingTraces = ref(false)
const expandedTraceId = ref<string | null>(null)
const traceDetail = ref<any>(null)
const loadingTraceDetail = ref(false)

const traceNodeDescriptions: Record<string, string> = {
  input_guard: '输入安全检查，过滤无效或不合规问题',
  intent_classifier: '意图识别，判断是否为咨询、工单或其他请求',
  hybrid_retrieval: '混合检索，使用向量检索和 BM25 查找候选知识',
  retrieval_no_role_filter: '放宽角色限制后再次检索，提升召回率',
  no_retrieval_results: '未检索到相关知识，准备转人工或创建工单',
  rerank: '重排序，对候选知识按相关性重新排序',
  confidence_gate: '置信度判断，决定直接回答或低置信处理',
  llm_call: '大模型调用，记录模型参数、响应摘要和 token 使用量',
  generate_answer: '答案生成，基于知识库上下文调用大模型生成回复',
  low_confidence: '低置信处理，判断是否可回答或建议创建工单',
  output_guard: '输出安全检查，清理不合规回答内容',
  ticket_draft: '工单草稿生成，整理问题并生成待确认工单',
  ticket_draft_error: '工单草稿生成异常，已记录错误并返回可用回答',
  api_response: '接口响应结果，记录最终返回给前端的回答摘要',
  api_error: '接口异常结果，记录真实错误和返回给用户的友好提示',
}

function traceNodeName(node: any): string {
  return node?.node || node?.node_name || node?.name || ''
}

function traceNodeDescription(node: any): string {
  const name = traceNodeName(node)
  return traceNodeDescriptions[name] || '业务处理节点，记录本次问答链路中的一个执行步骤'
}

function nodeInput(node: any) {
  return node?.input || node?.input_data || {}
}

function nodeOutput(node: any) {
  return node?.output || node?.output_data || {}
}

function isLlmNode(node: any): boolean {
  return traceNodeName(node) === 'llm_call'
}

async function loadTraces() {
  loadingTraces.value = true
  try {
    const params: any = { limit: 50 }
    if (traceFilterUser.value.trim()) {
      params.user_id = traceFilterUser.value.trim()
    }
    const res = await adminApi.traces(params)
    traces.value = res.data.traces || res.data || []
  } catch (e: any) {
    console.error('加载链路失败:', e)
  } finally {
    loadingTraces.value = false
  }
}

async function toggleTraceDetail(traceId: string) {
  if (expandedTraceId.value === traceId) {
    expandedTraceId.value = null
    traceDetail.value = null
    return
  }
  expandedTraceId.value = traceId
  loadingTraceDetail.value = true
  try {
    const res = await adminApi.traceDetail(traceId)
    traceDetail.value = res.data
  } catch (e: any) {
    console.error('加载链路详情失败:', e)
  } finally {
    loadingTraceDetail.value = false
  }
}

// ── BadCase tab ──
const badcases = ref<any[]>([])
const loadingBadcases = ref(false)
const convertingBadcaseId = ref<string | null>(null)

async function loadBadcases() {
  loadingBadcases.value = true
  try {
    const res = await adminApi.badcaseList(200)
    badcases.value = res.data.badcases || res.data || []
  } catch (e: any) {
    console.error('加载BadCase失败:', e)
  } finally {
    loadingBadcases.value = false
  }
}

async function convertBadcase(feedbackId: string) {
  convertingBadcaseId.value = feedbackId
  try {
    await adminApi.convertBadcase(feedbackId)
    alert('已转为BadCase')
    loadBadcases()
  } catch (e: any) {
    alert('转换失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    convertingBadcaseId.value = null
  }
}

// ── Feedback Review tab ──
const reviewFeedbacks = ref<any[]>([])
const loadingReview = ref(false)
const filterReviewStatus = ref('pending_review')
const actionReviewId = ref<string | null>(null)

async function loadReviewFeedbacks() {
  loadingReview.value = true
  try {
    const params: any = { limit: 200 }
    if (filterReviewStatus.value && filterReviewStatus.value !== 'all') {
      params.review_status = filterReviewStatus.value
    }
    const res = await adminApi.feedbackList(params)
    reviewFeedbacks.value = res.data.feedbacks || res.data || []
  } catch (e: any) {
    console.error('加载反馈审核列表失败:', e)
  } finally {
    loadingReview.value = false
  }
}

async function approveReview(feedbackId: string) {
  actionReviewId.value = feedbackId
  try {
    await adminApi.reviewFeedback(feedbackId)
    alert('已审核通过')
    loadReviewFeedbacks()
  } catch (e: any) {
    alert('审核失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    actionReviewId.value = null
  }
}

async function convertReviewToBadcase(feedbackId: string) {
  actionReviewId.value = feedbackId
  try {
    await adminApi.convertBadcase(feedbackId)
    alert('已转为BadCase')
    loadReviewFeedbacks()
  } catch (e: any) {
    alert('转换失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    actionReviewId.value = null
  }
}

// ── Role Module Permissions tab ──
const permissionRoles = ref<any[]>([])
const permissionModules = ref<string[]>([])
const selectedPermissionRole = ref('')
const permissionDraft = reactive<Record<string, string[]>>({})
const loadingPermissions = ref(false)
const savingPermissionRole = ref<string | null>(null)

async function loadPermissions() {
  loadingPermissions.value = true
  try {
    const res = await adminApi.roleModules()
    permissionRoles.value = res.data.roles || []
    permissionModules.value = res.data.modules || []
    for (const role of permissionRoles.value) {
      permissionDraft[role.role] = [...(role.modules || [])]
    }
    if (!selectedPermissionRole.value && permissionRoles.value.length > 0) {
      selectedPermissionRole.value = permissionRoles.value[0].role
    }
  } catch (e: any) {
    console.error('加载模块权限失败:', e)
  } finally {
    loadingPermissions.value = false
  }
}

function selectedRoleConfig() {
  return permissionRoles.value.find((role) => role.role === selectedPermissionRole.value)
}

function roleModules(role: string): string[] {
  if (!permissionDraft[role]) permissionDraft[role] = []
  return permissionDraft[role]
}

function isModuleChecked(role: string, module: string): boolean {
  return roleModules(role).includes(module)
}

function toggleModule(role: string, module: string) {
  const modules = roleModules(role)
  const index = modules.indexOf(module)
  if (index >= 0) {
    modules.splice(index, 1)
  } else {
    modules.push(module)
  }
}

function selectAllModules(role: string) {
  permissionDraft[role] = [...permissionModules.value]
}

function clearModules(role: string) {
  permissionDraft[role] = []
}

async function saveRoleModules(role: string) {
  savingPermissionRole.value = role
  try {
    await adminApi.updateRoleModules(role, roleModules(role))
    await loadPermissions()
    selectedPermissionRole.value = role
    alert('模块权限已保存')
  } catch (e: any) {
    alert('保存失败: ' + (e.userMessage || e.response?.data?.detail || e.message))
  } finally {
    savingPermissionRole.value = null
  }
}

async function resetRoleModules(role: string) {
  if (!confirm('确定恢复该角色的默认模块权限?')) return
  savingPermissionRole.value = role
  try {
    await adminApi.resetRoleModules(role)
    await loadPermissions()
    selectedPermissionRole.value = role
    alert('已恢复默认配置')
  } catch (e: any) {
    alert('恢复失败: ' + (e.userMessage || e.response?.data?.detail || e.message))
  } finally {
    savingPermissionRole.value = null
  }
}

function formatDate(ts: string | number): string {
  if (!ts) return '-'
  return new Date(ts).toLocaleString('zh-CN')
}

function formatDuration(ms?: number): string {
  if (ms === undefined || ms === null) return '-'
  if (ms < 1000) return `${ms}ms`
  const totalSeconds = Math.round(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes > 0) return `${minutes}分${seconds}秒`
  return `${seconds}秒`
}

function formatPercent(value?: number): string {
  return value === undefined || value === null ? '-' : `${(value * 100).toFixed(1)}%`
}

function truncate(text: string, len: number): string {
  if (!text) return ''
  return text.length > len ? text.slice(0, len) + '...' : text
}

function reviewStatusBadge(status: string) {
  switch (status) {
    case 'pending_review': return 'bg-yellow-100 text-yellow-700'
    case 'approved': return 'bg-green-100 text-green-700'
    case 'rejected': return 'bg-red-100 text-red-700'
    default: return 'bg-gray-100 text-gray-600'
  }
}

function traceStatusBadge(status: string) {
  switch (status) {
    case 'success': case 'ok': return 'bg-green-100 text-green-700'
    case 'error': return 'bg-red-100 text-red-700'
    case 'warning': return 'bg-yellow-100 text-yellow-700'
    case 'running': return 'bg-blue-100 text-blue-700'
    default: return 'bg-gray-100 text-gray-600'
  }
}

function badcaseStatusBadge(status: string) {
  switch (status) {
    case 'pending': return 'bg-yellow-100 text-yellow-700'
    case 'converted': return 'bg-green-100 text-green-700'
    case 'resolved': return 'bg-blue-100 text-blue-700'
    default: return 'bg-gray-100 text-gray-600'
  }
}

onMounted(() => {
  loadOverview()
  loadTraces()
  loadPermissions()
  loadBadcases()
  loadReviewFeedbacks()
  loadRagasStatus()
})

onUnmounted(() => {
  if (ragasPoller) window.clearInterval(ragasPoller)
})
</script>

<template>
  <div>
    <!-- Tabs -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 mb-4">
      <div class="flex border-b border-gray-200">
        <button
          v-for="tab in [
            { key: 'overview' as const, label: '概览', icon: '📊' },
            { key: 'ragas' as const, label: 'RAGAS 测试', icon: '🧪' },
            { key: 'trace' as const, label: '链路追踪', icon: '🔗' },
            { key: 'permissions' as const, label: '模块权限', icon: '🔐' },
            { key: 'badcase' as const, label: 'BadCase', icon: '🐛' },
            { key: 'review' as const, label: '反馈审核', icon: '✅' },
          ]"
          :key="tab.key"
          @click="activeTab = tab.key"
          :class="[
            'px-5 py-3 text-sm font-medium border-b-2 transition-colors',
            activeTab === tab.key
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700',
          ]"
        >
          <span class="mr-1.5">{{ tab.icon }}</span>{{ tab.label }}
        </button>
      </div>
    </div>

    <!-- Tab: RAGAS evaluation -->
    <div v-if="activeTab === 'ragas'" class="space-y-4">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
        <div class="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h3 class="text-lg font-semibold text-gray-800">亲子沟通话术评测</h3>
            <p class="mt-1 text-sm text-gray-500">运行预置用例，检查检索命中、答案覆盖及 RAGAS 指标。</p>
          </div>
          <div class="flex flex-wrap items-end gap-3">
            <label class="block text-sm text-gray-600">
              <span class="mb-1 block">运行数量</span>
              <select v-model.number="ragasLimit" :disabled="ragasStatus.status === 'running'" class="border border-gray-300 rounded-md px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500">
                <option :value="0">全部用例</option>
                <option :value="3">前 3 条</option>
                <option :value="10">前 10 条</option>
              </select>
            </label>
            <label class="flex items-center gap-2 pb-2 text-sm text-gray-600">
              <input v-model="includeRagas" :disabled="ragasStatus.status === 'running'" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
              计算 RAGAS 指标
            </label>
            <button @click="startRagas" :disabled="loadingRagas || ragasStatus.status === 'running'" class="px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {{ ragasStatus.status === 'running' ? '测试进行中...' : loadingRagas ? '启动中...' : '一键测试' }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="ragasStatus.status === 'running'" class="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
        <div class="flex items-center justify-between text-sm text-gray-600"><span>{{ ragasStatus.message || `正在运行 ${ragasStatus.run_id}` }}</span><span>{{ ragasStatus.completed || 0 }} / {{ ragasStatus.total || 0 }}</span></div>
        <div class="mt-3 h-2 overflow-hidden rounded bg-gray-100"><div class="h-full bg-blue-600 transition-all" :style="{ width: `${ragasStatus.total ? ((ragasStatus.completed || 0) / ragasStatus.total) * 100 : 0}%` }"></div></div>
      </div>

      <div v-if="ragasStatus.events?.length" class="bg-slate-950 border border-slate-800 rounded-lg p-4">
        <div class="mb-2 text-xs font-medium text-slate-300">后端任务日志</div>
        <div class="max-h-52 overflow-y-auto space-y-1 font-mono text-xs leading-5 text-slate-200">
          <div v-for="(event, index) in ragasStatus.events" :key="`${event.time}-${index}`"><span class="mr-2 text-slate-500">{{ event.time }}</span>{{ event.message }}</div>
        </div>
      </div>

      <div v-if="ragasStatus.status === 'failed'" class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{{ ragasStatus.error || '测试任务失败' }}</div>

      <template v-if="ragasStatus.report">
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4"><p class="text-xs text-gray-500">完成用例</p><p class="mt-1 text-2xl font-bold text-gray-800">{{ ragasStatus.report.completed }}<span class="text-sm font-normal text-gray-400"> / {{ ragasStatus.report.total }}</span></p></div>
          <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4"><p class="text-xs text-gray-500">文档命中率</p><p class="mt-1 text-2xl font-bold text-blue-600">{{ formatPercent(ragasStatus.report.source_hit_rate) }}</p></div>
          <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4"><p class="text-xs text-gray-500">答案覆盖率</p><p class="mt-1 text-2xl font-bold text-green-600">{{ formatPercent(ragasStatus.report.answer_coverage_rate) }}</p></div>
          <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4"><p class="text-xs text-gray-500">失败用例</p><p class="mt-1 text-2xl font-bold text-red-600">{{ ragasStatus.report.failed }}</p></div>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
          <h4 class="text-sm font-semibold text-gray-800">RAGAS 指标</h4>
          <div v-if="ragasStatus.report.ragas" class="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
            <div v-for="(value, key) in ragasStatus.report.ragas" :key="String(key)" class="rounded-md bg-gray-50 p-3"><p class="text-xs text-gray-500 break-all">{{ key }}</p><p class="mt-1 text-lg font-semibold text-gray-800">{{ typeof value === 'number' ? value.toFixed(3) : value }}</p></div>
          </div>
          <p v-else-if="ragasStatus.report.ragas_error" class="mt-2 text-sm text-yellow-700">RAGAS 未计算：{{ ragasStatus.report.ragas_error }}</p>
          <p v-else class="mt-2 text-sm text-gray-400">本次未选择 RAGAS 指标计算。</p>
        </div>
        <div v-if="ragasStatus.report.failures?.length" class="bg-white rounded-lg shadow-sm border border-gray-200 p-5"><h4 class="text-sm font-semibold text-gray-800">失败详情</h4><div class="mt-3 space-y-2"><div v-for="item in ragasStatus.report.failures" :key="item.id" class="rounded bg-red-50 px-3 py-2 text-sm text-red-700"><span class="font-mono">{{ item.id }}</span>：{{ item.error }}</div></div></div>
      </template>

      <div v-if="ragasStatus.status === 'idle'" class="rounded-lg border border-dashed border-gray-300 bg-white py-12 text-center text-sm text-gray-400">尚未运行测试。点击“一键测试”开始。</div>
    </div>

    <!-- Tab: Overview -->
    <div v-if="activeTab === 'overview'">
      <div class="grid grid-cols-6 gap-4 mb-4">
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <p class="text-xs text-gray-500">总块数</p>
          <p class="text-2xl font-bold text-gray-800">{{ overviewStats.total_chunks }}</p>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <p class="text-xs text-gray-500">总文档数</p>
          <p class="text-2xl font-bold text-gray-800">{{ overviewStats.total_documents }}</p>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <p class="text-xs text-gray-500">总反馈数</p>
          <p class="text-2xl font-bold text-gray-800">{{ overviewStats.total_feedback }}</p>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <p class="text-xs text-gray-500">总工单数</p>
          <p class="text-2xl font-bold text-gray-800">{{ overviewStats.total_tickets }}</p>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <p class="text-xs text-gray-500">总会话数</p>
          <p class="text-2xl font-bold text-gray-800">{{ overviewStats.total_sessions }}</p>
        </div>
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <p class="text-xs text-gray-500">系统状态</p>
          <p class="text-2xl font-bold" :class="overviewStats.status === 'healthy' ? 'text-green-600' : 'text-yellow-600'">
            {{ overviewStats.status }}
          </p>
        </div>
      </div>

      <!-- Feedback Stats Detail -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <h3 class="text-md font-semibold text-gray-800 mb-3">反馈统计详情</h3>
        <div v-if="overviewStats.feedback_stats && Object.keys(overviewStats.feedback_stats).length > 0" class="grid grid-cols-4 gap-3">
          <div v-for="(val, key) in overviewStats.feedback_stats" :key="key" class="bg-gray-50 rounded-lg p-3">
            <p class="text-xs text-gray-400">{{ key }}</p>
            <p class="text-lg font-semibold text-gray-800">{{ val }}</p>
          </div>
        </div>
        <p v-else class="text-sm text-gray-400">暂无反馈统计数据</p>
      </div>

      <div class="mt-4 text-center">
        <button
          @click="loadOverview"
          :disabled="loadingOverview"
          class="px-4 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-md transition-colors"
        >
          {{ loadingOverview ? '加载中...' : '刷新数据' }}
        </button>
      </div>
    </div>

    <!-- Tab: Trace -->
    <div v-if="activeTab === 'trace'">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-4">
        <div class="flex items-center space-x-4">
          <input
            v-model="traceFilterUser"
            type="text"
            placeholder="用户ID筛选..."
            class="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none w-48"
          />
          <button
            @click="loadTraces"
            :disabled="loadingTraces"
            class="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {{ loadingTraces ? '查询中...' : '查询' }}
          </button>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-gray-200 bg-gray-50">
                <th class="text-left py-3 px-4 font-semibold text-gray-600">Trace ID</th>
                <th class="text-left py-3 px-4 font-semibold text-gray-600">问题</th>
                <th class="text-left py-3 px-4 font-semibold text-gray-600">用户</th>
                <th class="text-left py-3 px-4 font-semibold text-gray-600">节点数</th>
                <th class="text-left py-3 px-4 font-semibold text-gray-600">总耗时</th>
                <th class="text-left py-3 px-4 font-semibold text-gray-600">状态</th>
                <th class="text-left py-3 px-4 font-semibold text-gray-600">时间</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="t in traces" :key="t.trace_id">
                <tr
                  @click="toggleTraceDetail(t.trace_id)"
                  class="border-b border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer"
                >
                  <td class="py-3 px-4 font-mono text-xs text-blue-600">{{ t.trace_id }}</td>
                  <td class="py-3 px-4 text-gray-700">
                    <div class="max-w-xl text-sm leading-relaxed">{{ t.question || '未记录问题' }}</div>
                    <div class="mt-1 text-xs text-gray-400">点击查看完整链路</div>
                  </td>
                  <td class="py-3 px-4 text-gray-600 text-xs">{{ t.user_role || t.user_id || '-' }}</td>
                  <td class="py-3 px-4 text-gray-600 text-xs">{{ t.node_count || (t.nodes ? t.nodes.length : '-') }}</td>
                  <td class="py-3 px-4 text-gray-600 text-xs">{{ formatDuration(t.duration_ms ?? t.duration) }}</td>
                  <td class="py-3 px-4">
                    <span :class="traceStatusBadge(t.status)" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium">
                      {{ t.status }}
                    </span>
                  </td>
                  <td class="py-3 px-4 text-xs text-gray-400">{{ formatDate(t.timestamp || t.time || t.created_at) }}</td>
                </tr>

                <!-- Expanded trace detail -->
                <tr v-if="expandedTraceId === t.trace_id" class="bg-blue-50/30">
                  <td colspan="7" class="py-4 px-6">
                    <div v-if="loadingTraceDetail" class="text-center text-gray-400 py-4">
                      <svg class="animate-spin h-4 w-4 mx-auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                    </div>

                    <div v-else-if="traceDetail" class="space-y-3">
                      <div class="space-y-1">
                        <h4 class="font-semibold text-gray-700 text-sm">链路节点详情</h4>
                        <p class="text-sm text-gray-600">问题：{{ traceDetail.question || t.question || '未记录问题' }}</p>
                        <p class="text-xs text-gray-400">
                          Trace ID: {{ traceDetail.trace_id || t.trace_id }}
                          <span class="ml-3">总耗时: {{ formatDuration(traceDetail.duration_ms ?? t.duration_ms) }}</span>
                        </p>
                      </div>
                      <div v-if="traceDetail.nodes && traceDetail.nodes.length > 0" class="space-y-2">
                        <div
                          v-for="(node, ni) in traceDetail.nodes"
                          :key="ni"
                          class="flex items-center space-x-4 bg-white rounded-lg p-3 border border-gray-200"
                        >
                          <span class="text-xs text-gray-400 w-8">#{{ ni + 1 }}</span>
                          <div class="flex-1 min-w-0">
                            <div class="text-sm text-gray-700 font-medium font-mono">{{ traceNodeName(node) || '-' }}</div>
                            <div class="mt-1 text-xs text-gray-400">{{ traceNodeDescription(node) }}</div>
                            <div v-if="isLlmNode(node)" class="mt-3 rounded-md bg-gray-50 border border-gray-100 p-3 text-xs text-gray-600 space-y-2">
                              <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
                                <div>
                                  <span class="text-gray-400">用途</span>
                                  <div class="font-mono text-gray-700">{{ nodeInput(node).purpose || '-' }}</div>
                                </div>
                                <div>
                                  <span class="text-gray-400">模型</span>
                                  <div class="font-mono text-gray-700">{{ nodeInput(node).model || '-' }}</div>
                                </div>
                                <div>
                                  <span class="text-gray-400">temperature</span>
                                  <div class="font-mono text-gray-700">{{ nodeInput(node).temperature ?? '-' }}</div>
                                </div>
                                <div>
                                  <span class="text-gray-400">max_tokens</span>
                                  <div class="font-mono text-gray-700">{{ nodeInput(node).max_tokens ?? '-' }}</div>
                                </div>
                              </div>
                              <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
                                <div>
                                  <span class="text-gray-400">消息数</span>
                                  <div class="font-mono text-gray-700">{{ nodeInput(node).message_count ?? '-' }}</div>
                                </div>
                                <div>
                                  <span class="text-gray-400">prompt_tokens</span>
                                  <div class="font-mono text-gray-700">{{ nodeOutput(node).usage?.prompt_tokens ?? '-' }}</div>
                                </div>
                                <div>
                                  <span class="text-gray-400">completion_tokens</span>
                                  <div class="font-mono text-gray-700">{{ nodeOutput(node).usage?.completion_tokens ?? '-' }}</div>
                                </div>
                                <div>
                                  <span class="text-gray-400">total_tokens</span>
                                  <div class="font-mono text-gray-700">{{ nodeOutput(node).usage?.total_tokens ?? '-' }}</div>
                                </div>
                              </div>
                              <div v-if="nodeOutput(node).response_preview">
                                <span class="text-gray-400">响应摘要</span>
                                <pre class="mt-1 whitespace-pre-wrap font-sans text-gray-700">{{ nodeOutput(node).response_preview }}</pre>
                              </div>
                              <div v-if="nodeOutput(node).error_message" class="text-red-600">
                                {{ nodeOutput(node).error_type }}: {{ nodeOutput(node).error_message }}
                              </div>
                            </div>
                          </div>
                          <span :class="traceStatusBadge(node.status)" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium">
                            {{ node.status || '-' }}
                          </span>
                          <span class="text-xs text-gray-400 w-20 text-right">{{ formatDuration(node.duration_ms ?? node.duration) }}</span>
                        </div>
                      </div>
                      <div v-else class="text-sm text-gray-400">无详细节点数据</div>
                      <div v-if="traceDetail.error" class="text-sm text-red-600 bg-red-50 p-2 rounded">{{ traceDetail.error }}</div>

                      <details>
                        <summary class="text-xs text-blue-600 cursor-pointer hover:text-blue-800">查看原始数据</summary>
                        <pre class="mt-2 p-3 bg-gray-50 rounded-lg text-xs text-gray-600 overflow-x-auto max-h-64">{{ JSON.stringify(traceDetail, null, 2) }}</pre>
                      </details>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Tab: Role Module Permissions -->
    <div v-if="activeTab === 'permissions'">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-4">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-md font-semibold text-gray-800">角色模块权限</h3>
            <p class="mt-1 text-xs text-gray-400">配置每个角色在知识库检索时可访问的模块范围，保存后立即对新问题生效</p>
          </div>
          <button
            @click="loadPermissions"
            :disabled="loadingPermissions"
            class="px-4 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-md transition-colors disabled:opacity-50"
          >
            {{ loadingPermissions ? '加载中...' : '刷新' }}
          </button>
        </div>
      </div>

      <div class="grid grid-cols-[260px_1fr] gap-4">
        <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <div class="px-4 py-3 border-b border-gray-100 bg-gray-50">
            <div class="text-sm font-semibold text-gray-700">角色</div>
          </div>
          <div v-if="permissionRoles.length === 0 && !loadingPermissions" class="p-5 text-sm text-gray-400 text-center">
            暂无角色配置
          </div>
          <button
            v-for="role in permissionRoles"
            :key="role.role"
            @click="selectedPermissionRole = role.role"
            :class="[
              'w-full px-4 py-3 text-left border-b border-gray-100 transition-colors',
              selectedPermissionRole === role.role ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50 text-gray-700'
            ]"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm font-medium">{{ role.label }}</span>
              <span class="text-xs text-gray-400 font-mono">{{ role.role }}</span>
            </div>
            <div class="mt-1 text-xs text-gray-400">
              <template v-if="role.role === 'admin' && roleModules(role.role).length === 0">全模块</template>
              <template v-else>{{ roleModules(role.role).length }} 个模块</template>
            </div>
          </button>
        </div>

        <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-5 min-h-[520px]">
          <div v-if="!selectedRoleConfig()" class="text-center text-gray-400 py-12">
            请选择角色
          </div>

          <div v-else>
            <div class="flex items-start justify-between gap-4 mb-5">
              <div>
                <h3 class="text-lg font-semibold text-gray-800">{{ selectedRoleConfig()?.label }}</h3>
                <p class="mt-1 text-xs text-gray-400 font-mono">{{ selectedPermissionRole }}</p>
                <p v-if="selectedPermissionRole === 'admin' && roleModules(selectedPermissionRole).length === 0" class="mt-2 text-sm text-green-600">
                  管理员当前为全模块可见
                </p>
              </div>
              <div class="flex items-center space-x-2">
                <button
                  @click="selectAllModules(selectedPermissionRole)"
                  class="px-3 py-1.5 text-xs bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-md transition-colors"
                >
                  全选
                </button>
                <button
                  @click="clearModules(selectedPermissionRole)"
                  class="px-3 py-1.5 text-xs bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-md transition-colors"
                >
                  清空
                </button>
                <button
                  @click="resetRoleModules(selectedPermissionRole)"
                  :disabled="savingPermissionRole === selectedPermissionRole"
                  class="px-3 py-1.5 text-xs bg-yellow-50 hover:bg-yellow-100 text-yellow-700 rounded-md transition-colors disabled:opacity-50"
                >
                  恢复默认
                </button>
                <button
                  @click="saveRoleModules(selectedPermissionRole)"
                  :disabled="savingPermissionRole === selectedPermissionRole"
                  class="px-4 py-1.5 text-xs font-medium bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50"
                >
                  {{ savingPermissionRole === selectedPermissionRole ? '保存中...' : '保存配置' }}
                </button>
              </div>
            </div>

            <div v-if="permissionModules.length === 0" class="text-center text-gray-400 py-12">
              当前知识库没有可配置模块
            </div>

            <div v-else class="grid grid-cols-2 xl:grid-cols-3 gap-3">
              <label
                v-for="module in permissionModules"
                :key="module"
                :class="[
                  'flex items-center justify-between gap-3 border rounded-lg px-3 py-3 cursor-pointer transition-colors',
                  isModuleChecked(selectedPermissionRole, module)
                    ? 'border-blue-300 bg-blue-50'
                    : 'border-gray-200 hover:bg-gray-50'
                ]"
              >
                <span class="text-sm text-gray-700 truncate">{{ module }}</span>
                <input
                  type="checkbox"
                  :checked="isModuleChecked(selectedPermissionRole, module)"
                  @change="toggleModule(selectedPermissionRole, module)"
                  class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                />
              </label>
            </div>

            <div class="mt-5 rounded-lg bg-gray-50 border border-gray-100 p-4">
              <div class="text-xs text-gray-400 mb-2">当前配置预览</div>
              <div class="text-sm text-gray-700 leading-relaxed">
                <template v-if="selectedPermissionRole === 'admin' && roleModules(selectedPermissionRole).length === 0">
                  该角色可检索全部模块。
                </template>
                <template v-else-if="roleModules(selectedPermissionRole).length === 0">
                  该角色不绑定业务模块，仅可检索公共知识。
                </template>
                <template v-else>
                  {{ roleModules(selectedPermissionRole).join('、') }}
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab: BadCase -->
    <div v-if="activeTab === 'badcase'">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-md font-semibold text-gray-800">BadCase 候选列表</h3>
        <button
          @click="loadBadcases"
          :disabled="loadingBadcases"
          class="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-md transition-colors"
        >
          {{ loadingBadcases ? '加载中...' : '刷新' }}
        </button>
      </div>

      <div v-if="badcases.length === 0 && !loadingBadcases" class="bg-white rounded-lg shadow-sm border border-gray-200 p-8 text-center text-gray-400">
        <p class="text-lg mb-2">暂无BadCase</p>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="bc in badcases"
          :key="bc.id || bc.feedback_id"
          class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 hover:shadow-md transition-shadow"
        >
          <div class="flex items-start justify-between">
            <div class="flex-1 min-w-0">
              <div class="flex items-center space-x-3 mb-2">
                <span class="font-mono text-xs text-blue-600">{{ bc.feedback_id || bc.id }}</span>
                <span :class="badcaseStatusBadge(bc.status)" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium">
                  {{ bc.status || 'pending' }}
                </span>
              </div>

              <div v-if="bc.question" class="mb-2">
                <p class="text-xs text-gray-400">问题:</p>
                <p class="text-sm text-gray-700">{{ truncate(bc.question, 200) }}</p>
              </div>

              <div v-if="bc.reason" class="mb-2">
                <p class="text-xs text-gray-400">原因:</p>
                <p class="text-sm text-red-600">{{ bc.reason }}</p>
              </div>

              <div v-if="bc.reason_category" class="mb-2">
                <span class="inline-flex items-center px-2 py-0.5 rounded text-xs bg-red-50 text-red-500">
                  {{ bc.reason_category }}
                </span>
              </div>

              <p class="text-xs text-gray-400">{{ formatDate(bc.created_at) }}</p>
            </div>

            <div class="flex items-center space-x-2 ml-4 flex-shrink-0">
              <button
                v-if="bc.status === 'pending'"
                @click="convertBadcase(bc.feedback_id || bc.id)"
                :disabled="convertingBadcaseId === (bc.feedback_id || bc.id)"
                class="px-3 py-1.5 text-xs font-medium bg-orange-600 text-white rounded-md hover:bg-orange-700 disabled:opacity-50 transition-colors"
              >
                {{ convertingBadcaseId === (bc.feedback_id || bc.id) ? '处理中...' : '转为BadCase' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab: Feedback Review -->
    <div v-if="activeTab === 'review'">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-4">
        <div class="flex items-center space-x-4">
          <div class="flex items-center space-x-2">
            <label class="text-sm font-medium text-gray-600">审核状态:</label>
            <select
              v-model="filterReviewStatus"
              @change="loadReviewFeedbacks"
              class="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
            >
              <option value="all">全部</option>
              <option value="pending_review">待审核</option>
              <option value="approved">已通过</option>
              <option value="rejected">已拒绝</option>
            </select>
          </div>
          <button
            @click="loadReviewFeedbacks"
            :disabled="loadingReview"
            class="px-4 py-1.5 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {{ loadingReview ? '查询中...' : '查询' }}
          </button>
        </div>
      </div>

      <div v-if="reviewFeedbacks.length === 0 && !loadingReview" class="bg-white rounded-lg shadow-sm border border-gray-200 p-8 text-center text-gray-400">
        <p class="text-lg mb-2">暂无反馈记录</p>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="fb in reviewFeedbacks"
          :key="fb.id || fb.feedback_id"
          class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 hover:shadow-md transition-shadow"
        >
          <div class="flex items-start justify-between">
            <div class="flex-1 min-w-0">
              <div class="flex items-center space-x-3 mb-2">
                <span class="text-xl">{{ fb.feedback_type === 'like' || fb.feedback === 'like' ? '👍' : '👎' }}</span>
                <span class="font-mono text-xs text-blue-600">{{ fb.answer_id }}</span>
                <span :class="reviewStatusBadge(fb.review_status)" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium">
                  <template v-if="fb.review_status === 'pending_review'">⏳ 待审核</template>
                  <template v-else-if="fb.review_status === 'approved'">✅ 已通过</template>
                  <template v-else-if="fb.review_status === 'rejected'">❌ 已拒绝</template>
                  <template v-else>{{ fb.review_status || '待审核' }}</template>
                </span>
              </div>

              <div v-if="fb.question" class="mb-2">
                <p class="text-sm text-gray-700">{{ truncate(fb.question, 200) }}</p>
              </div>

              <div v-if="(fb.feedback_type === 'dislike' || fb.feedback === 'dislike') && fb.reason" class="mb-2">
                <p class="text-sm text-red-600">{{ fb.reason }}</p>
                <span v-if="fb.reason_category" class="inline-flex items-center mt-1 px-2 py-0.5 rounded text-xs bg-red-50 text-red-500">
                  {{ fb.reason_category }}
                </span>
              </div>

              <p class="text-xs text-gray-400">{{ formatDate(fb.created_at) }}</p>
            </div>

            <div class="flex items-center space-x-2 ml-4 flex-shrink-0">
              <button
                @click="approveReview(fb.id || fb.feedback_id)"
                :disabled="actionReviewId === (fb.id || fb.feedback_id) || fb.review_status === 'approved'"
                class="px-3 py-1.5 text-xs font-medium bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 transition-colors"
              >
                {{ actionReviewId === (fb.id || fb.feedback_id) ? '处理中...' : '通过' }}
              </button>
              <button
                @click="convertReviewToBadcase(fb.id || fb.feedback_id)"
                :disabled="actionReviewId === (fb.id || fb.feedback_id)"
                class="px-3 py-1.5 text-xs font-medium bg-orange-600 text-white rounded-md hover:bg-orange-700 disabled:opacity-50 transition-colors"
              >
                BadCase
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
