import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/** Normalises VITE_BASE to an absolute path with leading and trailing slashes. */
function resolveBase(raw: string | undefined) {
  const value = (raw ?? '').trim()
  if (!value || value === '/') return '/'
  return `/${value.replace(/^\/+|\/+$/g, '')}/`
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')

  return {
    // Absolute base so deep links like /app/w/<id>/inbox resolve assets correctly.
    // GitHub Pages (project site) builds with VITE_BASE=/<repo>/; a custom domain uses '/'.
    base: resolveBase(env.VITE_BASE ?? process.env.VITE_BASE),
    plugins: [react(), tailwindcss()],
    // No manualChunks: grouping recharts/msw pulled shared deps (React) into those groups and made
    // the landing entry import them. Dynamic imports alone keep the dashboard, charts
    // (components/app/charts/LazyTrendChart) and MSW (App.tsx, mock mode only) out of the landing bundle.
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      restoreMocks: true,
      env: {
        VITE_API_MODE: 'live',
        VITE_API_URL: 'http://localhost:3000',
        VITE_WS_URL: 'ws://localhost:3000',
      },
    },
  }
})
