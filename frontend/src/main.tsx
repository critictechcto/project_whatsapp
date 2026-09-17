import { StrictMode } from 'react'
import { createRoot, hydrateRoot } from 'react-dom/client'
import '@fontsource-variable/schibsted-grotesk'
import '@fontsource-variable/ibm-plex-sans'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import './index.css'
import App from './App'
import { isLandingPath } from './config/site'

const root = document.getElementById('root')!
const app = (
  <StrictMode>
    <App />
  </StrictMode>
)

/*
 * `dist/index.html` carries the landing page prerendered at build time (scripts/prerender.mjs), so
 * the landing page hydrates it. Every other path renders from scratch: the dashboard, the site pages
 * and any host that serves index.html as its SPA fallback. The inline script in index.html hides the
 * prerendered markup on those paths until it is cleared here.
 */
if (isLandingPath() && root.firstElementChild) {
  hydrateRoot(root, app)
} else {
  root.replaceChildren()
  delete document.documentElement.dataset.shell
  createRoot(root).render(app)
}
