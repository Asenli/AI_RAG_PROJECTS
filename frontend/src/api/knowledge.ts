import api from './index'

function companyId() {
  return localStorage.getItem('fs_company_id') || '1'
}

export const knowledgeApi = {
  list() {
    return api.get('/knowledge/list', { params: { company_id: companyId() } })
  },
  detail(source: string) {
    return api.get('/knowledge/detail', {
      params: { source, company_id: companyId() },
    })
  },
  upload(formData: FormData) {
    formData.set('company_id', companyId())
    return api.post('/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,  // 5 分钟，embedding API 可能较慢
    })
  },
  previewSplit(data: { content: string; knowledge_type: string; module: string; sub_module: string }) {
    return api.post('/knowledge/preview-split', data)
  },
  searchTest(params: { q: string; role: string; top_k?: number }) {
    return api.get('/knowledge/search-test', {
      params: { ...params, company_id: companyId() },
    })
  },
  deleteDoc(source: string) {
    return api.delete('/knowledge/delete', {
      params: { source, company_id: companyId() },
    })
  },
  reindex(source: string) {
    return api.post('/knowledge/reindex', null, {
      params: { source, company_id: companyId() },
    })
  },
}
