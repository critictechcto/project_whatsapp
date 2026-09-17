// Content Security Policy for the built HTML (dist/index.html, dist/shell.html and the copies the
// Pages workflow makes). GitHub Pages and App Platform static sites cannot set response headers,
// so the policy ships as <meta http-equiv="Content-Security-Policy">, injected by
// scripts/prerender.mjs into the final text. The Vite dev server never gets it (react-refresh
// needs inline scripts).
//
// Rules the policy enforces, and what to update when they change:
// - Scripts run only from the page's own origin, plus the sha256 hash of every inline <script> in
//   the final HTML (computed here, after %BASE_URL% substitution). The build fails if an inline
//   script, an inline event handler or a javascript: URL is not covered.
// - A new third-party script, frame or API host needs an entry below; nothing else may load.
// - style-src keeps 'unsafe-inline': the prerendered landing markup carries style="" attributes,
//   and Meta's SDK and Razorpay Checkout inject <style> elements with changing content, so hashes
//   cannot cover them. Injected CSS cannot run script, and what it could load or leak through
//   url() is limited by img-src, font-src and connect-src below.
import { createHash } from 'node:crypto'

/** Third parties the live dashboard loads (lib/integrations). Mock builds load none of them. */
export const THIRD_PARTY = {
  // Meta JS SDK for Embedded Signup (lib/integrations/facebook.ts). FB.login opens a popup
  // (popups are not governed by CSP); the SDK talks to it through hidden www.facebook.com frames
  // and logs app events to graph.facebook.com.
  meta: {
    script: ['https://connect.facebook.net'],
    frame: ['https://www.facebook.com', 'https://web.facebook.com'],
    connect: ['https://graph.facebook.com', 'https://www.facebook.com', 'https://connect.facebook.net'],
    img: ['https://www.facebook.com'],
  },
  // Razorpay Checkout for UpChatz subscriptions (lib/integrations/razorpay.ts): checkout.js loads
  // its risk-detection bundle from cdn.razorpay.com, opens its payment frame from api.razorpay.com
  // and reports errors to lumberjack.razorpay.com.
  razorpay: {
    script: ['https://checkout.razorpay.com', 'https://cdn.razorpay.com'],
    frame: ['https://api.razorpay.com', 'https://checkout.razorpay.com'],
    connect: ['https://api.razorpay.com', 'https://lumberjack.razorpay.com'],
    img: ['https://cdn.razorpay.com'],
  },
}

/** Splits a space- or comma-separated env value into CSP sources, rejecting anything but origins. */
export function parseOrigins(value, name) {
  return (value ?? '')
    .split(/[\s,]+/)
    .filter(Boolean)
    .map((raw) => {
      // Scheme, host (optionally a leading *. wildcard) and port; no paths, quotes or keywords.
      if (!/^(https?|wss?):\/\/(\*\.)?[a-z0-9.-]+(:\d+)?\/?$/i.test(raw)) {
        throw new Error(`csp: ${name} must list origins like https://media.example.com, got ${JSON.stringify(raw)}`)
      }
      return raw.replace(/\/$/, '')
    })
}

/** The origin of a URL env value such as VITE_API_URL, or nothing when it is empty (same origin). */
function originOf(value, name) {
  const trimmed = (value ?? '').trim()
  if (!trimmed) return []
  let url
  try {
    url = new URL(trimmed)
  } catch {
    throw new Error(`csp: ${name} is not an absolute URL: ${JSON.stringify(trimmed)}`)
  }
  return parseOrigins(url.origin, name)
}

const unique = (items) => [...new Set(items)]

/**
 * Directive map for a build. `env` holds the VITE_* values; `scriptHashes` are 'sha256-…' sources.
 * - VITE_API_URL / VITE_WS_URL: API and WebSocket origins (empty = same origin, covered by 'self').
 * - VITE_MEDIA_ORIGINS: hosts of product images (PUBLIC_MEDIA_BASE_URL, Spaces), for img-src.
 * - VITE_CSP_EXTRA_CONNECT: any other origin the dashboard must call.
 */
export function buildDirectives(env, scriptHashes) {
  const mock = env.VITE_API_MODE === 'mock'
  const parties = mock ? [] : Object.values(THIRD_PARTY)
  const pick = (key) => parties.flatMap((party) => party[key] ?? [])
  const api = originOf(env.VITE_API_URL, 'VITE_API_URL')
  const ws = originOf(env.VITE_WS_URL, 'VITE_WS_URL')
  // Without VITE_WS_URL the socket goes to the API origin with ws(s):// (config/env.ts).
  const derivedWs = ws.length ? [] : api.map((origin) => origin.replace(/^http/, 'ws'))
  const media = parseOrigins(env.VITE_MEDIA_ORIGINS, 'VITE_MEDIA_ORIGINS')
  const extraConnect = parseOrigins(env.VITE_CSP_EXTRA_CONNECT, 'VITE_CSP_EXTRA_CONNECT')

  return {
    'default-src': ["'self'"],
    'script-src': unique(["'self'", ...scriptHashes, ...pick('script')]),
    'style-src': ["'self'", "'unsafe-inline'"],
    'img-src': unique(["'self'", 'data:', 'blob:', ...api, ...media, ...pick('img')]),
    'media-src': unique(["'self'", 'blob:', ...api, ...media]),
    'font-src': ["'self'"],
    'connect-src': unique(["'self'", ...api, ...ws, ...derivedWs, ...extraConnect, ...pick('connect')]),
    // MSW's service worker in mock builds; nothing else registers workers.
    'worker-src': ["'self'"],
    'frame-src': pick('frame').length ? unique(pick('frame')) : ["'none'"],
    'object-src': ["'none'"],
    'base-uri': ["'self'"],
    'form-action': ["'self'"],
  }
}

export function serializePolicy(directives) {
  return Object.entries(directives)
    .map(([name, sources]) => `${name} ${sources.join(' ')}`)
    .join('; ')
}

const SCRIPT_RE = /<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi

/** sha256 sources for every inline <script> (no src attribute), hashed exactly as the browser does. */
export function inlineScriptHashes(html) {
  const hashes = []
  for (const [, attrs, body] of html.matchAll(SCRIPT_RE)) {
    if (/\bsrc\s*=/i.test(attrs)) continue
    hashes.push(`'sha256-${createHash('sha256').update(body, 'utf8').digest('base64')}'`)
  }
  return unique(hashes)
}

const META_RE = /<meta http-equiv="Content-Security-Policy" content="([^"]*)"\s*\/?>/gi

/** Adds the policy meta tag as the first element after <meta charset>, before any script or style. */
export function injectCsp(html, env) {
  if (META_RE.test(html)) throw new Error('csp: the HTML already has a Content-Security-Policy meta tag')
  META_RE.lastIndex = 0
  const charset = html.match(/<meta charset="[^"]*"\s*\/?>/i)
  if (!charset) throw new Error('csp: expected <meta charset> in the HTML head')
  const policy = serializePolicy(buildDirectives(env, inlineScriptHashes(html)))
  const tag = `\n    <meta http-equiv="Content-Security-Policy" content="${policy}" />`
  const at = charset.index + charset[0].length
  const result = html.slice(0, at) + tag + html.slice(at)
  verifyCsp(result)
  return result
}

/**
 * Fails unless the HTML has exactly one policy tag, placed before every script and style, whose
 * script-src covers each inline script by hash and which the page does not undermine with inline
 * event handlers or javascript: URLs (those would need 'unsafe-inline').
 */
export function verifyCsp(html) {
  const tags = [...html.matchAll(META_RE)]
  if (tags.length !== 1) throw new Error(`csp: expected one Content-Security-Policy meta tag, found ${tags.length}`)
  const [tag] = tags
  const firstActive = html.search(/<(script|style|link)\b/i)
  if (firstActive !== -1 && firstActive < tag.index) {
    throw new Error('csp: the policy meta tag must come before any script, style or link')
  }
  const directives = Object.fromEntries(
    tag[1].split(';').map((part) => {
      const [name, ...sources] = part.trim().split(/\s+/)
      return [name, sources]
    }),
  )
  const scriptSrc = directives['script-src'] ?? []
  for (const forbidden of ["'unsafe-inline'", "'unsafe-eval'", '*', 'https:', 'data:']) {
    if (scriptSrc.includes(forbidden)) throw new Error(`csp: script-src must not allow ${forbidden}`)
  }
  for (const required of ['object-src', 'base-uri', 'form-action']) {
    if (!directives[required]) throw new Error(`csp: missing ${required}`)
  }
  for (const hash of inlineScriptHashes(html)) {
    if (!scriptSrc.includes(hash)) {
      throw new Error(`csp: an inline <script> has no matching hash in script-src (${hash}); inject the policy after the last HTML change`)
    }
  }
  const handler = html.match(/<[a-z][^>]*\son[a-z]+\s*=/i)
  if (handler) throw new Error(`csp: inline event handler would be blocked: ${handler[0].slice(0, 80)}`)
  if (/\b(?:href|src|action)\s*=\s*["']?\s*javascript:/i.test(html)) {
    throw new Error('csp: javascript: URLs would be blocked')
  }
  return directives
}
