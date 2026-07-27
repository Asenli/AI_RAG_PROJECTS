<script setup lang="ts">
import { watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore, ROLES } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const tabs = [
  { path: '/chat', label: '问答测试', icon: '💬' },
  { path: '/knowledge', label: '知识库', icon: '📚' },
  { path: '/tickets', label: '工单管理', icon: '🎫' },
  { path: '/feedback', label: '反馈管理', icon: '📝' },
  { path: '/sessions', label: '会话', icon: '🕐' },
  { path: '/admin', label: '管理后台', icon: '⚙️' },
]

function navigate(path: string) {
  router.push(path)
}

function isActive(path: string): boolean {
  return route.path === path
}

// Sync user store to localStorage for API interceptor
watch(() => userStore.userId, (val) => {
  localStorage.setItem('fs_user_id', val)
}, { immediate: true })

watch(() => userStore.userRole, (val) => {
  localStorage.setItem('fs_user_role', val)
}, { immediate: true })

watch(() => userStore.companyId, (val) => {
  localStorage.setItem('fs_company_id', val || '1')
}, { immediate: true })
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Top Navigation Bar -->
    <header class="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-50">
      <div class="max-w-7xl mx-auto px-4 py-3">
        <div class="flex items-center justify-between">
          <!-- App Title -->
          <div class="flex items-center space-x-3">
            <span class="text-2xl">🍽️</span>
            <h1 class="text-lg font-bold text-gray-800">售后智能助手</h1>
            <span class="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full"></span>
          </div>

          <!-- Role & User Controls -->
          <div class="flex items-center space-x-4">
            <div class="flex items-center space-x-2">
              <label class="text-sm text-gray-600">公司ID:</label>
              <input
                v-model="userStore.companyId"
                type="text"
                class="text-sm border border-gray-300 rounded-md px-3 py-1.5 w-24 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                placeholder="1"
              />
            </div>

            <!-- Role Selector -->
            <div class="flex items-center space-x-2">
              <label class="text-sm text-gray-600">角色:</label>
              <select
                :value="userStore.userRole"
                @change="userStore.setRole(($event.target as HTMLSelectElement).value)"
                class="text-sm border border-gray-300 rounded-md px-3 py-1.5 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              >
                <option
                  v-for="role in ROLES"
                  :key="role.value"
                  :value="role.value"
                >
                  {{ role.icon }} {{ role.label }}
                </option>
              </select>
            </div>

            <!-- User ID Input -->
            <div class="flex items-center space-x-2">
              <label class="text-sm text-gray-600">用户ID:</label>
              <input
                v-model="userStore.userId"
                type="text"
                class="text-sm border border-gray-300 rounded-md px-3 py-1.5 w-32 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                placeholder="dev_user"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Tab Navigation -->
      <nav class="max-w-7xl mx-auto px-4">
        <div class="flex space-x-0 border-b-0">
          <button
            v-for="tab in tabs"
            :key="tab.path"
            @click="navigate(tab.path)"
            :class="[
              'px-4 py-2.5 text-sm font-medium border-b-2 transition-colors duration-150',
              isActive(tab.path)
                ? 'border-blue-600 text-blue-600 bg-blue-50/50'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            ]"
          >
            <span class="mr-1.5">{{ tab.icon }}</span>
            {{ tab.label }}
          </button>
        </div>
      </nav>
    </header>

    <!-- Page Content -->
    <main class="max-w-7xl mx-auto px-4 py-6">
      <router-view />
    </main>
  </div>
</template>
