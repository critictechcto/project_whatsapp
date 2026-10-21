import { screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Schemas } from '../../../api/types'
import { formatDate } from '../../../lib/datetime'
import { server } from '../../../mocks/node'
import { daysAgo, ids } from '../../../mocks/seed'
import { apiUrl, errorResponse, http } from '../../../mocks/utils'
import { fill, renderDashboard, signIn } from '../../../test/render'
import { setMockCheckoutProvider } from './mocks'

// Tests run in live API mode; pay instantly instead of loading Razorpay or Cashfree Checkout.
vi.mock('../../../lib/integrations/razorpay', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/integrations/razorpay')>()
  return {
    ...actual,
    openRazorpayCheckout: async (session: { subscription_id: string | null; order_id: string | null }) => {
      razorpayOpened(session)
      const common = { razorpay_payment_id: 'pay_test_0001', razorpay_signature: 'test_signature' }
      return session.order_id
        ? { ...common, razorpay_order_id: session.order_id }
        : { ...common, razorpay_subscription_id: session.subscription_id ?? '' }
    },
  }
})

const razorpayOpened = vi.fn()
const cashfreeOpened = vi.fn()
vi.mock('../../../lib/integrations/cashfree', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/integrations/cashfree')>()
  return {
    ...actual,
    openCashfreeCheckout: async (session: unknown) => {
      cashfreeOpened(session)
      return 'finished'
    },
  }
})

afterEach(() => {
  vi.useRealTimers()
  cashfreeOpened.mockReset()
  razorpayOpened.mockReset()
  setMockCheckoutProvider('razorpay')
})

async function fillSharmaProfile(user: Awaited<ReturnType<typeof renderDashboard>>['user']) {
  await fill(user, await screen.findByLabelText(/^Legal name/), 'Sharma Sweets Private Limited')
  await user.type(screen.getByLabelText(/^GSTIN/), '08aabcs1429b1zx')
  expect(screen.getByLabelText(/^State/)).toHaveValue('08')
  const email = screen.getByLabelText(/^Invoice email/)
  await user.clear(email)
  await fill(user, email, 'accounts@sharmasweets.in')
  await fill(user, screen.getByLabelText(/^Address line 1/), 'Shop 12, Johari Bazar')
  await user.type(screen.getByLabelText(/^City/), 'Jaipur')
  await user.type(screen.getByLabelText(/^PIN code/), '302003')
}

const kaveriPeriodEnd = () => daysAgo(-325)

describe('billing', () => {
  it('defaults to auto-pay, collects billing details without a phone, and waits for the subscription to activate', async () => {
    signIn()
    const { user, router } = renderDashboard(`/app/w/${ids.sharmaSweets}/billing/plans`)

    expect(await screen.findByRole('radio', { name: 'Auto-pay' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: 'Pay once' })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText(/Charged automatically each month or year by UPI AutoPay or card/)).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Choose Growth' }))

    // billing_profile_required → billing details form
    expect(await screen.findByRole('heading', { level: 1, name: 'Billing details' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(`/app/w/${ids.sharmaSweets}/billing/profile`)
    expect(new URLSearchParams(router.state.location.search).get('next')).toBe('plans')

    // Razorpay doesn't need a phone number.
    expect(await screen.findByText('For payment receipts.')).toBeInTheDocument()
    expect(screen.queryByText(/Cashfree/)).not.toBeInTheDocument()
    await fillSharmaProfile(user)
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))

    // Back on plans with a resume prompt
    await user.click(await screen.findByRole('button', { name: 'Continue to payment' }))

    // Verified, but Razorpay hasn't confirmed the charge yet
    expect(await screen.findByRole('heading', { level: 1, name: 'Billing' })).toBeInTheDocument()
    expect(await screen.findByText('Confirming your payment…')).toBeInTheDocument()
    expect(cashfreeOpened).not.toHaveBeenCalled()
    expect(razorpayOpened).toHaveBeenCalledWith(
      expect.objectContaining({ provider: 'razorpay', payment_mode: 'autopay', subscription_id: expect.stringMatching(/^sub_/), order_id: null }),
    )
    expect(screen.getByText('Not added')).toBeInTheDocument()

    // Move the clock past the (mock) confirmation time; the page's subscription poll picks it up.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(Date.now() + 10_000)

    await waitFor(() => expect(screen.queryByText('Confirming your payment…')).not.toBeInTheDocument(), { timeout: 8000 })
    expect(await screen.findByText(/Renews automatically on/)).toBeInTheDocument()
    expect(screen.getByText('Razorpay, auto-pay')).toBeInTheDocument()
    expect(screen.getAllByText('Active').length).toBeGreaterThan(0)
  }, 30_000)

  it('pays once with Razorpay and activates a prepaid plan at once', async () => {
    signIn()
    const { user } = renderDashboard(`/app/w/${ids.sharmaSweets}/billing/plans`)

    await user.click(await screen.findByRole('radio', { name: 'Pay once' }))
    expect(screen.getByText(/Pay for a month or a year at a time; nothing is charged automatically/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Choose Growth' }))

    // The chosen payment mode survives the billing details detour.
    expect(await screen.findByRole('heading', { level: 1, name: 'Billing details' })).toBeInTheDocument()
    await fillSharmaProfile(user)
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))
    expect(await screen.findByRole('radio', { name: 'Pay once' })).toHaveAttribute('aria-checked', 'true')
    await user.click(await screen.findByRole('button', { name: 'Continue to payment' }))

    expect(await screen.findByText("You're on the Growth plan")).toBeInTheDocument()
    expect(razorpayOpened).toHaveBeenCalledWith(
      expect.objectContaining({ provider: 'razorpay', payment_mode: 'one_time', order_id: expect.stringMatching(/^order_/), subscription_id: null }),
    )
    expect(await screen.findByText(/^Paid until .*Nothing is charged automatically/)).toBeInTheDocument()
    expect(screen.queryByText(/Renews automatically/)).not.toBeInTheDocument()
    expect(screen.getByText('Razorpay, paid once')).toBeInTheDocument()

    // Renew pays once again for the same plan and cycle.
    razorpayOpened.mockClear()
    await user.click(screen.getByRole('button', { name: 'Renew' }))
    expect(await screen.findByText(/^Your Growth plan is paid until/)).toBeInTheDocument()
    expect(razorpayOpened).toHaveBeenCalledWith(expect.objectContaining({ payment_mode: 'one_time' }))
  }, 30_000)

  it('keeps a pay-once plan from switching to auto-pay until its period ends', async () => {
    signIn(ids.farhan)
    const { user } = renderDashboard(`/app/w/${ids.kaveriClinic}/billing/plans?interval=annual`)

    expect(await screen.findByText('You can switch to auto-pay when your paid period ends.')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Choose Growth' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Current plan' })).toBeDisabled()

    await user.click(screen.getByRole('radio', { name: 'Pay once' }))
    expect(screen.queryByText('You can switch to auto-pay when your paid period ends.')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Choose Growth' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Renew Starter' })).toBeEnabled()
  })

  it('requires a valid phone, pays with Cashfree and activates the plan at once', async () => {
    setMockCheckoutProvider('cashfree')
    signIn()
    const { user, router } = renderDashboard(`/app/w/${ids.sharmaSweets}/billing/plans`)

    expect(await screen.findByText(/Payments are processed by Cashfree\. You pay for a month or a year at a time/)).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Choose Growth' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Billing details' })).toBeInTheDocument()
    expect(await screen.findByText('Cashfree needs a phone number for payment receipts.')).toBeInTheDocument()
    await fill(user, await screen.findByLabelText(/^Legal name/), 'Sharma Sweets')
    const email = screen.getByLabelText(/^Invoice email/)
    await user.clear(email)
    await fill(user, email, 'accounts@sharmasweets.in')
    await fill(user, screen.getByLabelText(/^Address line 1/), 'Shop 12, Johari Bazar')
    await user.type(screen.getByLabelText(/^City/), 'Jaipur')
    await user.selectOptions(screen.getByLabelText(/^State/), '08')
    await user.type(screen.getByLabelText(/^PIN code/), '302003')

    // Missing, then malformed, phone numbers are caught before saving.
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))
    expect(await screen.findByText('Enter a phone number.')).toBeInTheDocument()
    const phone = screen.getByLabelText(/^Phone/)
    await user.type(phone, '12345')
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))
    expect(await screen.findByText(/Enter a 10-digit mobile number/)).toBeInTheDocument()
    expect(phone).toHaveAttribute('aria-invalid', 'true')
    await user.clear(phone)
    await user.type(phone, '98290 12345')
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))

    await user.click(await screen.findByRole('button', { name: 'Continue to payment' }))

    expect(await screen.findByText("You're on the Growth plan")).toBeInTheDocument()
    expect(cashfreeOpened).toHaveBeenCalledWith(
      expect.objectContaining({ provider: 'cashfree', mode: 'sandbox', order_id: expect.stringMatching(/^upc_/) }),
    )
    expect(router.state.location.pathname).toBe(`/app/w/${ids.sharmaSweets}/billing`)
    expect(await screen.findByText(/^Paid until .*Nothing is charged automatically/)).toBeInTheDocument()
    expect(screen.queryByText(/Renews automatically/)).not.toBeInTheDocument()
    expect(screen.getAllByText('Active').length).toBeGreaterThan(0)
    expect(screen.getByText('+919829012345')).toBeInTheDocument()
  }, 30_000)

  it("tells the owner they weren't charged when the Cashfree payment wasn't completed", async () => {
    server.use(
      http.untyped.post(apiUrl('/api/v1/billing/subscription/verify/'), () =>
        errorResponse(409, 'payment_not_completed', "The payment wasn't completed. You haven't been charged."),
      ),
    )
    setMockCheckoutProvider('cashfree')
    signIn(ids.farhan)
    const { user, router } = renderDashboard(`/app/w/${ids.kaveriClinic}/billing/plans`)

    expect(await screen.findByText("Your new plan starts now. Unused days on the current plan aren't refunded.", { exact: false })).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Choose Growth' }))

    expect(await screen.findByText('Payment not completed')).toBeInTheDocument()
    expect(screen.getByText("You haven't been charged.")).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(`/app/w/${ids.kaveriClinic}/billing/plans`)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose Growth' })).toBeEnabled())
    // The prepaid plan is still current and can be renewed from here.
    expect(screen.getByRole('button', { name: 'Choose Starter' })).toBeInTheDocument()
  })

  it('renews a Cashfree plan from the end of the paid period', async () => {
    setMockCheckoutProvider('cashfree')
    signIn(ids.farhan)
    const { user } = renderDashboard(`/app/w/${ids.kaveriClinic}/billing`)

    const periodEnd = formatDate(kaveriPeriodEnd(), 'Asia/Kolkata')
    expect(await screen.findByText(new RegExp(`^Paid until ${periodEnd}`))).toBeInTheDocument()
    expect(screen.queryByText(/Your plan ends in/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Renew' }))

    const renewedEnd = formatDate(new Date(new Date(kaveriPeriodEnd()).getTime() + 365 * 86_400_000).toISOString(), 'Asia/Kolkata')
    expect(await screen.findByText(`Your Starter plan is paid until ${renewedEnd}.`)).toBeInTheDocument()
    expect(cashfreeOpened).toHaveBeenCalledTimes(1)
    expect(await screen.findByText(new RegExp(`^Paid until ${renewedEnd}`))).toBeInTheDocument()
  })

  it('warns in the last 7 days of a prepaid plan', async () => {
    server.use(
      http.untyped.get(apiUrl('/api/v1/billing/subscription/'), () =>
        Response.json({
          plan: { id: 'starter', name: 'Starter', monthly_price_paise: 99900, annual_price_paise: 999000, limits: { whatsapp_numbers: 1, members: 2, contacts: 5000 }, features: [] },
          status: 'active',
          interval: 'monthly',
          trial_ends_at: null,
          current_period_start: daysAgo(27),
          current_period_end: new Date(Date.now() + 2.5 * 86_400_000).toISOString(),
          cancel_at_period_end: false,
          provider: 'cashfree',
          payment_mode: 'one_time',
          auto_renews: false,
          gst_rate_percent: 0,
          checkout_provider: 'cashfree',
        } satisfies Schemas['Subscription']),
      ),
    )
    signIn(ids.farhan)
    renderDashboard(`/app/w/${ids.kaveriClinic}/billing`)

    expect(await screen.findByText('Your plan ends in 3 days')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Renew' })).toBeInTheDocument()
  })

  it('verifies a Cashfree order when the browser returns with cf_order_id', async () => {
    const bodies: unknown[] = []
    server.use(
      http.untyped.post(apiUrl('/api/v1/billing/subscription/verify/'), async ({ request }) => {
        bodies.push(await request.json())
        return errorResponse(409, 'payment_not_completed', "The payment wasn't completed. You haven't been charged.")
      }),
    )
    signIn(ids.farhan)
    const { router } = renderDashboard(`/app/w/${ids.kaveriClinic}/billing?cf_order_id=upc_0123456789abcdef0123456789abcdef`)

    expect(await screen.findByText('Payment not completed')).toBeInTheDocument()
    expect(bodies).toEqual([{ order_id: 'upc_0123456789abcdef0123456789abcdef' }])
    expect(new URLSearchParams(router.state.location.search).has('cf_order_id')).toBe(false)
  })

  it('requires the state to match the GSTIN', async () => {
    signIn()
    const { user } = renderDashboard(`/app/w/${ids.sharmaSweets}/billing/profile`)

    await fill(user, await screen.findByLabelText(/^Legal name/), 'Sharma Sweets Private Limited')
    await user.type(screen.getByLabelText(/^GSTIN/), '08AABCS1429B1ZX')
    await user.selectOptions(screen.getByLabelText(/^State/), '27')
    await user.type(screen.getByLabelText(/^Phone/), '9829012345')
    await fill(user, screen.getByLabelText(/^Address line 1/), 'Shop 12, Johari Bazar')
    await user.type(screen.getByLabelText(/^City/), 'Jaipur')
    await user.type(screen.getByLabelText(/^PIN code/), '302003')
    await user.click(screen.getByRole('button', { name: 'Save billing details' }))

    expect(await screen.findByText('Must match the first two digits of the GSTIN.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^State/)).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows invoices in rupees without GST columns and hides owner actions from admins', async () => {
    signIn()
    renderDashboard(`/app/w/${ids.kaveriClinic}/billing`)

    expect((await screen.findAllByText('UPC/2026-27/000142')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('₹9,990.00').length).toBeGreaterThan(0)
    expect(screen.queryByRole('columnheader', { name: 'GST' })).not.toBeInTheDocument()
    expect(screen.getByText('₹9,990 / year')).toBeInTheDocument()
    expect(screen.getByText('Only the workspace owner can change the plan or cancel.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel plan' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Renew' })).not.toBeInTheDocument()
  })

  it('shows the GST breakdown on invoices that charged GST', async () => {
    server.use(
      http.untyped.get(apiUrl('/api/v1/billing/invoices/'), () =>
        Response.json({
          next: null,
          previous: null,
          results: [
            {
              id: '7b3c0d64-5f1e-4c55-9a0b-2b7f1c9e0a11',
              number: 'UPC/2026-27/000150',
              status: 'paid',
              issued_at: daysAgo(10),
              period_start: daysAgo(10),
              period_end: daysAgo(-355),
              subtotal_paise: 999000,
              cgst_paise: 89910,
              sgst_paise: 89910,
              igst_paise: 0,
              total_paise: 1178820,
              download_url: null,
            },
          ] satisfies Schemas['Invoice'][],
        }),
      ),
    )
    signIn()
    renderDashboard(`/app/w/${ids.kaveriClinic}/billing`)

    expect((await screen.findAllByText('CGST ₹899.10')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('₹11,788.20').length).toBeGreaterThan(0)
  })
})
