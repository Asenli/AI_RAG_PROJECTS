import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/chat' },
  { path: '/chat', name: 'Chat', component: () => import('@/views/ChatView.vue') },
  { path: '/knowledge', name: 'Knowledge', component: () => import('@/views/KnowledgeView.vue') },
  { path: '/tickets', name: 'Tickets', component: () => import('@/views/TicketView.vue') },
  { path: '/feedback', name: 'Feedback', component: () => import('@/views/FeedbackView.vue') },
  { path: '/sessions', name: 'Sessions', component: () => import('@/views/SessionView.vue') },
  { path: '/admin', name: 'Admin', component: () => import('@/views/AdminView.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
