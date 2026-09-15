import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ids } from '../../../mocks/seed'
import { findDialog, renderDashboard, signIn } from '../../../test/render'
import { platformState, PLATFORM_DISPLAY_NUMBER, storeState, type MockRecipient } from './mockState'

const alertsPath = `/app/w/${ids.sharmaSweets}/store/alerts`
const lazy = { timeout: 10_000 }

function addRecipient(patch: Partial<MockRecipient>) {
  const recipients = storeState(ids.sharmaSweets).recipients
  recipients.push({ ...recipients[0], id: `recipient-${recipients.length}`, verified_at: null, status: 'pending', ...patch })
}

describe('order alerts', () => {
  it('adds a number and explains the confirmation message', async () => {
    signIn()
    const { user } = renderDashboard(alertsPath)

    const table = await screen.findByRole('table', { name: 'Numbers that get order alerts' }, lazy)
    expect(await within(table).findByText('Rohit Sharma')).toBeInTheDocument()
    expect(within(within(table).getByRole('row', { name: /Rohit Sharma/ })).getByText('Confirmed')).toBeInTheDocument()
    expect(screen.getByText('ORDERS')).toBeInTheDocument()
    expect(screen.getByText('STOP')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add number' }))
    const dialog = await findDialog({ name: 'Add alert number' })
    expect(dialog).toHaveTextContent(`You'll get a WhatsApp message from UpChatz (${PLATFORM_DISPLAY_NUMBER}) — tap Confirm`)

    await user.click(within(dialog).getByRole('button', { name: 'Add and send confirmation' }))
    expect(await within(dialog).findByText('Enter a name.')).toBeInTheDocument()
    expect(within(dialog).getByText('Enter a 10-digit Indian mobile number.')).toBeInTheDocument()

    await user.type(within(dialog).getByLabelText(/^Name/), 'Priya Verma')
    await user.type(within(dialog).getByLabelText(/^WhatsApp number/), '9876543210')
    await user.click(within(dialog).getByRole('checkbox', { name: /^Cancelled orders/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Add and send confirmation' }))

    expect(await within(table).findByText('Priya Verma')).toBeInTheDocument()
    expect(within(table).getByText('Waiting for Confirm')).toBeInTheDocument()
    const created = storeState(ids.sharmaSweets).recipients.find((recipient) => recipient.name === 'Priya Verma')
    expect(created).toMatchObject({ phone_e164: '+919876543210', status: 'pending', events: ['new_order', 'needs_attention'] })
  })

  it('resends a confirmation and explains when it was sent too recently', async () => {
    addRecipient({ name: 'Anil Kumar', phone_e164: '+919811100001', last_sent_at: new Date().toISOString() })
    addRecipient({ name: 'Sunita Devi', phone_e164: '+919811100002', last_sent_at: new Date(Date.now() - 60 * 60_000).toISOString() })
    signIn()
    const { user } = renderDashboard(alertsPath)

    await user.click(await screen.findByRole('button', { name: 'Resend confirmation to Anil Kumar' }, lazy))
    expect(await screen.findByText(/We sent a confirmation less than 5 minutes ago/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Resend confirmation to Sunita Devi' }))
    expect(await screen.findByText('Confirmation sent')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Resend confirmation to Rohit Sharma' })).not.toBeInTheDocument()
  })

  it('stops at three numbers', async () => {
    addRecipient({ name: 'Anil Kumar', phone_e164: '+919811100001' })
    signIn()
    const { user } = renderDashboard(alertsPath)

    await user.click(await screen.findByRole('button', { name: 'Add number' }, lazy))
    const dialog = await findDialog({ name: 'Add alert number' })
    await user.type(within(dialog).getByLabelText(/^Name/), 'Meena')
    await user.type(within(dialog).getByLabelText(/^WhatsApp number/), '9811100003')
    // Someone else adds the third number meanwhile.
    addRecipient({ name: 'Sunita Devi', phone_e164: '+919811100002' })
    await user.click(within(dialog).getByRole('button', { name: 'Add and send confirmation' }))
    expect(await within(dialog).findByText('You can have up to 3 alert numbers. Remove one to add another.')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Add number' })).toBeDisabled())
    expect(screen.getByText("You've added the maximum of 3 numbers. Remove one to add another.")).toBeInTheDocument()
  })

  it('removes a number', async () => {
    signIn()
    const { user } = renderDashboard(alertsPath)

    await user.click(await screen.findByRole('button', { name: 'Remove Rohit Sharma' }, lazy))
    const dialog = await findDialog({ name: 'Remove Rohit Sharma?' })
    await user.click(within(dialog).getByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(storeState(ids.sharmaSweets).recipients).toHaveLength(0))
    expect(await screen.findByText('No alert numbers yet')).toBeInTheDocument()
  })

  it('explains when platform alerts are unavailable', async () => {
    platformState().available = false
    signIn()
    renderDashboard(alertsPath)

    expect(await screen.findByText("Order alerts aren't available yet", {}, lazy)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add number' })).toBeDisabled()
  })
})
