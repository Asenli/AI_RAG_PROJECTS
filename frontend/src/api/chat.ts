import api from './index'

export interface ChatAskParams {
  company_id: string
  session_id: string
  question: string
  user_id: string
  user_role: string
  school_id: string
}

export const chatApi = {
  ask(params: ChatAskParams) {
    return api.post('/chat/ask', params)
  },
}
