import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

/** Starts the MSW service worker. Loaded via dynamic import only when `VITE_API_MODE=mock`. */
export async function startMockWorker() {
  const base = import.meta.env.BASE_URL
  const worker = setupWorker(...handlers)
  await worker.start({
    serviceWorker: { url: `${base}mockServiceWorker.js`, options: { scope: base } },
    onUnhandledRequest: 'bypass',
    quiet: true,
  })
  return worker
}
