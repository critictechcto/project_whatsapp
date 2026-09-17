// Prerenders the landing page into dist/index.html after `vite build` and the SSR build of
// src/entry-server.tsx (see the `build` script in package.json).
//
// - dist/index.html: the landing page markup inside #root; main.tsx hydrates it.
// - dist/shell.html: the same document with an empty #root, for every other path (404.html, the
//   site pages and SPA fallbacks), so those never ship or flash the landing markup.
import { readFile, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

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

await writeFile(path.join(dist, 'shell.html'), template)
await writeFile(path.join(dist, 'index.html'), template.replace(EMPTY_ROOT, `<div id="root">${markup}</div>`))
await rm(ssrDir, { recursive: true, force: true })

console.log(`prerender: landing page ${(markup.length / 1024).toFixed(1)} kB -> dist/index.html; empty shell -> dist/shell.html`)
