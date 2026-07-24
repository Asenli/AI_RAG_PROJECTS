import api from './index'

function companyId() {
  return localStorage.getItem('fs_company_id') || '1'
}

export const ticketApi = {
  create(data: { company_id?: string; original_question: string; user_id: string; user_role: string; school_id?: string; trace_id?: string }) {
    return api.post('/ticket/create', { company_id: companyId(), ...data })
  },
  get(draftId: string) {
    return api.get(`/ticket/${draftId}`, { params: { company_id: companyId() } })
  },
  submit(draftId: string) {
    return api.post(`/ticket/${draftId}/submit`, null, {
      params: { company_id: companyId() },
    })
  },
  list(params?: { user_id?: string; status?: string; limit?: number }) {
    return api.get('/ticket/list', {
      params: { ...params, company_id: companyId() },
    })
  },
  update(draftId: string, data: Record<string, any>) {
    return api.patch(`/ticket/${draftId}`, data, {
      params: { company_id: companyId() },
    })
  },
}
