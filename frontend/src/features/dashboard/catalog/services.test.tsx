import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ids } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'
import { catalogMock } from './mockState'

const base = `/app/w/${ids.sharmaSweets}/catalog`
const LAZY = { timeout: 10_000 }

describe('services in the catalog', () => {
  it('switches the editor to a service: no stock fields, a duration and a Book button', async () => {
    signIn()
    const { user, router } = renderDashboard(`${base}/products/new`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Add product' }, LAZY)).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Track stock/ })).toBeInTheDocument()
    expect(screen.queryByLabelText(/^Duration/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: 'Service' }))
    expect(screen.getByRole('radio', { name: 'Service' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.queryByRole('checkbox', { name: /Track stock/ })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/^Stock quantity/)).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Price and length' })).toBeInTheDocument()

    const preview = screen.getByText('Interactive message preview').closest('figure')!
    const buttons = within(preview).getByRole('list', { name: 'Reply buttons' })
    expect(within(buttons).getByText('Book')).toBeInTheDocument()
    expect(within(buttons).queryByText('Add to cart')).not.toBeInTheDocument()
    expect(within(buttons).queryByText('Change qty')).not.toBeInTheDocument()

    await user.type(screen.getByLabelText(/^SKU/), 'HAIR-SPA-45')
    await user.type(screen.getByLabelText(/^Name/), 'Hair spa')
    await user.type(screen.getByLabelText(/^Price \(/), '899')
    const duration = screen.getByLabelText(/^Duration/)
    await user.clear(duration)
    await user.type(duration, '3')
    await user.click(screen.getByRole('button', { name: 'Add product' }))
    expect(await screen.findByText('Enter the length in minutes, from 5 to 600.')).toBeInTheDocument()

    await user.clear(duration)
    await user.type(duration, '45')
    expect(within(preview).getByText(/45 min/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add product' }))

    await waitFor(() => expect(catalogMock().products.some((p) => p.sku === 'HAIR-SPA-45')).toBe(true))
    const created = catalogMock().products.find((p) => p.sku === 'HAIR-SPA-45')!
    expect(created.kind).toBe('service')
    expect(created.duration_minutes).toBe(45)
    expect(created.stock_qty).toBeNull()
    await waitFor(() => expect(router.state.location.pathname).toBe(`${base}/products/${created.id}`))
    expect(await screen.findByText('Service added')).toBeInTheDocument()
  })

  it('opens a seeded service with its duration and without stock fields', async () => {
    const service = catalogMock().products.find((p) => p.sku === 'DIWALI-GLOW-60')!
    signIn()
    renderDashboard(`${base}/products/${service.id}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Diwali Glow facial' }, LAZY)).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Service' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByLabelText(/^Duration/)).toHaveValue('60')
    expect(screen.queryByRole('checkbox', { name: /Track stock/ })).not.toBeInTheDocument()
  })

  it('marks services in the list and filters by type', async () => {
    signIn()
    const { user, router } = renderDashboard(base)
    const table = await screen.findByRole('table', { name: 'Products' }, LAZY)
    const row = (await within(table).findByRole('link', { name: 'Diwali Glow facial' })).closest('tr')!
    expect(within(row).getByText(/Service/)).toBeInTheDocument()
    expect(within(row).getByText('Not stocked')).toBeInTheDocument()

    await user.selectOptions(screen.getByRole('combobox', { name: 'Type' }), 'service')
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get('kind')).toBe('service'))
    await waitFor(() => {
      expect(within(table).getByRole('link', { name: 'Diwali Glow facial' })).toBeInTheDocument()
      expect(within(table).queryByRole('link', { name: 'Kaju katli 500 g' })).not.toBeInTheDocument()
    })
  })
})
