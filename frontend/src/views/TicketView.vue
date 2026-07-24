<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ticketApi } from '@/api/ticket'

const filterStatus = ref('all')
const filterUserId = ref('')
const tickets = ref<any[]>([])
const loading = ref(false)
const expandedId = ref<string | null>(null)
const submittingId = ref<string | null>(null)

async function loadTickets() {
  loading.value = true
  try {
    const params: any = {}
    if (filterStatus.value && filterStatus.value !== 'all') {
      params.status = filterStatus.value
    }
    if (filterUserId.value.trim()) {
      params.user_id = filterUserId.value.trim()
    }
    const res = await ticketApi.list(params)
    tickets.value = res.data.tickets || res.data || []
  } catch (e: any) {
    console.error('加载工单失败:', e)
  } finally {
    loading.value = false
  }
}

function toggleExpand(draftId: string) {
  expandedId.value = expandedId.value === draftId ? null : draftId
}

async function submitTicket(draftId: string) {
  submittingId.value = draftId
  try {
    await ticketApi.submit(draftId)
    alert('工单已提交!')
    loadTickets()
  } catch (e: any) {
    alert('提交失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    submittingId.value = null
  }
}

function statusBadge(status: string) {
  switch (status) {
    case 'draft': return 'bg-yellow-100 text-yellow-700'
    case 'submitted': return 'bg-blue-100 text-blue-700'
    case 'processing': return 'bg-purple-100 text-purple-700'
    case 'resolved': return 'bg-green-100 text-green-700'
    case 'cancelled': return 'bg-gray-100 text-gray-500'
    default: return 'bg-gray-100 text-gray-600'
  }
}

function truncate(text: string, len: number): string {
  if (!text) return ''
  return text.length > len ? text.slice(0, len) + '...' : text
}

function formatDate(ts: string | number): string {
  if (!ts) return '-'
  const d = new Date(ts)
  return d.toLocaleString('zh-CN')
}

onMounted(() => {
  loadTickets()
})
</script>

<template>
  <div>
    <!-- Filter Bar -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-4">
      <div class="flex items-center space-x-4">
        <div class="flex items-center space-x-2">
          <label class="text-sm font-medium text-gray-600">状态:</label>
          <select
            v-model="filterStatus"
            @change="loadTickets"
            class="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
          >
            <option value="all">全部</option>
            <option value="draft">草稿</option>
            <option value="submitted">已提交</option>
            <option value="processing">处理中</option>
            <option value="resolved">已解决</option>
          </select>
        </div>

        <div class="flex items-center space-x-2">
          <label class="text-sm font-medium text-gray-600">用户ID:</label>
          <input
            v-model="filterUserId"
            type="text"
            placeholder="输入用户ID..."
            class="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none w-40"
          />
        </div>

        <button
          @click="loadTickets"
          :disabled="loading"
          class="px-4 py-1.5 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {{ loading ? '查询中...' : '查询' }}
        </button>
      </div>
    </div>

    <!-- Ticket Table -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      <div v-if="tickets.length === 0 && !loading" class="text-center text-gray-400 py-12">
        <p class="text-lg mb-2">暂无工单</p>
        <p class="text-sm">工单将在用户从低置信度回答中创建</p>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-200 bg-gray-50">
              <th class="text-left py-3 px-4 font-semibold text-gray-600">工单ID</th>
              <th class="text-left py-3 px-4 font-semibold text-gray-600">状态</th>
              <th class="text-left py-3 px-4 font-semibold text-gray-600">原始问题</th>
              <th class="text-left py-3 px-4 font-semibold text-gray-600">分类</th>
              <th class="text-left py-3 px-4 font-semibold text-gray-600">优先级</th>
              <th class="text-left py-3 px-4 font-semibold text-gray-600">用户角色</th>
              <th class="text-left py-3 px-4 font-semibold text-gray-600">创建时间</th>
              <th class="text-left py-3 px-4 font-semibold text-gray-600">操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="t in tickets" :key="t.draft_id || t.id">
              <tr
                @click="toggleExpand(t.draft_id || t.id)"
                class="border-b border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer"
              >
                <td class="py-3 px-4 font-mono text-xs text-blue-600">{{ t.draft_id || t.id }}</td>
                <td class="py-3 px-4">
                  <span :class="statusBadge(t.status)" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium">
                    <template v-if="t.status === 'draft'">⏳ 草稿</template>
                    <template v-else-if="t.status === 'submitted'">📤 已提交</template>
                    <template v-else-if="t.status === 'processing'">🔄 处理中</template>
                    <template v-else-if="t.status === 'resolved'">✅ 已解决</template>
                    <template v-else-if="t.status === 'cancelled'">❌ 已取消</template>
                    <template v-else>{{ t.status }}</template>
                  </span>
                </td>
                <td class="py-3 px-4 text-gray-700 max-w-xs">{{ truncate(t.original_question || t.question || '', 100) }}</td>
                <td class="py-3 px-4 text-gray-600">{{ t.category || t.suggested_category || '-' }}</td>
                <td class="py-3 px-4">
                  <span :class="{
                    'bg-red-100 text-red-700': t.priority === 'high',
                    'bg-yellow-100 text-yellow-700': t.priority === 'medium',
                    'bg-green-100 text-green-700': t.priority === 'low',
                    'bg-gray-100 text-gray-500': !t.priority,
                  }" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium">
                    {{ t.priority || '-' }}
                  </span>
                </td>
                <td class="py-3 px-4 text-gray-600">{{ t.user_role || '-' }}</td>
                <td class="py-3 px-4 text-xs text-gray-400">{{ formatDate(t.created_at) }}</td>
                <td class="py-3 px-4">
                  <button
                    v-if="t.status === 'draft'"
                    @click.stop="submitTicket(t.draft_id || t.id)"
                    :disabled="submittingId === (t.draft_id || t.id)"
                    class="px-3 py-1 text-xs font-medium bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
                  >
                    {{ submittingId === (t.draft_id || t.id) ? '提交中...' : '提交' }}
                  </button>
                </td>
              </tr>

              <!-- Expanded details -->
              <tr v-if="expandedId === (t.draft_id || t.id)" class="bg-blue-50/30">
                <td colspan="8" class="py-4 px-6">
                  <div class="space-y-3 text-sm">
                    <div>
                      <span class="font-semibold text-gray-600">完整问题:</span>
                      <p class="mt-1 text-gray-800 whitespace-pre-wrap">{{ t.original_question || t.question }}</p>
                    </div>
                    <div v-if="t.suggested_category">
                      <span class="font-semibold text-gray-600">建议分类:</span>
                      <span class="ml-2 text-gray-700">{{ t.suggested_category }}</span>
                    </div>
                    <div v-if="t.trace_id">
                      <span class="font-semibold text-gray-600">Trace ID:</span>
                      <span class="ml-2 font-mono text-xs text-blue-600">{{ t.trace_id }}</span>
                    </div>
                    <div v-if="t.assigned_to">
                      <span class="font-semibold text-gray-600">分配给:</span>
                      <span class="ml-2 text-gray-700">{{ t.assigned_to }}</span>
                    </div>
                    <div v-if="t.resolution">
                      <span class="font-semibold text-gray-600">解决方案:</span>
                      <p class="mt-1 text-gray-800">{{ t.resolution }}</p>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
