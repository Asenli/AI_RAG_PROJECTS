<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { feedbackApi } from '@/api/feedback'
import { adminApi } from '@/api/admin'

const stats = reactive({
  total: 0,
  likes: 0,
  dislikes: 0,
  satisfaction_rate: 0,
})
const loadingStats = ref(false)

const filterType = ref('all')
const filterStatus = ref('all')
const filterReason = ref('')
const feedbacks = ref<any[]>([])
const loadingList = ref(false)
const actionLoading = ref<string | null>(null)

async function loadStats() {
  loadingStats.value = true
  try {
    const res = await feedbackApi.stats()
    Object.assign(stats, res.data)
  } catch (e: any) {
    console.error('加载统计失败:', e)
  } finally {
    loadingStats.value = false
  }
}

async function loadFeedbackList() {
  loadingList.value = true
  try {
    const params: any = { limit: 200 }
    if (filterType.value !== 'all') {
      params.feedback_type = filterType.value
    }
    if (filterStatus.value !== 'all') {
      params.review_status = filterStatus.value
    }
    if (filterReason.value.trim()) {
      params.reason_category = filterReason.value.trim()
    }
    const res = await adminApi.feedbackList(params)
    feedbacks.value = res.data.feedbacks || res.data || []
  } catch (e: any) {
    console.error('加载反馈列表失败:', e)
  } finally {
    loadingList.value = false
  }
}

async function approveFeedback(feedbackId: string) {
  actionLoading.value = feedbackId
  try {
    await adminApi.reviewFeedback(feedbackId)
    alert('已审核通过')
    loadFeedbackList()
    loadStats()
  } catch (e: any) {
    alert('审核失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    actionLoading.value = null
  }
}

async function convertToBadcase(feedbackId: string) {
  actionLoading.value = feedbackId
  try {
    await adminApi.convertBadcase(feedbackId)
    alert('已转为BadCase')
    loadFeedbackList()
  } catch (e: any) {
    alert('转换失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    actionLoading.value = null
  }
}

function formatDate(ts: string | number): string {
  if (!ts) return '-'
  return new Date(ts).toLocaleString('zh-CN')
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

onMounted(() => {
  loadStats()
  loadFeedbackList()
})
</script>

<template>
  <div>
    <!-- Stats Bar -->
    <div class="grid grid-cols-4 gap-4 mb-4">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-xs text-gray-500">总反馈数</p>
            <p class="text-2xl font-bold text-gray-800">{{ stats.total }}</p>
          </div>
          <span class="text-2xl text-gray-300">📊</span>
        </div>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-xs text-gray-500">好评</p>
            <p class="text-2xl font-bold text-green-600">{{ stats.likes }}</p>
          </div>
          <span class="text-2xl">👍</span>
        </div>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-xs text-gray-500">差评</p>
            <p class="text-2xl font-bold text-red-600">{{ stats.dislikes }}</p>
          </div>
          <span class="text-2xl">👎</span>
        </div>
      </div>
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-xs text-gray-500">满意度</p>
            <p class="text-2xl font-bold text-blue-600">{{ (stats.satisfaction_rate * 100).toFixed(1) }}%</p>
          </div>
          <span class="text-2xl">📈</span>
        </div>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-4">
      <div class="flex items-center space-x-4">
        <div class="flex items-center space-x-2">
          <label class="text-sm font-medium text-gray-600">反馈类型:</label>
          <select
            v-model="filterType"
            @change="loadFeedbackList"
            class="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
          >
            <option value="all">全部</option>
            <option value="like">好评</option>
            <option value="dislike">差评</option>
          </select>
        </div>

        <div class="flex items-center space-x-2">
          <label class="text-sm font-medium text-gray-600">审核状态:</label>
          <select
            v-model="filterStatus"
            @change="loadFeedbackList"
            class="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
          >
            <option value="all">全部</option>
            <option value="pending_review">待审核</option>
            <option value="approved">已通过</option>
            <option value="rejected">已拒绝</option>
          </select>
        </div>

        <div class="flex items-center space-x-2">
          <label class="text-sm font-medium text-gray-600">原因分类:</label>
          <input
            v-model="filterReason"
            type="text"
            placeholder="incorrect/misleading..."
            class="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none w-40"
          />
        </div>

        <button
          @click="loadFeedbackList"
          :disabled="loadingList"
          class="px-4 py-1.5 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {{ loadingList ? '查询中...' : '查询' }}
        </button>
      </div>
    </div>

    <!-- Feedback List -->
    <div v-if="feedbacks.length === 0 && !loadingList" class="bg-white rounded-lg shadow-sm border border-gray-200 p-8 text-center text-gray-400">
      <p class="text-lg mb-2">暂无反馈</p>
    </div>

    <div v-else class="space-y-3">
      <div
        v-for="fb in feedbacks"
        :key="fb.id || fb.feedback_id"
        class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 hover:shadow-md transition-shadow"
      >
        <div class="flex items-start justify-between">
          <div class="flex-1 min-w-0">
            <div class="flex items-center space-x-3 mb-2">
              <!-- Feedback type icon -->
              <span class="text-xl">{{ fb.feedback_type === 'like' ? '👍' : '👎' }}</span>
              <span class="font-mono text-xs text-blue-600">答案ID: {{ fb.answer_id }}</span>
              <span class="text-xs text-gray-400">{{ fb.user_id || fb.user_role || '-' }}</span>
              <span :class="reviewStatusBadge(fb.review_status)" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium">
                <template v-if="fb.review_status === 'pending_review'">⏳ 待审核</template>
                <template v-else-if="fb.review_status === 'approved'">✅ 已通过</template>
                <template v-else-if="fb.review_status === 'rejected'">❌ 已拒绝</template>
                <template v-else>{{ fb.review_status || '待审核' }}</template>
              </span>
              <span v-if="fb.is_badcase_candidate" class="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">BadCase候选</span>
            </div>

            <!-- Question snippet -->
            <div v-if="fb.question" class="mb-2">
              <p class="text-xs text-gray-400">问题:</p>
              <p class="text-sm text-gray-700">{{ truncate(fb.question, 200) }}</p>
            </div>

            <!-- Dislike reason -->
            <div v-if="fb.feedback_type === 'dislike' && fb.reason" class="mb-2">
              <p class="text-xs text-gray-400">差评原因:</p>
              <p class="text-sm text-red-600">{{ fb.reason }}</p>
              <span v-if="fb.reason_category" class="inline-flex items-center mt-1 px-2 py-0.5 rounded text-xs bg-red-50 text-red-500">
                {{ fb.reason_category }}
              </span>
            </div>

            <!-- Answer text -->
            <div v-if="fb.llm_answer" class="mb-2">
              <p class="text-xs text-gray-400">LLM回答:</p>
              <p class="text-sm text-gray-600">{{ truncate(fb.llm_answer, 150) }}</p>
            </div>

            <p class="text-xs text-gray-400 mt-2">{{ formatDate(fb.created_at) }}</p>
          </div>

          <!-- Actions -->
          <div class="flex items-center space-x-2 ml-4 flex-shrink-0">
            <button
              @click="approveFeedback(fb.id || fb.feedback_id)"
              :disabled="actionLoading === (fb.id || fb.feedback_id) || fb.review_status === 'approved'"
              class="px-3 py-1.5 text-xs font-medium bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              {{ actionLoading === (fb.id || fb.feedback_id) ? '处理中...' : '通过' }}
            </button>
            <button
              v-if="!fb.is_badcase_candidate"
              @click="convertToBadcase(fb.id || fb.feedback_id)"
              :disabled="actionLoading === (fb.id || fb.feedback_id)"
              class="px-3 py-1.5 text-xs font-medium bg-orange-600 text-white rounded-md hover:bg-orange-700 disabled:opacity-50 transition-colors"
            >
              BadCase
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
