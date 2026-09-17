// Prerenders the landing page into dist/index.html after `vite build` and the SSR build of
// src/entry-server.tsx (see the `build` script in package.json).
//
// - dist/index.html: the landing page markup inside #root; main.tsx hydrates it.
// - dist/shell.html: the same document with an empty #root, for every other path (404.html, the
//   site pages and SPA fallbacks), so those never ship or flash the landing markup.
// - Both get the Content-Security-Policy meta tag (scripts/csp.mjs), hashed from their final text.
import { readFile, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { loadEnv } from 'vite'
import { injectCsp, verifyCsp } from './csp.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dist = path.join(root, 'dist')
const ssrDir = path.join(root, 'node_modules', '.prerender')
const EMPTY_ROOT = '<div id="root"></div>'

const template = await readFile(path.join(dist, 'index.html'), 'utf8')
if (template.split(EMPTY_ROOT).length !== 2) {
  throw new Error(`prerender: expected exactly one ${EMPTY_ROOT} in dist/index.html`)
}

const { render } = await import(pathToFileURL(path.join(ssrDir, 'entry-server.js')).href)
const markup = await render()
if (!markup.includes('id="main"')) {
  throw new Error('prerender: the rendered markup does not look like the landing page')
}

// The same VITE_* values `vite build` saw: .env files for the production mode plus the environment.
const env = loadEnv('production', root, 'VITE_')
const pages = {
  'shell.html': injectCsp(template, env),
  'index.html': injectCsp(template.replace(EMPTY_ROOT, () => `<div id="root">${markup}</div>`), env),
}
for (const [file, html] of Object.entries(pages)) await writeFile(path.join(dist, file), html)
// Check what hosts will serve: every inline script on disk has its hash in the policy.
for (const file of Object.keys(pages)) verifyCsp(await readFile(path.join(dist, file), 'utf8'))
await rm(ssrDir, { recursive: true, force: true })

console.log(`prerender: landing page ${(markup.length / 1024).toFixed(1)} kB -> dist/index.html; empty shell -> dist/shell.html (with CSP)`)
