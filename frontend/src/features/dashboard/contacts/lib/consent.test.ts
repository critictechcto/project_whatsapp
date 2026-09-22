import { describe, expect, it } from 'vitest'
import { normalizeKeyword } from './consent'

describe('normalizeKeyword', () => {
  it('ignores case, spacing and trailing punctuation like the backend', () => {
    expect(normalizeKeyword('  Band   KARO!! ')).toBe('band karo')
    expect(normalizeKeyword('Subscribe.')).toBe('subscribe')
    expect(normalizeKeyword('हाँ।')).toBe('हाँ')
    expect(normalizeKeyword('!!!')).toBe('')
  })
})
