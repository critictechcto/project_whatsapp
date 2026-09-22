import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const root = path.resolve(__dirname, '..')
const html = readFileSync(path.join(root, 'index.html'), 'utf8')

function attr(selector: RegExp) {
  return html.match(selector)?.[1]
}

describe('index.html head', () => {
  it('points social previews at an absolute 1200x630 PNG that exists', () => {
    // WhatsApp, Facebook, LinkedIn and X ignore relative URLs and SVG images.
    const image = attr(/<meta property="og:image" content="([^"]+)"/)
    expect(image).toBe('https://upchatz.com/og-image.png')
    expect(attr(/<meta name="twitter:image" content="([^"]+)"/)).toBe(image)
    expect(attr(/<meta property="og:image:width" content="([^"]+)"/)).toBe('1200')
    expect(attr(/<meta property="og:image:height" content="([^"]+)"/)).toBe('630')

    const png = readFileSync(path.join(root, 'public/og-image.png'))
    expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([1200, 630])
  })

  it('has no canonical link: the shell also serves other pages (prerender adds it to the landing page)', () => {
    expect(html).not.toMatch(/rel="canonical"|property="og:url"/)
  })

  it.each(['favicon.ico', 'favicon.svg', 'apple-touch-icon.png', 'site.webmanifest'])('links %s, which exists', (file) => {
    expect(html).toContain(`href="/${file}"`)
    expect(existsSync(path.join(root, 'public', file))).toBe(true)
  })

  it('lists manifest icons that exist', () => {
    const manifest = JSON.parse(readFileSync(path.join(root, 'public/site.webmanifest'), 'utf8')) as {
      icons: { src: string }[]
    }
    for (const icon of manifest.icons) expect(existsSync(path.join(root, 'public', icon.src))).toBe(true)
  })
})
