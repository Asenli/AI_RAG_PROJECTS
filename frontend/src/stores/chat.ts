import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  traceId?: string
  answerId?: string
  sources?: Array<{ source: string; title: string; score: number }>
  needTicket?: boolean
  ticketDraft?: any
  durationMs?: number
  timestamp: number
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)

  function addMessage(msg: ChatMessage) {
    messages.value.push(msg)
  }

  function clearMessages() {
    messages.value = []
  }

  function setMessages(nextMessages: ChatMessage[]) {
    messages.value = nextMessages
  }

  return { messages, loading, addMessage, clearMessages, setMessages }
})
