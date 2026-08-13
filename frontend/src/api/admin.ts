import api from './index'

function companyId() {
  return localStorage.getItem('fs_company_id') || '1'
}

export const adminApi = {
  stats() {
    return api.get('/admin/stats', { params: { company_id: companyId() } })
  },
  traces(params?: { user_id?: string; limit?: number }) {
    return api.get('/admin/traces', {
      params: { ...params, company_id: companyId() },
    })
  },
  traceDetail(traceId: string) {
    return api.get(`/admin/traces/${traceId}`, {
      params: { company_id: companyId() },
    })
  },
  badcaseList(limit?: number) {
    return api.get('/admin/badcase/list', {
      params: { limit, company_id: companyId() },
    })
  },
  feedbackList(params?: { feedback_type?: string; review_status?: string; reason_category?: string; limit?: number }) {
    return api.get('/admin/feedback/list', {
      params: { ...params, company_id: companyId() },
    })
  },
  reviewFeedback(feedbackId: string) {
    return api.post(`/admin/feedback/${feedbackId}/review`, null, {
      params: { company_id: companyId() },
    })
  },
  convertBadcase(feedbackId: string) {
    return api.post(`/admin/feedback/${feedbackId}/convert-badcase`, null, {
      params: { company_id: companyId() },
    })
  },
  roleModules() {
    return api.get('/admin/role-modules', {
      params: { company_id: companyId() },
    })
  },
  updateRoleModules(role: string, modules: string[]) {
    return api.put(`/admin/role-modules/${role}`, { modules }, {
      params: { company_id: companyId() },
    })
  },
  resetRoleModules(role: string) {
    return api.post(`/admin/role-modules/${role}/reset`, null, {
      params: { company_id: companyId() },
    })
  },
  runRagas(limit: number, includeRagas: boolean) {
    return api.post('/admin/ragas/run', { limit, include_ragas: includeRagas }, {
      params: { company_id: companyId() },
    })
  },
  ragasStatus() {
    return api.get('/admin/ragas/status')
  },
}
