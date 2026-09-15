import { File as NodeFile, Blob as NodeBlob } from 'node:buffer'
import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { db } from '../../../mocks/db'
import { ids } from '../../../mocks/seed'
import { findDialog, renderDashboard, signIn } from '../../../test/render'
import { catalogMock, collectionId } from './mockState'

const base = `/app/w/${ids.sharmaSweets}/catalog`
const LAZY = { timeout: 10_000 }
const search = (router: ReturnType<typeof renderDashboard>['router']) => new URLSearchParams(router.state.location.search)

afterEach(() => {
  vi.unstubAllGlobals()
})

function makeViewer() {
  const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.demoUser)
  membership!.role = 'viewer'
}

describe('products list', () => {
  it('shows Catalog in the nav and lists seeded products with prices, stock and review status', async () => {
    signIn()
    renderDashboard(base)

    expect(await screen.findByRole('heading', { level: 1, name: 'Catalog' }, LAZY)).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Workspace' })
    expect(within(nav).getByRole('link', { name: 'Catalog' })).toHaveAttribute('href', base)

    const table = await screen.findByRole('table', { name: 'Products' })
    const kaju = (await within(table).findByRole('link', { name: 'Kaju katli 500 g' })).closest('tr')!
    expect(within(kaju).getByText('₹599')).toBeInTheDocument()
    expect(within(kaju).getByText('₹650').closest('s')).not.toBeNull()
    expect(within(kaju).getByRole('switch', { name: 'Active: Kaju katli 500 g' })).toBeChecked()

    const untracked = within(table).getByRole('link', { name: /Kaju katli 1/ }).closest('tr')!
    expect(within(untracked).getByText('Not tracked')).toBeInTheDocument()
    const pista = within(table).getByRole('link', { name: 'Pista roll 250 g' }).closest('tr')!
    expect(within(pista).getByText('Out of stock')).toBeInTheDocument()
    const anjeer = within(table).getByRole('link', { name: 'Sugar-free anjeer barfi 400 g' }).closest('tr')!
    expect(within(anjeer).getByText('Rejected')).toBeInTheDocument()
    expect(within(anjeer).getByText(/Health claims/)).toBeInTheDocument()
  })

  it('keeps search and filters in the URL', async () => {
    signIn()
    const { router, user } = renderDashboard(base)
    const table = await screen.findByRole('table', { name: 'Products' }, LAZY)
    expect(await within(table).findByRole('link', { name: 'Kaju katli 500 g' })).toBeInTheDocument()

    await user.type(screen.getByRole('searchbox', { name: 'Search products' }), 'pista')
    await waitFor(() => expect(search(router).get('q')).toBe('pista'))
    expect(await within(table).findByRole('link', { name: 'Pista roll 250 g' })).toBeInTheDocument()
    await waitFor(() => expect(within(table).queryByRole('link', { name: 'Kaju katli 500 g' })).not.toBeInTheDocument())

    await user.clear(screen.getByRole('searchbox', { name: 'Search products' }))
    await waitFor(() => expect(search(router).get('q')).toBeNull())
    expect(await within(table).findByRole('link', { name: 'Kaju katli 500 g' })).toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Collection' }), 'Laddus')
    await waitFor(() => expect(search(router).get('collection')).toBe(collectionId(2)))
    expect(await within(table).findByRole('link', { name: /Motichoor/ })).toBeInTheDocument()
    await waitFor(() => expect(within(table).queryByRole('link', { name: 'Kaju katli 500 g' })).not.toBeInTheDocument())

    await user.selectOptions(screen.getByRole('combobox', { name: 'Collection' }), 'No collection')
    await waitFor(() => expect(search(router).get('collection')).toBe('none'))
    expect(await within(table).findByRole('link', { name: 'Malai ghewar (4 pcs)' })).toBeInTheDocument()
    await waitFor(() => expect(within(table).queryByRole('link', { name: /Motichoor/ })).not.toBeInTheDocument())

    await user.selectOptions(screen.getByRole('combobox', { name: 'Active' }), 'Active only')
    await waitFor(() => expect(search(router).get('active')).toBe('true'))
    expect(await screen.findByRole('heading', { name: 'No products match these filters' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(router.state.location.search).toBe(''))
    // The empty state replaced the table, so query it again.
    const refreshed = await screen.findByRole('table', { name: 'Products' })
    expect(await within(refreshed).findByRole('link', { name: 'Kaju katli 500 g' })).toBeInTheDocument()
  })

  it('restores filters from the URL', async () => {
    signIn()
    renderDashboard(`${base}?availability=out_of_stock&review=approved`)
    const table = await screen.findByRole('table', { name: 'Products' }, LAZY)
    expect(await within(table).findByRole('link', { name: 'Pista roll 250 g' })).toBeInTheDocument()
    expect(within(table).queryByRole('link', { name: 'Kaju katli 500 g' })).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Availability' })).toHaveValue('out_of_stock')
    expect(screen.getByRole('combobox', { name: 'Meta review' })).toHaveValue('approved')
  })

  it('hides the Meta review column and filter without a connected catalog', async () => {
    catalogMock().metaCatalogs = []
    signIn()
    renderDashboard(`${base}?review=rejected`)
    const table = await screen.findByRole('table', { name: 'Products' }, LAZY)
    expect(await within(table).findByRole('link', { name: 'Kaju katli 500 g' })).toBeInTheDocument()
    expect(within(table).queryByRole('columnheader', { name: 'Meta review' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Meta review' })).not.toBeInTheDocument()
  })

  it('shows the empty state with import and add actions', async () => {
    catalogMock().products = []
    signIn()
    renderDashboard(base)
    const empty = await screen.findByRole('heading', { name: 'No products yet' }, LAZY)
    const container = empty.parentElement!.parentElement!
    expect(within(container).getByRole('button', { name: 'Import CSV' })).toBeInTheDocument()
    expect(within(container).getByRole('link', { name: 'Add product' })).toHaveAttribute('href', `${base}/products/new`)
  })

  it('toggles a product active', async () => {
    signIn()
    const { user } = renderDashboard(base)
    const toggle = await screen.findByRole('switch', { name: 'Active: Kaju katli 500 g' }, LAZY)
    await user.click(toggle)
    await waitFor(() => expect(catalogMock().products.find((p) => p.sku === 'KAJU-KATLI-500')!.is_active).toBe(false))
  })

  it('reorders products with the move buttons', async () => {
    signIn()
    const { user } = renderDashboard(base)
    await user.click(await screen.findByRole('button', { name: 'Reorder' }, LAZY))
    const dialog = await findDialog({ name: 'Reorder products' })
    expect(within(dialog).getByRole('button', { name: 'Save order' })).toBeDisabled()
    await user.click(await within(dialog).findByRole('button', { name: 'Move Kaju katli 500 g down' }))
    await user.click(within(dialog).getByRole('button', { name: 'Save order' }))
    await waitFor(() => {
      const ordered = [...catalogMock().products].sort((a, b) => a.position - b.position)
      expect(ordered[1].sku).toBe('KAJU-KATLI-500')
    })
  })
})

describe('CSV import', () => {
  it('shows created, updated and skipped counts with row errors', async () => {
    // jsdom's FormData/File aren't understood by Node's fetch, which MSW uses to read multipart bodies.
    const NodeFormData = (
      await new Response('a=1', { headers: { 'content-type': 'application/x-www-form-urlencoded' } }).formData()
    ).constructor as typeof FormData
    vi.stubGlobal('FormData', NodeFormData)
    vi.stubGlobal('File', NodeFile)
    vi.stubGlobal('Blob', NodeBlob)

    signIn()
    const { user } = renderDashboard(base)
    await user.click(await screen.findByRole('button', { name: 'Import CSV' }, LAZY))
    const dialog = await findDialog({ name: 'Import products from CSV' })
    expect(within(dialog).getByRole('table', { name: 'CSV columns' })).toBeInTheDocument()
    expect(within(dialog).getByRole('link', { name: 'Download sample CSV' })).toHaveAttribute('href', expect.stringMatching(/^data:text\/csv/))

    const csv = [
      'sku,name,price,collection',
      'RASGULLA-1KG,Rasgulla 1 kg,380,Bengali sweets',
      'KAJU-KATLI-500,Kaju katli 500 g (new box),660,',
      'SOAN-PAPDI,Soan papdi,abc,',
    ].join('\n')
    const file = new NodeFile([csv], 'products.csv', { type: 'text/csv' }) as unknown as File
    await user.upload(within(dialog).getByLabelText(/Drop a CSV here or browse/), file)
    await user.click(within(dialog).getByRole('button', { name: 'Import products' }))

    const result = await within(dialog).findByRole('region', { name: 'Import result' })
    expect(within(result).getByText('Created').nextElementSibling).toHaveTextContent('1')
    expect(within(result).getByText('Updated').nextElementSibling).toHaveTextContent('1')
    expect(within(result).getByText('Skipped').nextElementSibling).toHaveTextContent('1')
    const errors = within(dialog).getByRole('table', { name: 'Rows not imported' })
    expect(within(errors).getByRole('row', { name: /4\s+SOAN-PAPDI\s+"abc" is not a price in rupees\./ })).toBeInTheDocument()

    const created = catalogMock().products.find((p) => p.sku === 'RASGULLA-1KG')!
    expect(created.price_paise).toBe(38000)
    expect(catalogMock().collections.find((c) => c.id === created.collection_id)?.name).toBe('Bengali sweets')
    expect(catalogMock().products.find((p) => p.sku === 'KAJU-KATLI-500')!.price_paise).toBe(66000)
  })
})

describe('viewer role', () => {
  it('hides write actions on products and collections', async () => {
    makeViewer()
    signIn()
    const { unmount } = renderDashboard(base)
    const table = await screen.findByRole('table', { name: 'Products' }, LAZY)
    expect(await within(table).findByRole('link', { name: 'Kaju katli 500 g' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Import CSV' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reorder' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Add product' })).not.toBeInTheDocument()
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    unmount()

    renderDashboard(`${base}/collections`)
    const collections = await screen.findByRole('table', { name: 'Collections' }, LAZY)
    expect(await within(collections).findByText('Laddus')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New collection' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Delete / })).not.toBeInTheDocument()
  })

  it('shows the product editor read-only', async () => {
    makeViewer()
    signIn()
    renderDashboard(`${base}/products/${catalogMock().products[0].id}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Kaju katli 500 g' }, LAZY)).toBeInTheDocument()
    expect(screen.getByText(/Only admins and owners can change them/)).toBeInTheDocument()
    expect(screen.getByLabelText(/^Name/)).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Save product' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Drop a photo|Replace photo/)).not.toBeInTheDocument()
  })
})
