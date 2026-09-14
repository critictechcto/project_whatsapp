import { act, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { db } from '../../../mocks/db'
import { ids } from '../../../mocks/seed'
import { dispatch } from '../../../lib/realtime/registry'
import { renderDashboard, signIn } from '../../../test/render'
import { catalogMock, metaCatalogId } from './mockState'

const base = `/app/w/${ids.sharmaSweets}/catalog/whatsapp`
const LAZY = { timeout: 10_000 }

describe('native WhatsApp catalog', () => {
  it('shows the connected catalog and saves commerce toggles per number', async () => {
    signIn()
    const { user } = renderDashboard(base)
    expect(await screen.findByRole('heading', { name: 'Sharma Sweets products' }, LAZY)).toBeInTheDocument()
    expect(screen.getByText(/Commerce Policy/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sync now' })).toBeInTheDocument()

    const settings = catalogMock().metaCatalogs[0].phone_numbers[0]
    const section = screen.getByRole('region', { name: `Settings for ${settings.display_phone_number}` })
    const cart = within(section).getByRole('switch', { name: /Shopping cart/ })
    expect(cart).toBeChecked()
    await user.click(cart)
    await waitFor(() => expect(catalogMock().metaCatalogs[0].phone_numbers[0].is_cart_enabled).toBe(false))
    await waitFor(() => expect(within(section).getByRole('switch', { name: /Shopping cart/ })).not.toBeChecked())

    await user.click(within(section).getByRole('switch', { name: /Catalog visible/ }))
    await waitFor(() => expect(catalogMock().metaCatalogs[0].phone_numbers[0].is_catalog_visible).toBe(false))
  })

  it('connects an existing catalog from the Meta business', async () => {
    catalogMock().metaCatalogs = []
    signIn()
    const { user } = renderDashboard(base)
    await user.click(await screen.findByRole('button', { name: 'Connect a Meta catalog' }, LAZY))
    const dialog = await screen.findByRole('dialog', { name: 'Connect a Meta catalog' })

    expect(await within(dialog).findByRole('combobox', { name: 'WhatsApp Business Account' })).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Connect catalog' }))
    expect(await within(dialog).findByText('Choose a catalog.')).toBeInTheDocument()

    await user.click(await within(dialog).findByRole('radio', { name: /Sharma Sweets wholesale/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Connect catalog' }))

    expect(await screen.findByRole('heading', { name: 'Sharma Sweets wholesale' })).toBeInTheDocument()
    expect(catalogMock().metaCatalogs).toHaveLength(1)
    expect(catalogMock().metaCatalogs[0].catalog_id).toBe('912837465019284')
  })

  it('creates a new catalog by name', async () => {
    catalogMock().metaCatalogs = []
    signIn()
    const { user } = renderDashboard(base)
    await user.click(await screen.findByRole('button', { name: 'Connect a Meta catalog' }, LAZY))
    const dialog = await screen.findByRole('dialog', { name: 'Connect a Meta catalog' })
    await user.click(await within(dialog).findByRole('radio', { name: 'Create a new catalog' }))
    await user.type(within(dialog).getByLabelText(/^New catalog name/), 'Sharma Sweets Diwali')
    await user.click(within(dialog).getByRole('button', { name: 'Create and connect' }))

    expect(await screen.findByRole('heading', { name: 'Sharma Sweets Diwali' })).toBeInTheDocument()
    expect(catalogMock().metaCatalogs[0].catalog_name).toBe('Sharma Sweets Diwali')
  })

  it('explains missing catalog permissions and links to WhatsApp', async () => {
    catalogMock().metaCatalogs = []
    catalogMock().permissionsMissing = true
    signIn()
    const { user } = renderDashboard(base)
    await user.click(await screen.findByRole('button', { name: 'Connect a Meta catalog' }, LAZY))
    const dialog = await screen.findByRole('dialog', { name: 'Connect a Meta catalog' })

    const notice = await within(dialog).findByRole('alert', undefined, LAZY)
    expect(notice).toHaveTextContent('Reconnect WhatsApp to allow catalog access')
    expect(within(notice).getByRole('link', { name: 'Go to WhatsApp' })).toHaveAttribute('href', `/app/w/${ids.sharmaSweets}/whatsapp`)
  })

  it('refetches when a catalog.sync frame arrives', async () => {
    signIn()
    renderDashboard(base)
    expect(await screen.findByRole('heading', { name: 'Sharma Sweets products' }, LAZY)).toBeInTheDocument()

    catalogMock().metaCatalogs[0].last_sync_error = 'Meta could not fetch 1 product image.'
    act(() => {
      dispatch({ v: 1, type: 'catalog.sync', workspace_id: ids.sharmaSweets, data: { meta_catalog_id: metaCatalogId, status: 'failed' } })
    })
    expect(await screen.findByText('Meta could not fetch 1 product image.')).toBeInTheDocument()
  })

  it('keeps settings read-only for viewers', async () => {
    const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.demoUser)
    membership!.role = 'viewer'
    signIn()
    renderDashboard(base)
    expect(await screen.findByRole('heading', { name: 'Sharma Sweets products' }, LAZY)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sync now' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Disconnect' })).not.toBeInTheDocument()
    for (const toggle of screen.getAllByRole('switch')) expect(toggle).toBeDisabled()
  })
})
