import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ids } from '../../../mocks/seed'
import { fill, findDialog, renderDashboard, signIn } from '../../../test/render'
import { catalogMock, collectionId } from './mockState'

const base = `/app/w/${ids.sharmaSweets}/catalog/collections`
const LAZY = { timeout: 10_000 }

describe('collections', () => {
  it('lists collections with product counts', async () => {
    signIn()
    renderDashboard(base)
    const table = await screen.findByRole('table', { name: 'Collections' }, LAZY)
    const laddus = (await within(table).findByText('Laddus')).closest('tr')!
    const count = catalogMock().products.filter((p) => p.collection_id === collectionId(2)).length
    expect(within(laddus).getByText(String(count))).toBeInTheDocument()
    expect(within(laddus).getByRole('switch', { name: 'Active: Laddus' })).toBeChecked()
  })

  it('enforces the WhatsApp list limits on name and description', async () => {
    signIn()
    const { user } = renderDashboard(base)
    await user.click(await screen.findByRole('button', { name: 'New collection' }, LAZY))
    const dialog = await findDialog({ name: 'New collection' })

    await fill(user, within(dialog).getByLabelText(/^Name/), 'Seasonal festival specials')
    await fill(user, within(dialog).getByLabelText(/^Description/), 'x'.repeat(73))
    expect(within(dialog).getByText('26/24')).toBeInTheDocument()
    expect(within(dialog).getByText('73/72')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Create collection' }))

    expect(await within(dialog).findByText('Use at most 24 characters: WhatsApp cuts list row titles there.')).toBeInTheDocument()
    expect(within(dialog).getByLabelText(/^Name/)).toHaveAttribute('aria-invalid', 'true')
    expect(within(dialog).getByLabelText(/^Description/)).toHaveAttribute('aria-invalid', 'true')
    expect(catalogMock().collections).toHaveLength(3)

    await user.clear(within(dialog).getByLabelText(/^Name/))
    await user.type(within(dialog).getByLabelText(/^Name/), 'Festival specials')
    await user.clear(within(dialog).getByLabelText(/^Description/))
    await fill(user, within(dialog).getByLabelText(/^Description/), 'Ghewar, gujiya and Diwali boxes')
    await user.click(within(dialog).getByRole('button', { name: 'Create collection' }))

    await waitFor(() => expect(catalogMock().collections.map((c) => c.name)).toContain('Festival specials'))
    const table = screen.getByRole('table', { name: 'Collections' })
    expect(await within(table).findByText('Festival specials')).toBeInTheDocument()
  })

  it('explains that products become uncollected when a collection is deleted', async () => {
    signIn()
    const { user } = renderDashboard(base)
    await user.click(await screen.findByRole('button', { name: 'Delete Laddus' }, LAZY))
    const dialog = await findDialog({ name: 'Delete Laddus?' })
    expect(within(dialog).getByText(/in your catalog without a collection/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Delete collection' }))

    await waitFor(() => expect(catalogMock().collections.some((c) => c.id === collectionId(2))).toBe(false))
    expect(catalogMock().products.some((p) => p.collection_id === collectionId(2))).toBe(false)
  })
})
