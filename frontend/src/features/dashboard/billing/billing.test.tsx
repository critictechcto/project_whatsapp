import { screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ids } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'

// Tests run in live API mode; pay instantly instead of loading Razorpay Checkout.
vi.mock('../../../lib/integrations/razorpay', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/integrations/razorpay')>()
  return {
    ...actual,
    openRazorpayCheckout: async (session: { subscription_id: string }) => ({
      razorpay_payment_id: 'pay_test_0001',
      razorpay_subscription_id: session.subscription_id,
      razorpay_signature: 'test_signature',
    }),
  }
})

afterEach(() => {
  vi.useRealTimers()
})

describe('billing', () => {
  it('collects billing details, pays, and waits for the subscription to activate', async () => {
    signIn()
    const { user, router } = renderDashboard(`/app/w/${ids.sharmaSweets}/billing/plans`)

    await user.click(await screen.findByRole('button', { name: 'Choose Growth' }))

    // billing_profile_required → billing details form
    expect(await screen.findByRole('heading', { level: 1, name: 'Billing details' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(`/app/w/${ids.sharmaSweets}/billing/profile`)
    expect(new URLSearchParams(router.state.location.search).get('next')).toBe('plans')

    await user.type(await screen.findByLabelText(/^Legal name/), 'Sharma Sweets Private Limited')
    await user.type(screen.getByLabelText(/^GSTIN/), '08aabcs1429b1zx')
    expect(screen.getByLabelText(/^State/)).toHaveValue('08')
    const email = screen.getByLabelText(/^Invoice email/)
    await user.clear(email)
    await user.type(email, 'accounts@sharmasweets.in')
    await user.type(screen.getByLabelText(/^Address line 1/), 'Shop 12, Johari Bazar')
    await user.type(screen.getByLabelText(/^City/), 'Jaipur')
    await user.type(screen.getByLabelText(/^PIN code/), '302003')
    await user.click(screen.getByRole('button', { name: 'Save and continue' }))

    // Back on plans with a resume prompt
    await user.click(await screen.findByRole('button', { name: 'Continue to payment' }))

    // Verified, but Razorpay hasn't confirmed the charge yet
    expect(await screen.findByRole('heading', { level: 1, name: 'Billing' })).toBeInTheDocument()
    expect(await screen.findByText('Confirming your payment…')).toBeInTheDocument()

    // Move the clock past the (mock) confirmation time; the page's subscription poll picks it up.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(Date.now() + 10_000)

    await waitFor(() => expect(screen.queryByText('Confirming your payment…')).not.toBeInTheDocument(), { timeout: 8000 })
    expect(await screen.findByText(/Renews automatically on/)).toBeInTheDocument()
    expect(screen.getAllByText('Active').length).toBeGreaterThan(0)
  }, 30_000)

  it('requires the state to match the GSTIN', async () => {
    signIn()
    const { user } = renderDashboard(`/app/w/${ids.sharmaSweets}/billing/profile`)

    await user.type(await screen.findByLabelText(/^Legal name/), 'Sharma Sweets Private Limited')
    await user.type(screen.getByLabelText(/^GSTIN/), '08AABCS1429B1ZX')
    await user.selectOptions(screen.getByLabelText(/^State/), '27')
    await user.type(screen.getByLabelText(/^Address line 1/), 'Shop 12, Johari Bazar')
    await user.type(screen.getByLabelText(/^City/), 'Jaipur')
    await user.type(screen.getByLabelText(/^PIN code/), '302003')
    await user.click(screen.getByRole('button', { name: 'Save billing details' }))

    expect(await screen.findByText('Must match the first two digits of the GSTIN.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^State/)).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows GST invoices in rupees and hides owner actions from admins', async () => {
    signIn()
    renderDashboard(`/app/w/${ids.kaveriClinic}/billing`)

    expect((await screen.findAllByText('UPC/2026-27/000142')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('₹11,788.20').length).toBeGreaterThan(0)
    expect(screen.getAllByText('CGST ₹899.10').length).toBeGreaterThan(0)
    expect(screen.getByText('Only the workspace owner can change the plan or cancel.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel subscription' })).not.toBeInTheDocument()
  })
})
