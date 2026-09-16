import { describe, expect, it } from 'vitest'
import { describeDeliveryError } from './deliveryError'

describe('describeDeliveryError', () => {
  it('explains the payment method error in plain language', () => {
    const error = describeDeliveryError('131042', 'Business eligibility payment issue')
    expect(error.summary).toBe('Not delivered: add a payment method in WhatsApp Manager.')
    expect(error.action).toMatch(/WhatsApp Manager/)
    expect(error.known).toBe(true)
  })

  it("falls back to Meta's message, then to a generic line", () => {
    expect(describeDeliveryError('999999', 'Something odd happened')).toEqual({
      summary: 'Not delivered: Something odd happened',
      known: false,
    })
    expect(describeDeliveryError('', '  ').summary).toBe('Not delivered.')
    expect(describeDeliveryError(null).summary).toBe('Not delivered.')
  })
})
