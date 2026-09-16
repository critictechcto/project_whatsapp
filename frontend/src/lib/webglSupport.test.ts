import { afterEach, describe, expect, it, vi } from 'vitest'
import { canUseWebGLStory } from './webglSupport'

function mockMedia({ reduce = false, fine = true } = {}) {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches:
          (reduce && query.includes('prefers-reduced-motion: reduce')) || (fine && query.includes('pointer: fine')),
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList,
  )
}

function mockWebGL2() {
  const loseContext = vi.fn()
  const getContext = vi
    .spyOn(HTMLCanvasElement.prototype, 'getContext')
    .mockImplementation(((type: string) =>
      type === 'webgl2' ? { getExtension: () => ({ loseContext }) } : null) as unknown as HTMLCanvasElement['getContext'])
  return { getContext, loseContext }
}

function setNavigatorHint(key: 'connection' | 'deviceMemory', value: unknown) {
  Object.defineProperty(navigator, key, { configurable: true, value })
}

afterEach(() => {
  delete (navigator as unknown as Record<string, unknown>).connection
  delete (navigator as unknown as Record<string, unknown>).deviceMemory
})

describe('canUseWebGLStory', () => {
  it('is true with WebGL 2, a fine pointer and no preferences against it', () => {
    mockMedia()
    const { getContext, loseContext } = mockWebGL2()
    expect(canUseWebGLStory()).toBe(true)
    expect(getContext).toHaveBeenCalledWith('webgl2')
    expect(loseContext).toHaveBeenCalled()
  })

  it('is false with reduced motion, before probing WebGL', () => {
    mockMedia({ reduce: true })
    const { getContext } = mockWebGL2()
    expect(canUseWebGLStory()).toBe(false)
    expect(getContext).not.toHaveBeenCalled()
  })

  it('is false when data saver is on', () => {
    mockMedia()
    mockWebGL2()
    setNavigatorHint('connection', { saveData: true })
    expect(canUseWebGLStory()).toBe(false)
  })

  it('is false on low-memory devices', () => {
    mockMedia()
    mockWebGL2()
    setNavigatorHint('deviceMemory', 2)
    expect(canUseWebGLStory()).toBe(false)
    setNavigatorHint('deviceMemory', 8)
    expect(canUseWebGLStory()).toBe(true)
  })

  it('is false on small touch screens', () => {
    mockMedia({ fine: false })
    mockWebGL2()
    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(390)
    expect(canUseWebGLStory()).toBe(false)
  })

  it('is false without WebGL 2', () => {
    mockMedia()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    expect(canUseWebGLStory()).toBe(false)
  })
})
