import api from './index'

function companyId() {
  return localStorage.getItem('fs_company_id') || '1'
}

export const sessionApi = {
  create(data: { company_id?: string; user_id: string; user_role: string; school_id?: string }) {
    return api.post('/session/create', { company_id: companyId(), ...data })
  },
  list(userId: string, limit = 30) {
    return api.get('/session/list', {
      params: { company_id: companyId(), user_id: userId, limit },
    })
  },
  history(sessionId: string) {
    return api.get(`/session/${sessionId}/history`, {
      params: { company_id: companyId() },
    })
  },
  summary(sessionId: string) {
    return api.get(`/session/${sessionId}/summary`, {
      params: { company_id: companyId() },
    })
  },
  userProfile(userId: string) {
    return api.get(`/session/user/${userId}/profile`, {
      params: { company_id: companyId() },
    })
  },
  close(sessionId: string) {
    return api.delete(`/session/${sessionId}`, {
      params: { company_id: companyId() },
    })
  },
}
