import type { Schemas } from '../../api/types'
import { loadScript } from './loadScript'

export type CheckoutSession = Schemas['CheckoutSession']

/** Post this to `POST /api/v1/billing/subscription/verify/`. */
export type CheckoutResult = {
  razorpay_payment_id: string
  razorpay_subscription_id: string
  razorpay_signature: string
}

export class CheckoutDismissed extends Error {
  constructor() {
    super('Payment window closed before completing the payment.')
    this.name = 'CheckoutDismissed'
  }
}

type RazorpayInstance = { open(): void; on(event: string, handler: (response: { error?: { description?: string } }) => void): void }
type RazorpayConstructor = new (options: Record<string, unknown>) => RazorpayInstance

declare global {
  interface Window {
    Razorpay?: RazorpayConstructor
  }
}

export type RazorpayCheckout = (session: CheckoutSession) => Promise<CheckoutResult>

const realCheckout: RazorpayCheckout = async (session) => {
  await loadScript('https://checkout.razorpay.com/v1/checkout.js')
  const Razorpay = window.Razorpay
  if (!Razorpay) throw new Error('Razorpay Checkout did not load')

  return new Promise<CheckoutResult>((resolve, reject) => {
    const checkout = new Razorpay({
      key: session.key_id,
      subscription_id: session.subscription_id,
      name: session.name,
      description: session.description,
      prefill: session.prefill,
      theme: { color: '#1d7f55' },
      handler: (response: CheckoutResult) => resolve(response),
      modal: { ondismiss: () => reject(new CheckoutDismissed()) },
    })
    checkout.on('payment.failed', (response) => {
      reject(new Error(response.error?.description ?? 'Payment failed'))
    })
    checkout.open()
  })
}

export const mockCheckout: RazorpayCheckout = (session) =>
  new Promise((resolve) =>
    setTimeout(
      () =>
        resolve({
          razorpay_payment_id: `pay_mock${Date.now()}`,
          razorpay_subscription_id: session.subscription_id,
          razorpay_signature: 'mock_signature',
        }),
      900,
    ),
  )

/** Opens Razorpay Checkout for a subscription. Mock mode resolves without loading Razorpay. */
export function openRazorpayCheckout(session: CheckoutSession): Promise<CheckoutResult> {
  return import.meta.env.VITE_API_MODE === 'mock' ? mockCheckout(session) : realCheckout(session)
}
