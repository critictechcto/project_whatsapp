import type { Schemas } from '../../api/types'
import { loadScript } from './loadScript'

type CheckoutSession = Schemas['CheckoutSession']

/**
 * How the Cashfree window ended. Whatever it says, the caller always asks the server to verify the
 * order (`POST /api/v1/billing/subscription/verify/` with `order_id`): only Cashfree's order status
 * decides whether the plan was paid for.
 */
export type CashfreeOutcome = 'finished' | 'redirecting'

type CashfreeCheckoutResult = {
  error?: { message?: string }
  redirect?: boolean
  paymentDetails?: { paymentMessage?: string }
}
type CashfreeInstance = {
  checkout(options: { paymentSessionId: string; redirectTarget: '_modal' | '_self' | '_blank' | '_top' }): Promise<CashfreeCheckoutResult>
}
type CashfreeFactory = (options: { mode: 'sandbox' | 'production' }) => CashfreeInstance

declare global {
  interface Window {
    Cashfree?: CashfreeFactory
  }
}

export type CashfreeCheckout = (session: CheckoutSession) => Promise<CashfreeOutcome>

const realCheckout: CashfreeCheckout = async (session) => {
  if (!session.payment_session_id) throw new Error('The checkout session has no Cashfree payment session')
  // Cashfree requires the SDK from its CDN (no bundled copy); scripts/csp.mjs allows its hosts.
  await loadScript('https://sdk.cashfree.com/js/v3/cashfree.js')
  const Cashfree = window.Cashfree
  if (!Cashfree) throw new Error('Cashfree Checkout did not load')

  const cashfree = Cashfree({ mode: session.mode === 'production' ? 'production' : 'sandbox' })
  // The promise settles when the buyer pays, fails or closes the modal; an error here (closing the
  // window included) still ends with a verify call, which reports what actually happened.
  const result = await cashfree.checkout({ paymentSessionId: session.payment_session_id, redirectTarget: '_modal' })
  // Some in-app browsers can't show the modal and are sent to the return URL instead; the billing
  // page verifies `?cf_order_id=` when the browser comes back.
  return result?.redirect && !result.paymentDetails && !result.error ? 'redirecting' : 'finished'
}

export const mockCheckout: CashfreeCheckout = () => new Promise((resolve) => setTimeout(() => resolve('finished'), 900))

/** Opens Cashfree Checkout as a modal. Mock mode resolves without loading Cashfree's SDK. */
export function openCashfreeCheckout(session: CheckoutSession): Promise<CashfreeOutcome> {
  return import.meta.env.VITE_API_MODE === 'mock' ? mockCheckout(session) : realCheckout(session)
}
