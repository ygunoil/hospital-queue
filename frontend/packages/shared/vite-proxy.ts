import type { ProxyOptions } from 'vite'

/** 与 scripts/start.sh 中 BACKEND_PORT 保持一致 */
export function hospitalDevProxy(): Record<string, ProxyOptions> {
  const port = process.env.BACKEND_PORT || '8000'
  const target = `http://127.0.0.1:${port}`
  return {
    '/api': { target, changeOrigin: true },
    '/ws': { target, ws: true, changeOrigin: true },
  }
}
