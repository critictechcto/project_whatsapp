import { StrictMode } from 'react'
import { prerender } from 'react-dom/static'
import App from './App'

/*
 * Build-time prerender of the landing page (scripts/prerender.mjs). Renders the same tree that
 * main.tsx hydrates, so anything read during render must not depend on the browser: reduced motion,
 * pointer type and viewport size switch in effects or through `usePrefersReducedMotion`.
 */
export async function render(): Promise<string> {
  const { prelude } = await prerender(
    <StrictMode>
      <App />
    </StrictMode>,
  )
  return new Response(prelude).text()
}
