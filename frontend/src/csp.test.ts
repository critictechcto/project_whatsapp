import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { buildDirectives, injectCsp, inlineScriptHashes, verifyCsp } from '../scripts/csp.mjs'

// index.html as vite build emits it for VITE_BASE=/ (the only build-time substitution in it).
const template = readFileSync(path.resolve(__dirname, '../index.html'), 'utf8').replaceAll('%BASE_URL%', '/')

function policyOf(html: string) {
  return verifyCsp(html)
}

function sha256(text: string) {
  return `'sha256-${createHash('sha256').update(text, 'utf8').digest('base64')}'`
}

describe('build CSP', () => {
  it('hashes the inline script of index.html after %BASE_URL% substitution', () => {
    const inline = [...template.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((match) => match[1])
    expect(inline).toHaveLength(1)
    expect(inline[0]).toContain("('/', location.pathname")

    const html = injectCsp(template, { VITE_API_MODE: 'mock' })
    const policy = policyOf(html)
    expect(policy['script-src']).toEqual(["'self'", sha256(inline[0])])
    expect(html.indexOf('Content-Security-Policy')).toBeLessThan(html.indexOf('<style>'))
  })

  it('fails when an inline script changes after the policy was built', () => {
    const html = injectCsp(template, { VITE_API_MODE: 'mock' })
    expect(() => verifyCsp(html.replace("('/', location.pathname", "('/app/', location.pathname"))).toThrow(/no matching hash/)
    expect(() => verifyCsp(html.replace('</body>', '<script>alert(1)</script></body>'))).toThrow(/no matching hash/)
    expect(() => verifyCsp(html.replace('<body>', '<body onload="alert(1)">'))).toThrow(/event handler/)
    expect(() => verifyCsp(template)).toThrow(/one Content-Security-Policy/)
    expect(() => injectCsp(html, {})).toThrow(/already/)
  })

  it('allows no third parties in mock builds', () => {
    const policy = buildDirectives({ VITE_API_MODE: 'mock', VITE_API_URL: '', VITE_WS_URL: '' }, [])
    expect(policy['script-src']).toEqual(["'self'"])
    expect(policy['connect-src']).toEqual(["'self'"])
    expect(policy['frame-src']).toEqual(["'none'"])
    expect(policy['worker-src']).toEqual(["'self'"])
    expect(policy['object-src']).toEqual(["'none'"])
  })

  it('allows Meta, Razorpay, the API, sockets and media hosts in live builds', () => {
    const policy = buildDirectives(
      {
        VITE_API_MODE: 'live',
        VITE_API_URL: 'https://api.example.com/',
        VITE_MEDIA_ORIGINS: 'https://*.digitaloceanspaces.com, https://cdn.example.com',
      },
      ["'sha256-abc'"],
    )
    expect(policy['script-src']).toEqual(["'self'", "'sha256-abc'", 'https://connect.facebook.net', 'https://checkout.razorpay.com', 'https://cdn.razorpay.com'])
    expect(policy['connect-src']).toEqual(expect.arrayContaining(['https://api.example.com', 'wss://api.example.com', 'https://graph.facebook.com']))
    expect(policy['img-src']).toEqual(expect.arrayContaining(['https://*.digitaloceanspaces.com', 'https://cdn.example.com']))
    expect(policy['frame-src']).toEqual(expect.arrayContaining(['https://www.facebook.com', 'https://api.razorpay.com']))
  })

  it('rejects env values that are not origins', () => {
    expect(() => buildDirectives({ VITE_MEDIA_ORIGINS: "'unsafe-inline'" }, [])).toThrow(/VITE_MEDIA_ORIGINS/)
    expect(() => buildDirectives({ VITE_CSP_EXTRA_CONNECT: 'https://x.com/path' }, [])).toThrow(/VITE_CSP_EXTRA_CONNECT/)
    expect(() => buildDirectives({ VITE_API_URL: 'not a url' }, [])).toThrow(/VITE_API_URL/)
  })

  it('skips external scripts when hashing', () => {
    expect(inlineScriptHashes('<script type="module" crossorigin src="/assets/index.js"></script>')).toEqual([])
  })
})
