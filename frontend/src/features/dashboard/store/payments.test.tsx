import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ids } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'
import { storeState } from './mockState'
import { formToAccountPatch, paymentsSchema, razorpayModeFromKey } from './payments'

const paymentsPath = `/app/w/${ids.sharmaSweets}/store/payments`
const lazy = { timeout: 10_000 }

describe('payments helpers', () => {
  it('derives the Razorpay mode from the key and requires a Cashfree mode', () => {
    expect(razorpayModeFromKey('rzp_test_abc')).toBe('test')
    expect(razorpayModeFromKey('rzp_live_abc')).toBe('live')
    expect(razorpayModeFromKey('abc')).toBeNull()

    const issues = (provider: 'razorpay' | 'cashfree', values: { key_id: string; key_secret: string; mode: '' | 'test' | 'live' }, hasSecret = false) => {
      const result = paymentsSchema(provider, hasSecret).safeParse(values)
      return result.success ? [] : result.error.issues.map((issue) => issue.message)
    }
    expect(issues('razorpay', { key_id: 'key_123', key_secret: 'x', mode: '' })).toContain('Razorpay key ids start with rzp_test_ or rzp_live_.')
    expect(issues('razorpay', { key_id: 'rzp_test_1', key_secret: '', mode: '' }, true)).toEqual([])
    expect(issues('cashfree', { key_id: 'TEST1', key_secret: 'x', mode: '' })).toContain('Choose Test or Live.')

    expect(formToAccountPatch('razorpay', { key_id: 'rzp_live_1', key_secret: '', mode: 'test' })).toEqual({ provider: 'razorpay', key_id: 'rzp_live_1' })
  })
})

describe('payments page', () => {
  it('shows the mode from the key, saves the secret without showing it, and verifies', async () => {
    signIn()
    const { user } = renderDashboard(paymentsPath)

    const keyId = await screen.findByLabelText(/^Key id/, {}, lazy)
    expect(keyId).toHaveValue('rzp_test_Sh4rmaSw33ts01')
    expect(screen.getByText(/^Mode:/)).toHaveTextContent('Mode: Test')
    expect(screen.getByText('No webhook setup needed — we confirm payments automatically.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Verify' })).toBeDisabled()

    await user.clear(keyId)
    await user.type(keyId, 'rzp_live_Sh4rma')
    expect(screen.getByText(/^Mode:/)).toHaveTextContent('Mode: Live')
    await user.clear(keyId)
    await user.type(keyId, 'rzp_test_Sh4rmaSw33ts02')

    const secret = screen.getByLabelText(/^Key secret/)
    await user.type(secret, 'topSecretValue42')
    await user.click(screen.getByRole('button', { name: 'Save keys' }))

    await waitFor(() => expect(storeState(ids.sharmaSweets).account.key_secret).toBe('topSecretValue42'))
    await waitFor(() => expect(screen.getByLabelText(/^Key secret/)).toHaveValue(''))
    expect(screen.getByLabelText(/^Key secret/)).toHaveAttribute('placeholder', 'Saved')
    expect(screen.queryByDisplayValue('topSecretValue42')).not.toBeInTheDocument()
    expect(document.body).not.toHaveTextContent('topSecretValue42')

    const verify = screen.getByRole('button', { name: 'Verify' })
    await waitFor(() => expect(verify).toBeEnabled())
    await user.click(verify)
    expect(await screen.findByText('Connected')).toBeInTheDocument()
    expect(screen.getByText(/^Verified/)).toBeInTheDocument()
    expect(storeState(ids.sharmaSweets).account.status).toBe('verified')
  })

  it('shows the gateway error when the keys are invalid', async () => {
    signIn()
    const { user } = renderDashboard(paymentsPath)

    const keyId = await screen.findByLabelText(/^Key id/, {}, lazy)
    await user.clear(keyId)
    await user.type(keyId, 'rzp_live_Wr0ngKey')
    await user.type(screen.getByLabelText(/^Key secret/), 'nope')
    await user.click(screen.getByRole('button', { name: 'Save keys' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Verify' })).toBeEnabled())

    await user.click(screen.getByRole('button', { name: 'Verify' }))
    const alert = await screen.findByText("Razorpay didn't accept these keys")
    expect(alert.closest('[role="alert"]')).toHaveTextContent('Razorpay rejected these keys (401 Unauthorized)')
    expect(screen.getByText('Invalid')).toBeInTheDocument()
    expect(storeState(ids.sharmaSweets).account.status).toBe('invalid')
  })

  it('warns before switching gateway, then requires a Cashfree mode', async () => {
    signIn()
    const { user } = renderDashboard(paymentsPath)

    await user.click(await screen.findByRole('radio', { name: /^Cashfree/ }, lazy))
    const dialog = await screen.findByRole('dialog', { name: 'Switch to Cashfree?' })
    expect(dialog).toHaveTextContent('Your saved Razorpay keys will be cleared')
    await user.click(within(dialog).getByRole('button', { name: 'Switch and clear keys' }))
    await waitFor(() => expect(storeState(ids.sharmaSweets).account.provider).toBe('cashfree'))
    expect(storeState(ids.sharmaSweets).account.key_id).toBe('')

    await user.type(await screen.findByLabelText(/^App ID/), 'TEST10293847')
    await user.type(screen.getByLabelText(/^Secret key/), 'cfsk_ma_test_secret')
    await user.click(screen.getByRole('button', { name: 'Save keys' }))
    expect(await screen.findByText('Choose Test or Live.')).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: /^Test \(sandbox\)/ }))
    await user.click(screen.getByRole('button', { name: 'Save keys' }))
    await waitFor(() => expect(storeState(ids.sharmaSweets).account.mode).toBe('test'))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Verify' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'Verify' }))
    expect(await screen.findByText('Connected')).toBeInTheDocument()
  })

  it('keeps the webhook section collapsed until opened, and rotates the URL', async () => {
    signIn()
    const { user } = renderDashboard(paymentsPath)

    const toggle = await screen.findByRole('button', { name: /^Faster confirmation \(optional\)/ }, lazy)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByLabelText('Webhook URL')).not.toBeInTheDocument()

    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const url = screen.getByLabelText('Webhook URL')
    expect(url).toHaveValue('https://api.upchatz.com/webhooks/payments/merchants/whk_sharma_0001/')
    expect(within(screen.getByRole('list', { name: 'Webhook events' })).getAllByRole('listitem').length).toBeGreaterThan(0)
    expect(screen.getByLabelText(/^Webhook secret/)).toHaveValue('')

    await user.click(screen.getByRole('button', { name: 'Rotate URL' }))
    const dialog = await screen.findByRole('dialog', { name: 'Rotate the webhook URL?' })
    await user.click(within(dialog).getByRole('button', { name: 'Rotate URL' }))
    await waitFor(() => expect(screen.getByLabelText('Webhook URL')).not.toHaveValue('https://api.upchatz.com/webhooks/payments/merchants/whk_sharma_0001/'))
  })
})
