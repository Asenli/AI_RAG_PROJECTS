import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const ROLES = [
  { value: 'school', label: '学校人员', icon: '🏫' },
  { value: 'canteen', label: '食堂人员', icon: '👨‍🍳' },
  { value: 'finance', label: '财务/会计', icon: '💰' },
  { value: 'cashier', label: '出纳', icon: '💳' },
  { value: 'purchaser', label: '采购员', icon: '🛒' },
  { value: 'storekeeper', label: '仓管员', icon: '📦' },
  { value: 'distributor', label: '配送商', icon: '🚚' },
  { value: 'inspector', label: '巡检员', icon: '🔍' },
  { value: 'nutritionist', label: '营养师', icon: '🥗' },
  { value: 'education_bureau', label: '教育局', icon: '🏛️' },
  { value: 'admin', label: '管理员', icon: '⚙️' },
] as const

export const useUserStore = defineStore('user', () => {
  const companyId = ref(localStorage.getItem('fs_company_id') || '1')
  const userId = ref('dev_user')
  const userRole = ref('school')
  const schoolId = ref('school_001')
  const sessionId = ref('')

  const currentRole = computed(() =>
    ROLES.find((r) => r.value === userRole.value)
  )

  function setRole(role: string) {
    userRole.value = role
  }

  function setSession(id: string) {
    sessionId.value = id
  }

  return {
    companyId,
    userId,
    userRole,
    schoolId,
    sessionId,
    currentRole,
    setRole,
    setSession,
  }
})
