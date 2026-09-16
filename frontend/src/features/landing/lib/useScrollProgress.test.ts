import { describe, expect, it } from 'vitest'
import { chapterAt, chapterLocalProgress, clamp01, sectionProgress } from './useScrollProgress'

describe('sectionProgress', () => {
  const base = { trackHeight: 4000, stageHeight: 800, stageTop: 64 }

  it('is 0 before the stage sticks and 1 once it is about to scroll away', () => {
    expect(sectionProgress({ ...base, trackTop: 500 })).toBe(0)
    expect(sectionProgress({ ...base, trackTop: 64 })).toBe(0)
    expect(sectionProgress({ ...base, trackTop: 64 - 1600 })).toBe(0.5)
    expect(sectionProgress({ ...base, trackTop: 64 - 3200 })).toBe(1)
    expect(sectionProgress({ ...base, trackTop: -10_000 })).toBe(1)
  })

  it('reports 0 for a track that is not taller than its stage', () => {
    expect(sectionProgress({ trackTop: -200, trackHeight: 0, stageHeight: 0 })).toBe(0)
    expect(sectionProgress({ trackTop: -200, trackHeight: 600, stageHeight: 800 })).toBe(0)
  })
})

describe('chapter helpers', () => {
  it('maps progress to one of the chapters', () => {
    expect(chapterAt(0, 5)).toBe(0)
    expect(chapterAt(0.19, 5)).toBe(0)
    expect(chapterAt(0.2, 5)).toBe(1)
    expect(chapterAt(0.59, 5)).toBe(2)
    expect(chapterAt(0.99, 5)).toBe(4)
    expect(chapterAt(1, 5)).toBe(4)
    expect(chapterAt(-1, 5)).toBe(0)
    expect(chapterAt(2, 5)).toBe(4)
    expect(chapterAt(0.7, 1)).toBe(0)
  })

  it('gives progress inside a chapter', () => {
    expect(chapterLocalProgress(0.1, 5, 0)).toBeCloseTo(0.5)
    expect(chapterLocalProgress(0.1, 5, 1)).toBe(0)
    expect(chapterLocalProgress(0.5, 5, 2)).toBeCloseTo(0.5)
    expect(chapterLocalProgress(0.5, 5, 1)).toBe(1)
    expect(chapterLocalProgress(1, 5, 4)).toBe(1)
  })

  it('clamps to 0..1', () => {
    expect(clamp01(-0.5)).toBe(0)
    expect(clamp01(0.25)).toBe(0.25)
    expect(clamp01(3)).toBe(1)
  })
})
