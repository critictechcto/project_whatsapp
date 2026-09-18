import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BrandLoader } from '../../../components/app'
import { areaRoutes } from '.'
import { canPrefetchInBackground, prefetchArea, prefetchAreasWhenIdle } from './prefetch'

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  Object.defineProperty(navigator, 'connection', { configurable: true, value: undefined })
})

function lazySpy(path: string) {
  const route = areaRoutes.find((candidate) => candidate.path === path)
  if (!route || typeof route.lazy !== 'function') throw new Error(`no lazy route ${path}`)
  return vi.spyOn(route as { lazy: () => unknown }, 'lazy')
}

describe('prefetchArea', () => {
  it("starts the area's lazy import once", () => {
    const lazy = lazySpy('contacts')
    prefetchArea('contacts')
    prefetchArea('contacts')
    expect(lazy).toHaveBeenCalledTimes(1)
  })

  it('prefetches the idle queue one area at a time', () => {
    vi.useFakeTimers()
    const lazy = lazySpy('orders')
    const cancel = prefetchAreasWhenIdle([{ to: 'orders' }])
    expect(lazy).not.toHaveBeenCalled()
    vi.advanceTimersByTime(5000)
    expect(lazy).toHaveBeenCalledTimes(1)
    cancel()
  })

  it('skips background prefetching on Data Saver and 2G', () => {
    Object.defineProperty(navigator, 'connection', { configurable: true, value: { saveData: true } })
    expect(canPrefetchInBackground()).toBe(false)
    Object.defineProperty(navigator, 'connection', { configurable: true, value: { effectiveType: 'slow-2g' } })
    expect(canPrefetchInBackground()).toBe(false)
    Object.defineProperty(navigator, 'connection', { configurable: true, value: { effectiveType: '4g' } })
    expect(canPrefetchInBackground()).toBe(true)
  })
})

describe('BrandLoader', () => {
  it('announces its label and draws the wordmark one letter at a time', () => {
    const { container } = render(<BrandLoader label="Loading orders" />)
    expect(screen.getByRole('status', { name: 'Loading orders' })).toBeInTheDocument()
    expect(container.querySelectorAll('.brand-loader-letter')).toHaveLength('UpChatz'.length)
  })
})
