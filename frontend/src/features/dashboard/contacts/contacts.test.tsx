import { File as NodeFile, Blob as NodeBlob } from 'node:buffer'
import { act, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { db } from '../../../mocks/db'
import { ids } from '../../../mocks/seed'
import { fill, findDialog, renderDashboard, signIn } from '../../../test/render'
import { contactId, contactsMock, mockTagIds } from './mockState'

const base = `/app/w/${ids.sharmaSweets}/contacts`
/** The list is newest first, so the highest seed indexes are on the first page. */
const seeded = (i: number) => contactsMock().contacts.find((contact) => contact.id === contactId(i))!
const LAZY = { timeout: 10_000 }

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

async function chooseOption(user: ReturnType<typeof renderDashboard>['user'], combobox: HTMLElement, label: string) {
  await user.click(combobox)
  await user.click(await screen.findByRole('option', { name: label }))
}

function makeViewer() {
  const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.demoUser)
  membership!.role = 'viewer'
}

describe('contacts list', () => {
  it('keeps search and tag filters in the URL', async () => {
    signIn()
    const newest = seeded(59).name // not tagged Wholesale, and not an "Ananya"
    const wholesale = seeded(58).name // 58 % 7 === 2
    const { router, user } = renderDashboard(base)

    expect(await screen.findByRole('link', { name: newest }, LAZY)).toBeInTheDocument()
    await user.type(screen.getByRole('searchbox', { name: 'Search contacts' }), 'Ananya')
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get('q')).toBe('Ananya'))
    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Ananya Khan' })).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: newest })).not.toBeInTheDocument()
    }, LAZY)

    await user.clear(screen.getByRole('searchbox', { name: 'Search contacts' }))
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get('q')).toBeNull())
    await chooseOption(user, screen.getByRole('combobox', { name: 'Filter by tags' }), 'Wholesale')
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).getAll('tag')).toEqual([mockTagIds.wholesale]))
    // Check both together: `wholesale` is also in the unfiltered list, which stays until the tag results render.
    await waitFor(() => {
      expect(screen.getByRole('link', { name: wholesale })).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: newest })).not.toBeInTheDocument()
    })
  })

  it('restores filters from the URL', async () => {
    signIn()
    renderDashboard(`${base}?status=opted_out&tag=${mockTagIds.regular}`)
    const table = await screen.findByRole('table', { name: 'Contacts' }, LAZY)
    await waitFor(() => expect(within(table).getAllByText('Opted out').length).toBeGreaterThan(0))
    expect(within(table).queryByText('Opted in')).not.toBeInTheDocument()
    expect(within(table).queryByText('Unknown')).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Marketing opt-in' })).toHaveValue('opted_out')
  })

  it('shows the duplicate phone error from the server on the phone field', async () => {
    signIn()
    const { user } = renderDashboard(base)
    await user.click(await screen.findByRole('button', { name: 'Add contact' }, LAZY))
    const dialog = await findDialog({ name: 'Add contact' })

    // Aarav Patel's number (+919012345678), typed the way people write Indian mobiles.
    await user.type(within(dialog).getByLabelText(/^WhatsApp phone number/), '90123 45678')
    await user.type(within(dialog).getByLabelText(/^Name/), 'Aarav again')
    await user.click(within(dialog).getByRole('button', { name: 'Add contact' }))

    expect(await within(dialog).findByText('A contact with this phone number already exists.')).toBeInTheDocument()
    expect(within(dialog).getByLabelText(/^WhatsApp phone number/)).toHaveAttribute('aria-invalid', 'true')
    expect(contactsMock().contacts.filter((contact) => contact.phone_e164 === '+919012345678')).toHaveLength(1)
  })

  it('validates the phone number before submitting', async () => {
    signIn()
    const { user } = renderDashboard(base)
    await user.click(await screen.findByRole('button', { name: 'Add contact' }, LAZY))
    const dialog = await findDialog({ name: 'Add contact' })
    await user.type(within(dialog).getByLabelText(/^WhatsApp phone number/), '12345')
    await user.click(within(dialog).getByRole('button', { name: 'Add contact' }))
    expect(await within(dialog).findByText(/Enter a valid number with its country code/)).toBeInTheDocument()
  })

  it('adds a tag to the selected contacts', async () => {
    signIn()
    const first = seeded(59)
    const second = seeded(58)
    const { user } = renderDashboard(base)
    await user.click(await screen.findByRole('checkbox', { name: `Select ${first.name}` }, LAZY))
    await user.click(screen.getByRole('checkbox', { name: `Select ${second.name}` }))

    const bar = screen.getByRole('region', { name: 'Bulk actions' })
    expect(within(bar).getByText('2 selected')).toBeInTheDocument()
    await user.click(within(bar).getByRole('button', { name: 'Add tags' }))

    const dialog = await findDialog({ name: 'Add tags' })
    await chooseOption(user, within(dialog).getByRole('combobox', { name: /^Tags/ }), 'VIP')
    await user.click(within(dialog).getByRole('button', { name: 'Add tags' }))

    expect(await screen.findByText('Tags added')).toBeInTheDocument()
    expect(seeded(59).tags).toContain(mockTagIds.vip)
    expect(seeded(58).tags).toContain(mockTagIds.vip)
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Bulk actions' })).not.toBeInTheDocument())
  })
})

describe('contact detail', () => {
  it('shows the consent history and records a manual opt-out', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/${contactId(1)}`)

    expect(await screen.findByRole('heading', { level: 1, name: 'Ananya Khan' }, LAZY)).toBeInTheDocument()
    const history = await screen.findByRole('list', { name: 'Consent history' })
    expect(within(history).getByText('Opted in')).toBeInTheDocument()
    expect(await within(history).findByText(/CSV import · by Rohan Sharma/)).toBeInTheDocument()
    expect(within(history).getByText(/Checkout form on sharmasweets\.in/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Record opt-out' }))
    const dialog = await findDialog({ name: 'Record marketing opt-out' })
    await fill(user, within(dialog).getByLabelText(/^Note/), 'Asked on a call to stop offers')
    await user.click(within(dialog).getByRole('button', { name: 'Record opt-out' }))

    await waitFor(() => expect(within(screen.getByRole('list', { name: 'Consent history' })).getByText('Opted out')).toBeInTheDocument())
    const updated = screen.getByRole('list', { name: 'Consent history' })
    expect(within(updated).getByText(/Recorded manually · by Rohan Sharma/)).toBeInTheDocument()
    expect(within(updated).getByText('Asked on a call to stop offers')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Record opt-in' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Record opt-out' })).not.toBeInTheDocument()
    expect(seeded(1).marketing_opt_in_status).toBe('opted_out')
  })

  it('requires evidence for a manual opt-in', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/${contactId(0)}`)
    await user.click(await screen.findByRole('button', { name: 'Record opt-in' }, LAZY))
    const dialog = await findDialog({ name: 'Record marketing opt-in' })
    await user.click(within(dialog).getByRole('button', { name: 'Record opt-in' }))
    expect(await within(dialog).findByText('Describe how the customer opted in.')).toBeInTheDocument()
  })
})

describe('CSV import', () => {
  it('shows an example file that can be downloaded', async () => {
    signIn()
    // jsdom has no object URLs; define them so they can be spied on (restoreMocks undoes the spies).
    URL.createObjectURL ??= () => ''
    URL.revokeObjectURL ??= () => {}
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:sample')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const { user } = renderDashboard(`${base}/imports/new`)

    const sample = await screen.findByRole('table', { name: /Example CSV/ }, LAZY)
    expect(within(sample).getByRole('columnheader', { name: /phone\s*Phone number/ })).toBeInTheDocument()
    expect(within(sample).getByRole('columnheader', { name: /city\s*Attribute/ })).toBeInTheDocument()
    expect(within(sample).getByRole('row', { name: /Priya Sharma/ })).toBeInTheDocument()
    expect(within(sample).getByRole('cell', { name: 'Rasgulla, 1 kg' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Download sample CSV' }))
    expect(click).toHaveBeenCalledTimes(1)
    const link = click.mock.instances[0] as unknown as HTMLAnchorElement
    expect(link.download).toBe('upchatz-contacts-sample.csv')
    const text = await (createObjectURL.mock.calls[0][0] as Blob).text()
    expect(text.split('\r\n')[0]).toBe('phone,name,email,city,last_order')
  })

  it('blocks without the consent attestation, then polls until the import completes', async () => {
    // jsdom's FormData/File aren't understood by Node's fetch, which MSW uses to read multipart bodies.
    const NodeFormData = (
      await new Response('a=1', { headers: { 'content-type': 'application/x-www-form-urlencoded' } }).formData()
    ).constructor as typeof FormData
    vi.stubGlobal('FormData', NodeFormData)
    vi.stubGlobal('File', NodeFile)
    vi.stubGlobal('Blob', NodeBlob)
    vi.useFakeTimers({ shouldAdvanceTime: true })

    signIn()
    const { router, user } = renderDashboard(`${base}/imports/new`)
    const csv = ['phone,name,city', '9876500001,Test One,Pune', '98765 00002,Test Two,Delhi', '+919012345678,Aarav Patel,Mumbai', 'not-a-number,Nobody,Delhi'].join('\n')
    const file = new NodeFile([csv], 'diwali-customers.csv', { type: 'text/csv' }) as unknown as File

    await user.upload(await screen.findByLabelText(/Drop a CSV here or browse/, undefined, LAZY), file)
    const mapping = await screen.findByRole('table', { name: 'Column mapping' })
    expect(within(mapping).getByRole('row', { name: /phone\s+Phone number\s+9876500001/ })).toBeInTheDocument()
    expect(within(mapping).getByRole('row', { name: /city\s+Attribute\s*city\s+Pune/ })).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: /Example CSV/ })).not.toBeInTheDocument()

    const before = contactsMock().imports.length
    await user.click(screen.getByRole('button', { name: 'Start import' }))
    expect(await screen.findByText('Confirm that these contacts agreed to receive WhatsApp messages from your business.')).toBeInTheDocument()
    expect(contactsMock().imports).toHaveLength(before)

    await user.click(screen.getByRole('checkbox', { name: /I confirm every contact in this file agreed/ }))
    await user.click(screen.getByRole('button', { name: 'Start import' }))

    await waitFor(() => expect(router.state.location.pathname).toMatch(/\/contacts\/imports\/[0-9a-f-]{36}$/))
    expect(await screen.findByRole('heading', { level: 1, name: 'diwali-customers.csv' }, LAZY)).toBeInTheDocument()

    for (let poll = 0; poll < 5 && !screen.queryByText(/Import complete/); poll += 1) {
      await act(() => vi.advanceTimersByTimeAsync(1600))
    }
    expect(await screen.findByText(/Import complete/)).toBeInTheDocument()

    const summary = screen.getByRole('region', { name: 'Result summary' })
    const stat = (label: string) => within(summary).getByText(label).nextElementSibling?.textContent
    expect(stat('Created')).toBe('2')
    expect(stat('Updated')).toBe('1')
    expect(stat('Errors')).toBe('1')
    expect(screen.getByRole('button', { name: 'Download CSV' })).toBeInTheDocument()
    expect(contactsMock().contacts.some((contact) => contact.phone_e164 === '+919876500002')).toBe(true)
  })
})

describe('viewer role', () => {
  it('hides write actions from viewers', async () => {
    makeViewer()
    signIn()
    const newest = seeded(59).name
    const { unmount } = renderDashboard(base)

    expect(await screen.findByRole('link', { name: newest }, LAZY)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add contact' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Import CSV|Imports/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    unmount()

    renderDashboard(`${base}/${contactId(1)}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Ananya Khan' }, LAZY)).toBeInTheDocument()
    expect(await screen.findByRole('list', { name: 'Consent history' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Record opt-/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start conversation' })).not.toBeInTheDocument()
  })

  it('shows tags read-only to viewers', async () => {
    makeViewer()
    signIn()
    renderDashboard(`${base}/tags`)
    const table = await screen.findByRole('table', { name: 'Tags' }, LAZY)
    expect(await within(table).findByText('Wholesale')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New tag' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Delete / })).not.toBeInTheDocument()
  })
})
