import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ids, seedTemplates } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'
import { storeState } from './mockState'
import { settingsSchema, settingsToForm } from './settingsForm'

const storePath = `/app/w/${ids.sharmaSweets}/store`
const lazy = { timeout: 10_000 }

describe('booking settings', () => {
  it('validates days, windows and numbers', () => {
    const values = settingsToForm(storeState(ids.sharmaSweets).settings)
    expect(values.booking_windows).toHaveLength(3)
    const messages = (patch: Partial<typeof values>) => {
      const result = settingsSchema.safeParse({ ...values, ...patch })
      return result.success ? [] : result.error.issues.map((issue) => issue.message)
    }
    expect(messages({})).toEqual([])
    expect(messages({ booking_days: [] })).toContain('Pick at least one day you take bookings.')
    expect(messages({ booking_windows: [{ label: 'Late', start: '20:00', end: '19:00' }] })).toContain('End after the start time.')
    expect(messages({ booking_windows: [] })).toContain('Add at least one time window.')
    expect(messages({ booking_days_ahead: '31' })).toContain('Enter a whole number from 1 to 30.')
    expect(messages({ booking_reminder_hours: '49' })).toContain('Enter a whole number from 0 to 48.')
  })

  it('edits days, windows, pay at the shop and reminders, and saves', async () => {
    signIn()
    const { user } = renderDashboard(`${storePath}/settings`)

    const scope = within(await screen.findByRole('region', { name: 'Bookings' }, lazy))
    await user.click(scope.getByRole('switch', { name: /^Offer pay at the shop/ }))
    await user.click(scope.getByRole('checkbox', { name: 'Sun' }))

    await user.click(scope.getByRole('button', { name: 'Add window' }))
    const list = scope.getByRole('list', { name: 'Time windows' })
    const added = within(list).getAllByRole('listitem')[3]
    await user.type(within(added).getByLabelText(/^Window 4 name/), 'Late')
    fireEvent.change(within(added).getByLabelText(/^Starts/), { target: { value: '20:00' } })
    fireEvent.change(within(added).getByLabelText(/^Ends/), { target: { value: '19:00' } })

    const daysAhead = scope.getByLabelText(/^Days shown ahead/)
    await user.clear(daysAhead)
    await user.type(daysAhead, '14')
    const reminder = scope.getByLabelText(/^Reminder \(hours before\)/)
    await user.clear(reminder)
    await user.type(reminder, '0')
    const eveningBefore = scope.getByRole('switch', { name: /^Reminder the evening before \(6 pm\)/ })
    expect(eveningBefore).toBeChecked()
    await user.click(eveningBefore)

    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(await screen.findByText('End after the start time.')).toBeInTheDocument()
    expect(storeState(ids.sharmaSweets).settings.booking_days_ahead).toBe(7)

    fireEvent.change(within(added).getByLabelText(/^Ends/), { target: { value: '21:30' } })
    await user.click(within(list).getByRole('button', { name: 'Remove Morning' }))
    expect(within(list).getAllByRole('listitem')).toHaveLength(3)

    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    await waitFor(() => expect(storeState(ids.sharmaSweets).settings.booking_days_ahead).toBe(14))
    const saved = storeState(ids.sharmaSweets).settings
    expect(saved.pay_at_shop_enabled).toBe(false)
    expect(saved.booking_days).toEqual([0, 1, 2, 3, 4, 5])
    expect(saved.booking_reminder_hours).toBe(0)
    expect(saved.booking_day_before_reminder).toBe(false)
    expect(saved.booking_windows).toEqual([
      { label: 'Afternoon', start: '12:00', end: '16:00' },
      { label: 'Evening', start: '16:00', end: '20:00' },
      { label: 'Late', start: '20:00', end: '21:30' },
    ])
  })

  it('keeps at least one window', async () => {
    storeState(ids.sharmaSweets).settings.booking_windows = [{ label: 'All day', start: '10:00', end: '19:00' }]
    signIn()
    renderDashboard(`${storePath}/settings`)

    const list = await screen.findByRole('list', { name: 'Time windows' }, lazy)
    expect(within(list).getByRole('button', { name: 'Remove All day' })).toBeDisabled()
  })
})

describe('booking templates', () => {
  it('shows the booking templates step on the setup checklist', async () => {
    signIn()
    renderDashboard(storePath)

    const steps = await screen.findByRole('list', { name: 'Store setup steps' }, lazy)
    expect(within(steps).getByText('Pick booking update templates')).toBeInTheDocument()
    expect(within(steps).getByText('0 of 3 booking updates have a template.')).toBeInTheDocument()
    expect(within(steps).getByRole('link', { name: 'Choose booking templates' })).toHaveAttribute('href', `${storePath}/notifications`)
  })

  it('hides the step when the workspace has no services', async () => {
    storeState(ids.sharmaSweets).activeServices = 0
    signIn()
    renderDashboard(storePath)

    const steps = await screen.findByRole('list', { name: 'Store setup steps' }, lazy)
    expect(within(steps).getAllByRole('listitem')).toHaveLength(6)
    expect(within(steps).queryByText('Pick booking update templates')).not.toBeInTheDocument()
  })

  it('saves booking templates separately from order templates', async () => {
    storeState(ids.sharmaSweets).settings.booking_reminder_template_id = seedTemplates[0].id
    signIn()
    const { user } = renderDashboard(`${storePath}/notifications`)

    expect(await screen.findByRole('heading', { name: 'Booking update templates' }, lazy)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save booking templates' })).toBeDisabled()

    // An unsaved order change is not sent with the booking save.
    await user.click(screen.getByRole('button', { name: 'Clear template for Shipped' }))
    await user.click(screen.getByRole('button', { name: 'Clear template for Booking reminder' }))
    await user.click(screen.getByRole('button', { name: 'Save booking templates' }))

    await waitFor(() => expect(storeState(ids.sharmaSweets).settings.booking_reminder_template_id).toBeNull())
    expect(storeState(ids.sharmaSweets).settings.notification_templates.shipped).toBe(seedTemplates[0].id)
    expect(screen.getByRole('button', { name: 'Save templates' })).toBeEnabled()
  })
})
