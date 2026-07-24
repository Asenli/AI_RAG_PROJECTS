import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const BACKEND = 'http://localhost:5002'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/chat': BACKEND,
      '/ticket': BACKEND,
      '/feedback': BACKEND,
      '/knowledge': BACKEND,
      '/session': BACKEND,
      '/admin': BACKEND,
      '/health': BACKEND,
    },
  },
})
