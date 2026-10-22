import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// The backend lives at http://127.0.0.1:8001 and serves the API under /api.
// In dev we proxy /api so the browser sees a same-origin request (no CORS).
// The target is overridable with VITE_API_PROXY_TARGET for local testing.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const apiTarget = env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8001'

  return {
    plugins: [vue()],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: '127.0.0.1',
      port: 4173,
      strictPort: true,
    },
    build: {
      target: 'es2022',
      outDir: 'dist',
      sourcemap: false,
    },
  }
})
