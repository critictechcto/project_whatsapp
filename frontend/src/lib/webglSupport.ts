import { prefersReducedMotion } from './motion'

type NavigatorHints = Navigator & {
  connection?: { saveData?: boolean }
  deviceMemory?: number
}

/**
 * Whether the browser can create a WebGL context. three.js (r163+) renders with WebGL 2 only, so a
 * WebGL 1-only browser gets `false` here and the CSS fallback instead of a useless download.
 * The probe context is released straight away.
 */
export function hasWebGL2() {
  try {
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('webgl2')
    if (!context) return false
    context.getExtension('WEBGL_lose_context')?.loseContext()
    return true
  } catch {
    return false
  }
}

/**
 * Whether to load the WebGL scroll story: WebGL available, no reduced-motion or data-saver
 * preference, at least 4 GB of device memory where the browser reports it, and a large viewport or a
 * precise pointer. Cheap checks run first, so the WebGL probe only happens when it could matter.
 */
export function canUseWebGLStory() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return false
  if (prefersReducedMotion()) return false

  const nav = navigator as NavigatorHints
  if (nav.connection?.saveData) return false
  if (typeof nav.deviceMemory === 'number' && nav.deviceMemory < 4) return false
  if (window.innerWidth < 1024 && !window.matchMedia('(pointer: fine)').matches) return false

  return hasWebGL2()
}
