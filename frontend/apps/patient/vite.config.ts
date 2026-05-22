import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { hospitalDevProxy } from '../../packages/shared/vite-proxy'

export default defineConfig({
  plugins: [vue()],
  server: { port: 5175, host: true, proxy: hospitalDevProxy() },
})
