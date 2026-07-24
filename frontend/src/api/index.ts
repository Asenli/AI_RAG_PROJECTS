import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 180000,
  headers: { 'Content-Type': 'application/json' },
})

function createTraceId() {
  const random = Math.random().toString(16).slice(2, 18).padEnd(16, '0')
  return `trace_${random.slice(0, 16)}`
}

function friendlyErrorMessage(err: any) {
  if (err.code === 'ECONNABORTED' || String(err.message || '').includes('timeout')) {
    return '系统处理时间较长，请稍后再试。若多次出现，请联系管理员并提供 Trace ID。'
  }
  if (!err.response) {
    return '暂时无法连接服务，请检查网络或稍后再试。'
  }
  if (err.response.status >= 500) {
    return '检测到当前咨询量较大，请稍后重试，抱歉给您带来不便。'
  }
  return err.response?.data?.message || '请求未能完成，请检查输入后重试。'
}

// Request interceptor: inject user/role headers
api.interceptors.request.use((config) => {
  const userId = localStorage.getItem('fs_user_id') || 'dev_user'
  const userRole = localStorage.getItem('fs_user_role') || 'school'
  const companyId = localStorage.getItem('fs_company_id') || '1'
  config.headers['X-Trace-Id'] = config.headers['X-Trace-Id'] || createTraceId()
  config.headers['X-Company-Id'] = companyId
  config.headers['X-User-Id'] = userId
  config.headers['X-User-Role'] = userRole
  return config
})

// Response interceptor: error handling
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail || err.message || '请求失败'
    const traceId = err.response?.headers?.['x-trace-id'] || err.config?.headers?.['X-Trace-Id']
    err.userMessage = friendlyErrorMessage(err)
    err.traceId = traceId
    err.debugMessage = msg
    console.error(`[API Error] trace=${traceId || '-'} ${msg}`)
    return Promise.reject(err)
  }
)

export default api
