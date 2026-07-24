import api from './index'

function companyId() {
  return localStorage.getItem('fs_company_id') || '1'
}

export const feedbackApi = {
  like(data: { company_id?: string; answer_id: string; trace_id: string; session_id: string; user_id: string; user_role: string; question: string; llm_answer: string; retrieved_sources: any[] }) {
    return api.post('/feedback/like', { company_id: companyId(), ...data })
  },
  dislike(data: { company_id?: string; answer_id: string; reason: string; reason_category: string; trace_id: string; session_id: string; user_id: string; user_role: string; question: string; llm_answer: string; retrieved_sources: any[] }) {
    return api.post('/feedback/dislike', { company_id: companyId(), ...data })
  },
  stats(params?: { user_id?: string; days?: number }) {
    return api.get('/feedback/stats', {
      params: { ...params, company_id: companyId() },
    })
  },
}
