<script setup lang="ts">
import { ref, nextTick, watch, onMounted } from 'vue'
import { useChatStore, type ChatMessage } from '@/stores/chat'
import { useUserStore } from '@/stores/user'
import { chatApi, type ChatAskParams } from '@/api/chat'
import { feedbackApi } from '@/api/feedback'
import { ticketApi } from '@/api/ticket'
import { sessionApi } from '@/api/session'

const chatStore = useChatStore()
const userStore = useUserStore()

const question = ref('')
const creatingSession = ref(false)
const loadingSessions = ref(false)
const switchingSession = ref<string | null>(null)
const submittingTicket = ref<string | null>(null)
const feedbackLoading = ref<string | null>(null)
const chatContainer = ref<HTMLDivElement | null>(null)

interface SessionListItem {
  session_id: string
  title: string
  preview: string
  message_count: number
  created_at: string
  updated_at: string
}

const sessions = ref<SessionListItem[]>([])

// Create new session
async function createSession() {
  creatingSession.value = true
  try {
    const res = await sessionApi.create({
      user_id: userStore.userId,
      user_role: userStore.userRole,
      school_id: userStore.schoolId,
    })
    userStore.setSession(res.data.session_id)
    chatStore.clearMessages()
    await loadSessionList()
  } catch (e: any) {
    console.error('Failed to create session:', e)
    alert(e.userMessage || '创建会话失败，请稍后再试。')
  } finally {
    creatingSession.value = false
  }
}

// Clear chat
function clearChat() {
  chatStore.clearMessages()
}

async function loadSessionList() {
  loadingSessions.value = true
  try {
    const res = await sessionApi.list(userStore.userId, 50)
    sessions.value = res.data.sessions || []
  } catch (e: any) {
    console.error('Failed to load sessions:', e)
  } finally {
    loadingSessions.value = false
  }
}

function parseTimestamp(value?: string): number {
  if (!value) return Date.now()
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? Date.now() : parsed
}

function toChatMessage(msg: any, index: number): ChatMessage {
  const metadata = msg.metadata || {}
  const role = msg.role === 'assistant' ? 'assistant' : 'user'
  return {
    id: `${role}_${parseTimestamp(msg.timestamp)}_${index}`,
    role,
    content: msg.content || '',
    traceId: metadata.trace_id,
    answerId: metadata.answer_id,
    sources: metadata.sources || [],
    needTicket: metadata.need_ticket || false,
    ticketDraft: metadata.ticket_draft || null,
    durationMs: metadata.duration_ms,
    timestamp: parseTimestamp(msg.timestamp),
  }
}

async function selectSession(item: SessionListItem) {
  if (chatStore.loading || switchingSession.value) return
  switchingSession.value = item.session_id
  try {
    userStore.setSession(item.session_id)
    const res = await sessionApi.history(item.session_id)
    const history = res.data.history || []
    chatStore.setMessages(history.map(toChatMessage))
    await scrollToBottom()
  } catch (e: any) {
    console.error('Failed to switch session:', e)
    alert(e.userMessage || '加载历史对话失败，请稍后再试。')
  } finally {
    switchingSession.value = null
  }
}

// Send question
async function sendQuestion() {
  const q = question.value.trim()
  if (!q || chatStore.loading) return

  if (!userStore.sessionId) {
    await createSession()
    if (!userStore.sessionId) return
  }

  // Add user message
  const userMsgId = 'msg_' + Date.now()
  chatStore.addMessage({
    id: userMsgId,
    role: 'user',
    content: q,
    timestamp: Date.now(),
  })
  question.value = ''

  chatStore.loading = true
  await scrollToBottom()

  try {
    const params: ChatAskParams = {
      company_id: userStore.companyId || '1',
      session_id: userStore.sessionId,
      question: q,
      user_id: userStore.userId,
      user_role: userStore.userRole,
      school_id: userStore.schoolId,
    }
    const res = await chatApi.ask(params)
    const data = res.data

    const assistantMsgId = 'msg_' + Date.now() + '_assistant'
    chatStore.addMessage({
      id: assistantMsgId,
      role: 'assistant',
      content: data.answer || '',
      traceId: data.trace_id,
      answerId: data.answer_id,
      sources: data.sources || [],
      needTicket: data.need_ticket || false,
      ticketDraft: data.ticket_draft || null,
      durationMs: data.duration_ms,
      timestamp: Date.now(),
    })
    await loadSessionList()
    await scrollToBottom()
  } catch (e: any) {
    console.error('Chat error:', e)
    const traceText = e.traceId ? `\n\nTrace ID：${e.traceId}` : ''
    chatStore.addMessage({
      id: 'msg_error_' + Date.now(),
      role: 'assistant',
      content: `${e.userMessage || '抱歉，系统暂时无法处理您的请求，请稍后再试。'}${traceText}`,
      traceId: e.traceId,
      timestamp: Date.now(),
    })
  } finally {
    chatStore.loading = false
  }
}

// Submit feedback
async function submitFeedback(msg: any, type: 'like' | 'dislike') {
  if (feedbackLoading.value || !msg.answerId) return
  feedbackLoading.value = msg.id
  try {
    const base = {
      answer_id: msg.answerId,
      trace_id: msg.traceId || '',
      session_id: userStore.sessionId,
      user_id: userStore.userId,
      user_role: userStore.userRole,
      company_id: userStore.companyId || '1',
      question: getPreviousQuestion(msg),
      llm_answer: msg.content,
      retrieved_sources: msg.sources || [],
    }
    if (type === 'like') {
      await feedbackApi.like(base)
    } else {
      const reason = prompt('请输入差评原因(可选):') || ''
      const reasonCategory = prompt('原因分类(可选, 如: incorrect/misleading/outdated):') || ''
      await feedbackApi.dislike({
        ...base,
        reason,
        reason_category: reasonCategory,
      })
    }
    alert(type === 'like' ? '感谢您的反馈!' : '已记录差评')
  } catch (e: any) {
    alert('反馈提交失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    feedbackLoading.value = null
  }
}

function getPreviousQuestion(msg: any): string {
  const msgs = chatStore.messages
  const idx = msgs.findIndex((m) => m.id === msg.id)
  if (idx > 0 && msgs[idx - 1].role === 'user') {
    return msgs[idx - 1].content
  }
  return ''
}

// Submit ticket
async function submitTicket(msg: any) {
  const draftId = msg.ticketDraft?.draft_id
  if (!draftId || submittingTicket.value) return
  submittingTicket.value = msg.id
  try {
    await ticketApi.submit(draftId)
    alert('工单已提交!')
    msg.needTicket = false
  } catch (e: any) {
    alert('工单提交失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    submittingTicket.value = null
  }
}

async function scrollToBottom() {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

// Keyboard shortcut: Ctrl+Enter to send
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && e.ctrlKey) {
    e.preventDefault()
    sendQuestion()
  }
}

// Source score color
function scoreColor(score: number): string {
  if (score >= 0.8) return 'bg-green-100 text-green-700'
  if (score >= 0.65) return 'bg-yellow-100 text-yellow-700'
  return 'bg-red-100 text-red-700'
}

function formatDuration(ms?: number): string {
  if (!ms && ms !== 0) return '-'
  const totalSeconds = Math.round(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes > 0) {
    return `${minutes}分${seconds}秒`
  }
  return `${seconds}秒`
}

function formatSessionTime(value?: string): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  const time = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  if (sameDay) return time
  return `${date.getMonth() + 1}/${date.getDate()} ${time}`
}

watch(
  () => [userStore.companyId, userStore.userId],
  async () => {
    userStore.setSession('')
    chatStore.clearMessages()
    await loadSessionList()
  }
)

onMounted(loadSessionList)
</script>

<template>
  <div class="flex h-[calc(100vh-180px)] gap-4">
    <!-- Left Sidebar - Session Controls -->
    <aside class="w-80 flex-shrink-0 flex flex-col space-y-3">
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <h3 class="text-sm font-semibold text-gray-700 mb-3">会话控制</h3>

        <div class="space-y-3">
          <button
            @click="createSession"
            :disabled="creatingSession"
            class="w-full py-2 px-4 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {{ creatingSession ? '创建中...' : '创建会话' }}
          </button>

          <div v-if="userStore.sessionId" class="text-xs text-gray-500">
            <span class="block">会话ID:</span>
            <span class="block font-mono text-blue-600 break-all">{{ userStore.sessionId }}</span>
          </div>

          <button
            @click="clearChat"
            class="w-full py-2 px-4 bg-gray-100 text-gray-600 text-sm font-medium rounded-lg hover:bg-gray-200 transition-colors"
          >
            清空当前显示
          </button>
        </div>
      </div>

      <!-- Session History -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4 flex-1 min-h-0 flex flex-col">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-gray-700">历史对话</h3>
          <button
            @click="loadSessionList"
            :disabled="loadingSessions"
            class="text-xs text-blue-600 hover:text-blue-700 disabled:text-gray-400"
          >
            {{ loadingSessions ? '刷新中' : '刷新' }}
          </button>
        </div>

        <div v-if="loadingSessions && sessions.length === 0" class="text-center text-xs text-gray-400 py-5">
          加载中...
        </div>

        <div v-else-if="sessions.length === 0" class="text-center text-xs text-gray-400 py-5">
          暂无历史会话
        </div>

        <div v-else class="space-y-2 overflow-y-auto pr-1">
          <button
            v-for="item in sessions"
            :key="item.session_id"
            @click="selectSession(item)"
            :disabled="chatStore.loading || switchingSession === item.session_id"
            :class="[
              'w-full text-left px-3 py-2 rounded-lg border transition-colors disabled:cursor-not-allowed',
              userStore.sessionId === item.session_id
                ? 'border-blue-300 bg-blue-50'
                : 'border-gray-200 bg-white hover:bg-gray-50'
            ]"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm font-medium text-gray-800 truncate">
                {{ item.title || '新会话' }}
              </span>
              <span class="text-[11px] text-gray-400 flex-shrink-0">
                {{ formatSessionTime(item.updated_at || item.created_at) }}
              </span>
            </div>
            <div class="mt-1 text-xs text-gray-500 truncate">
              {{ item.preview || '尚无消息' }}
            </div>
            <div class="mt-1 text-[11px] text-gray-400 font-mono">
              {{ item.message_count || 0 }} 条 · {{ item.session_id }}
            </div>
          </button>
        </div>
      </div>

      <!-- Info Card -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <h3 class="text-sm font-semibold text-gray-700 mb-2">当前用户</h3>
        <div class="text-xs text-gray-500 space-y-1">
          <div>角色: <span class="text-gray-700">{{ userStore.currentRole?.icon }} {{ userStore.currentRole?.label }}</span></div>
          <div>公司ID: <span class="text-gray-700 font-mono">{{ userStore.companyId }}</span></div>
          <div>用户ID: <span class="text-gray-700 font-mono">{{ userStore.userId }}</span></div>
          <div>学校ID: <span class="text-gray-700 font-mono">{{ userStore.schoolId }}</span></div>
        </div>
      </div>
    </aside>

    <!-- Main Chat Area -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- Messages -->
      <div
        ref="chatContainer"
        class="flex-1 overflow-y-auto space-y-4 p-4 bg-white rounded-lg shadow-sm border border-gray-200"
      >
        <div v-if="chatStore.messages.length === 0" class="flex items-center justify-center h-full text-gray-400">
          <div class="text-center">
            <div class="text-4xl mb-3">💬</div>
            <p class="text-lg">输入问题开始测试</p>
            <p class="text-sm mt-1">按 Ctrl+Enter 发送</p>
          </div>
        </div>

        <div
          v-for="msg in chatStore.messages"
          :key="msg.id"
          class="animate-fade-in"
        >
          <!-- User Message -->
          <div v-if="msg.role === 'user'" class="flex justify-end">
            <div class="max-w-[70%] bg-blue-500 text-white rounded-2xl rounded-br-md px-4 py-3">
              <p class="text-sm whitespace-pre-wrap">{{ msg.content }}</p>
            </div>
          </div>

          <!-- Assistant Message -->
          <div v-else class="flex justify-start">
            <div class="max-w-[85%] bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
              <!-- Answer text -->
              <p class="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">{{ msg.content }}</p>

              <!-- Trace info -->
              <div v-if="msg.traceId" class="mt-2 text-xs text-gray-400 font-mono">
                trace: {{ msg.traceId }}
                <span v-if="msg.durationMs" class="ml-2">耗时: {{ formatDuration(msg.durationMs) }}</span>
              </div>

              <!-- Source Citations -->
              <div v-if="msg.sources && msg.sources.length > 0" class="mt-3 pt-3 border-t border-gray-100">
                <p class="text-xs font-semibold text-gray-500 mb-2">📄 参考来源</p>
                <div class="space-y-1.5">
                  <div
                    v-for="(src, si) in msg.sources"
                    :key="si"
                    class="flex items-start space-x-2 text-xs"
                  >
                    <span
                      :class="scoreColor(src.score)"
                      class="inline-flex items-center px-1.5 py-0.5 rounded font-mono text-xs flex-shrink-0"
                    >
                      {{ (src.score * 100).toFixed(0) }}%
                    </span>
                    <span class="text-gray-600">{{ src.title || src.source }}</span>
                  </div>
                </div>
              </div>

              <!-- Feedback Buttons -->
              <div v-if="msg.answerId" class="mt-3 pt-3 border-t border-gray-100 flex items-center space-x-3">
                <button
                  @click="submitFeedback(msg, 'like')"
                  :disabled="feedbackLoading === msg.id"
                  class="inline-flex items-center space-x-1 px-2.5 py-1 text-xs rounded-md bg-gray-50 hover:bg-green-50 text-gray-500 hover:text-green-600 border border-gray-200 hover:border-green-300 transition-colors disabled:opacity-50"
                >
                  <span>👍</span><span>好评</span>
                </button>
                <button
                  @click="submitFeedback(msg, 'dislike')"
                  :disabled="feedbackLoading === msg.id"
                  class="inline-flex items-center space-x-1 px-2.5 py-1 text-xs rounded-md bg-gray-50 hover:bg-red-50 text-gray-500 hover:text-red-600 border border-gray-200 hover:border-red-300 transition-colors disabled:opacity-50"
                >
                  <span>👎</span><span>差评</span>
                </button>
                <span v-if="feedbackLoading === msg.id" class="text-xs text-gray-400">提交中...</span>
              </div>

              <!-- Ticket Draft Card -->
              <div v-if="msg.needTicket && msg.ticketDraft" class="mt-3 pt-3 border-t border-yellow-200">
                <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                  <div class="flex items-center space-x-2 mb-2">
                    <span>🎫</span>
                    <span class="text-sm font-semibold text-yellow-700">建议创建工单</span>
                  </div>
                  <p class="text-xs text-yellow-600 mb-2">系统无法准确回答此问题，您可以创建人工工单获取帮助</p>
                  <div class="text-xs text-yellow-700 font-mono mb-2">草稿ID: {{ msg.ticketDraft.draft_id }}</div>
                  <div v-if="msg.ticketDraft.suggested_category" class="text-xs text-yellow-700 mb-2">
                    建议分类: {{ msg.ticketDraft.suggested_category }}
                  </div>
                  <button
                    @click="submitTicket(msg)"
                    :disabled="submittingTicket === msg.id"
                    class="px-3 py-1.5 text-xs font-medium bg-yellow-600 text-white rounded-md hover:bg-yellow-700 disabled:opacity-50 transition-colors"
                  >
                    {{ submittingTicket === msg.id ? '提交中...' : '提交工单' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Loading indicator -->
        <div v-if="chatStore.loading" class="flex justify-start animate-fade-in">
          <div class="bg-white border border-gray-200 rounded-2xl rounded-bl-md px-6 py-3 shadow-sm">
            <div class="flex items-center space-x-2 text-gray-400 text-sm">
              <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span>正在思考...</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Input Area -->
      <div class="mt-3 bg-white rounded-lg shadow-sm border border-gray-200 p-3">
        <div class="flex space-x-3">
          <textarea
            v-model="question"
            @keydown="onKeydown"
            :disabled="chatStore.loading"
            placeholder="输入您的问题... (Ctrl+Enter 发送)"
            rows="3"
            class="flex-1 resize-none border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none disabled:bg-gray-50 disabled:cursor-not-allowed"
          ></textarea>
          <button
            @click="sendQuestion"
            :disabled="chatStore.loading || !question.trim()"
            class="px-6 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors self-end"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
