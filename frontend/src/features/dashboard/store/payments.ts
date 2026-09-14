import { z } from 'zod'
import type { Tone } from '../../../components/app'
import type { PaymentAccount, PaymentAccountPatch, PaymentAccountStatus, PaymentMode, PaymentProvider } from './api'

export const RAZORPAY_KEY = /^rzp_(test|live)_[A-Za-z0-9]+$/

export const providerInfo: Record<
  PaymentProvider,
  { name: string; description: string; keyLabel: string; secretLabel: string; keyPlaceholder: string; whereToFind: string }
> = {
  razorpay: {
    name: 'Razorpay',
    description: 'Payment links on your Razorpay account. Test or live mode comes from your key.',
    keyLabel: 'Key id',
    secretLabel: 'Key secret',
    keyPlaceholder: 'rzp_live_…',
    whereToFind: 'In the Razorpay Dashboard, open Account & Settings → API Keys.',
  },
  cashfree: {
    name: 'Cashfree',
    description: 'Payment links on your Cashfree Payments account, in test (sandbox) or live mode.',
    keyLabel: 'App ID',
    secretLabel: 'Secret key',
    keyPlaceholder: 'App ID',
    whereToFind: 'In the Cashfree Merchant Dashboard, open Developers → API Keys. Test and live keys are listed separately.',
  },
}

export const accountStatusInfo: Record<PaymentAccountStatus, { label: string; tone: Tone }> = {
  not_configured: { label: 'Not connected', tone: 'neutral' },
  unverified: { label: 'Unverified', tone: 'amber' },
  verified: { label: 'Connected', tone: 'green' },
  invalid: { label: 'Invalid', tone: 'red' },
}

export const modeLabels: Record<PaymentMode, string> = { test: 'Test', live: 'Live' }

/** Razorpay's mode comes from the key prefix; null until the key looks like one. */
export function razorpayModeFromKey(keyId: string): PaymentMode | null {
  const key = keyId.trim()
  if (key.startsWith('rzp_test_')) return 'test'
  if (key.startsWith('rzp_live_')) return 'live'
  return null
}

export function hasSavedKeys(account: PaymentAccount | undefined): boolean {
  return Boolean(account && (account.key_id || account.has_key_secret))
}

export type PaymentsFormValues = { key_id: string; key_secret: string; mode: '' | PaymentMode }

/** Validation depends on the gateway and on whether a secret is already saved. */
export function paymentsSchema(provider: PaymentProvider, hasKeySecret: boolean) {
  return z
    .object({ key_id: z.string(), key_secret: z.string(), mode: z.enum(['', 'test', 'live']) })
    .superRefine((values, ctx) => {
      const issue = (path: keyof PaymentsFormValues, message: string) => ctx.addIssue({ code: 'custom', path: [path], message })
      const keyId = values.key_id.trim()
      if (provider === 'razorpay') {
        if (!keyId) issue('key_id', 'Enter your Razorpay key id.')
        else if (!RAZORPAY_KEY.test(keyId)) issue('key_id', 'Razorpay key ids start with rzp_test_ or rzp_live_.')
      } else {
        if (!keyId) issue('key_id', 'Enter your Cashfree App ID.')
        if (!values.mode) issue('mode', 'Choose Test or Live.')
      }
      if (!hasKeySecret && !values.key_secret.trim()) {
        issue('key_secret', `Enter your ${providerInfo[provider].secretLabel.toLowerCase()}.`)
      }
    })
}

export function accountToForm(account: PaymentAccount | undefined): PaymentsFormValues {
  return { key_id: account?.key_id ?? '', key_secret: '', mode: account?.provider === 'cashfree' ? (account.mode ?? '') : '' }
}

/** PATCH body. The secret is sent only when typed; Razorpay's mode is derived from the key by the API. */
export function formToAccountPatch(provider: PaymentProvider, values: PaymentsFormValues): PaymentAccountPatch {
  return {
    provider,
    key_id: values.key_id.trim(),
    ...(values.key_secret.trim() ? { key_secret: values.key_secret.trim() } : {}),
    ...(provider === 'cashfree' && values.mode ? { mode: values.mode } : {}),
  }
}
