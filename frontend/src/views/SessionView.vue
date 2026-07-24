<script setup lang="ts">
import { ref } from 'vue'
import { sessionApi } from '@/api/session'

const sessionIdInput = ref('')
const shortTermHistory = ref<any[]>([])
const mediumTermSummary = ref<any>(null)
const loadingSession = ref(false)

const profileUserId = ref('')
const userProfile = ref<any>(null)
const loadingProfile = ref(false)

// Load session history & summary
async function loadSession() {
  const sid = sessionIdInput.value.trim()
  if (!sid) {
    alert('请输入会话ID')
    return
  }

  loadingSession.value = true
  shortTermHistory.value = []
  mediumTermSummary.value = null

  try {
    const [histRes, sumRes] = await Promise.all([
      sessionApi.history(sid),
      sessionApi.summary(sid),
    ])
    shortTermHistory.value = histRes.data.history || histRes.data.messages || histRes.data || []
    mediumTermSummary.value = sumRes.data
  } catch (e: any) {
    alert('加载失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loadingSession.value = false
  }
}

// Load user profile
async function loadUserProfile() {
  const uid = profileUserId.value.trim()
  if (!uid) {
    alert('请输入用户ID')
    return
  }

  loadingProfile.value = true
  userProfile.value = null

  try {
    const res = await sessionApi.userProfile(uid)
    const data = res.data
    userProfile.value = {
      userId: data.user_id || data.userId,
      role: data.role || data.profile?.role,
      schoolName: data.school_name || data.profile?.school_name,
      preferredResponseStyle: data.preferred_response_style || data.profile?.preferred_response_style,
      totalSessions: data.total_sessions ?? data.profile?.total_sessions ?? 0,
      totalQuestions: data.total_questions ?? data.profile?.total_questions ?? 0,
      avgSatisfaction: data.avg_satisfaction ?? data.profile?.avg_satisfaction,
      needsHumanPriority: data.needs_human_priority ?? data.profile?.needs_human_priority,
      preferences: data.preferences || data.profile?.preferences,
      stats: data.stats || data.profile?.stats || {},
      facts: data.facts || [],
      frequentQuestions: data.frequent_questions || data.frequentQuestions || [],
      _raw: data,
    }
  } catch (e: any) {
    alert('加载失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loadingProfile.value = false
  }
}

function formatDate(ts: string | number): string {
  if (!ts) return '-'
  return new Date(ts).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="space-y-4">
    <!-- Session Lookup -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <h2 class="text-lg font-semibold text-gray-800 mb-3">会话查询</h2>
      <div class="flex items-center space-x-3">
        <input
          v-model="sessionIdInput"
          type="text"
          placeholder="输入会话ID..."
          class="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
        />
        <button
          @click="loadSession"
          :disabled="loadingSession"
          class="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {{ loadingSession ? '加载中...' : '加载' }}
        </button>
      </div>
    </div>

    <!-- Short-term Memory Panel -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-md font-semibold text-gray-800">短期记忆 (最近5轮)</h3>
        <span class="text-xs text-gray-400">{{ shortTermHistory.length }} 条消息</span>
      </div>

      <div v-if="shortTermHistory.length === 0 && !loadingSession" class="text-center text-gray-400 py-4">
        <p class="text-sm">暂无数据，请先查询会话</p>
      </div>

      <div v-else-if="loadingSession" class="text-center text-gray-400 py-4">
        <svg class="animate-spin h-5 w-5 mx-auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="(msg, mi) in shortTermHistory"
          :key="mi"
          :class="[
            'rounded-lg p-3 border',
            msg.role === 'user' ? 'bg-blue-50 border-blue-200' : 'bg-gray-50 border-gray-200'
          ]"
        >
          <div class="flex items-center space-x-2 mb-1">
            <span class="text-xs font-semibold" :class="msg.role === 'user' ? 'text-blue-600' : 'text-gray-600'">
              {{ msg.role === 'user' ? '用户' : '助手' }}
            </span>
            <span class="text-xs text-gray-400">第{{ mi + 1 }}轮</span>
          </div>
          <p class="text-sm text-gray-700 whitespace-pre-wrap">{{ msg.content || msg.text }}</p>
        </div>
      </div>
    </div>

    <!-- Medium-term Memory Panel -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <h3 class="text-md font-semibold text-gray-800 mb-3">中期记忆 (压缩摘要)</h3>

      <div v-if="!mediumTermSummary && !loadingSession" class="text-center text-gray-400 py-4">
        <p class="text-sm">暂无数据，请先查询会话</p>
      </div>

      <div v-else-if="loadingSession" class="text-center text-gray-400 py-4">
        <svg class="animate-spin h-5 w-5 mx-auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      </div>

      <div v-else class="space-y-3">
        <div class="flex items-center space-x-2 text-xs text-gray-400 mb-2">
          <span>版本: {{ mediumTermSummary?.version || '-' }}</span>
          <span>|</span>
          <span>更新: {{ formatDate(mediumTermSummary?.updated_at) }}</span>
        </div>
        <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <p class="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{{ mediumTermSummary?.summary || mediumTermSummary?.content || '-' }}</p>
        </div>

        <!-- Full JSON view -->
        <details class="mt-3">
          <summary class="text-xs text-blue-600 cursor-pointer hover:text-blue-800">查看原始数据</summary>
          <pre class="mt-2 p-3 bg-gray-50 rounded-lg text-xs text-gray-600 overflow-x-auto max-h-64">{{ JSON.stringify(mediumTermSummary, null, 2) }}</pre>
        </details>
      </div>
    </div>

    <!-- Long-term Memory Panel -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <h3 class="text-md font-semibold text-gray-800 mb-3">长期记忆 (用户画像)</h3>

      <div class="flex items-center space-x-3 mb-4">
        <input
          v-model="profileUserId"
          type="text"
          placeholder="输入用户ID..."
          class="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none flex-1 max-w-xs"
        />
        <button
          @click="loadUserProfile"
          :disabled="loadingProfile"
          class="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {{ loadingProfile ? '加载中...' : '查询画像' }}
        </button>
      </div>

      <div v-if="!userProfile && !loadingProfile" class="text-center text-gray-400 py-4">
        <p class="text-sm">请输入用户ID查询长期记忆</p>
      </div>

      <div v-else-if="loadingProfile" class="text-center text-gray-400 py-4">
        <svg class="animate-spin h-5 w-5 mx-auto" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      </div>

      <div v-else class="space-y-4">
        <!-- Profile Info -->
        <div class="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <h4 class="text-sm font-semibold text-gray-700 mb-2">基本信息</h4>
          <div class="grid grid-cols-2 gap-3 text-sm text-gray-600">
            <div>角色: <span class="text-gray-800">{{ userProfile?.role || '-' }}</span></div>
            <div>学校: <span class="text-gray-800">{{ userProfile?.schoolName || '-' }}</span></div>
            <div>回答风格: <span class="text-gray-800">{{ userProfile?.preferredResponseStyle || '-' }}</span></div>
            <div>总会话: <span class="text-gray-800">{{ userProfile?.totalSessions }}</span></div>
            <div>总问题: <span class="text-gray-800">{{ userProfile?.totalQuestions }}</span></div>
            <div>满意度: <span class="text-gray-800">{{ userProfile?.avgSatisfaction?.toFixed(2) || '-' }}</span></div>
            <div>
              优先人工:
              <span :class="userProfile?.needsHumanPriority ? 'text-red-600 font-semibold' : 'text-green-600'">
                {{ userProfile?.needsHumanPriority ? '是' : '否' }}
              </span>
            </div>
          </div>
          <div v-if="userProfile?.preferences" class="mt-2 pt-2 border-t border-gray-200">
            <span class="text-xs text-gray-400">偏好设置:</span>
            <span class="text-xs text-gray-600 ml-2">{{ JSON.stringify(userProfile.preferences) }}</span>
          </div>
        </div>

        <!-- Facts List -->
        <div v-if="userProfile?.facts && userProfile.facts.length > 0" class="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <h4 class="text-sm font-semibold text-gray-700 mb-2">已知事实 ({{ userProfile.facts.length }})</h4>
          <ul class="space-y-1.5">
            <li v-for="(fact, fi) in userProfile.facts" :key="fi" class="text-sm text-gray-600 flex items-start space-x-2">
              <span v-if="fact.type" class="text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded flex-shrink-0">{{ fact.type }}</span>
              <span>{{ fact.content || fact }}</span>
              <span v-if="fact.confidence" class="text-xs text-gray-400">({{ (fact.confidence * 100).toFixed(0) }}%)</span>
            </li>
          </ul>
        </div>

        <!-- Frequent Questions -->
        <div v-if="userProfile?.frequentQuestions && userProfile.frequentQuestions.length > 0" class="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <h4 class="text-sm font-semibold text-gray-700 mb-2">常见问题 ({{ userProfile.frequentQuestions.length }})</h4>
          <ul class="space-y-1.5">
            <li v-for="(q, qi) in userProfile.frequentQuestions" :key="qi" class="text-sm text-gray-600 flex items-start space-x-2">
              <span class="text-blue-500">Q:</span>
              <span>{{ q.question || q }}</span>
              <span v-if="q.frequency" class="text-xs text-gray-400">频率: {{ q.frequency }}</span>
            </li>
          </ul>
        </div>

        <!-- Full JSON -->
        <details class="mt-3">
          <summary class="text-xs text-blue-600 cursor-pointer hover:text-blue-800">查看原始数据</summary>
          <pre class="mt-2 p-3 bg-gray-50 rounded-lg text-xs text-gray-600 overflow-x-auto max-h-64">{{ JSON.stringify(userProfile._raw || userProfile, null, 2) }}</pre>
        </details>
      </div>
    </div>
  </div>
</template>
