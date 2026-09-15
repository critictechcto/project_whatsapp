import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ids } from '../../../mocks/seed'
import { findDialog, renderDashboard, signIn } from '../../../test/render'
import { catalogMock, productId } from './mockState'

const base = `/app/w/${ids.sharmaSweets}/catalog`
const LAZY = { timeout: 10_000 }
const originalCreateObjectURL = URL.createObjectURL
const originalRevokeObjectURL = URL.revokeObjectURL

afterEach(() => {
  vi.unstubAllGlobals()
  URL.createObjectURL = originalCreateObjectURL
  URL.revokeObjectURL = originalRevokeObjectURL
})

describe('product editor', () => {
  it('validates, converts rupees to paise and opens the new product', async () => {
    signIn()
    const { router, user } = renderDashboard(`${base}/products/new`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Add product' }, LAZY)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add product' }))
    expect(await screen.findByText('Enter a SKU.')).toBeInTheDocument()
    expect(screen.getByText('Enter a product name.')).toBeInTheDocument()
    expect(screen.getByText('Enter a price.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^SKU/)).toHaveAttribute('aria-invalid', 'true')

    await user.type(screen.getByLabelText(/^SKU/), 'RASGULLA 1KG')
    await user.type(screen.getByLabelText(/^Name/), 'Rasgulla 1 kg')
    await user.type(screen.getByLabelText(/^Price \(/), '249.50')
    await user.type(screen.getByLabelText(/^Sale price/), '300')
    await user.click(screen.getByRole('button', { name: 'Add product' }))
    expect(await screen.findByText('Use letters, numbers, hyphens and underscores only (up to 100).')).toBeInTheDocument()
    expect(screen.getByText('The sale price must be lower than the price.')).toBeInTheDocument()

    await user.clear(screen.getByLabelText(/^SKU/))
    await user.type(screen.getByLabelText(/^SKU/), 'RASGULLA-1KG')
    await user.clear(screen.getByLabelText(/^Sale price/))
    await user.type(screen.getByLabelText(/^Sale price/), '199')
    await user.selectOptions(screen.getByLabelText(/^Collection/), 'Dry fruit sweets')
    await user.click(screen.getByRole('button', { name: 'Add product' }))

    await waitFor(() => expect(catalogMock().products.some((p) => p.sku === 'RASGULLA-1KG')).toBe(true))
    const created = catalogMock().products.find((p) => p.sku === 'RASGULLA-1KG')!
    expect(created.price_paise).toBe(24950)
    expect(created.sale_price_paise).toBe(19900)
    await waitFor(() => expect(router.state.location.pathname).toBe(`${base}/products/${created.id}`))
    expect(await screen.findByRole('heading', { level: 1, name: 'Rasgulla 1 kg' })).toBeInTheDocument()
    // The SKU is fixed once the product exists.
    expect(screen.getByLabelText(/^SKU/)).toHaveAttribute('readonly')
  })

  it('shows a duplicate SKU from the server on the SKU field', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/products/new`)
    await user.type(await screen.findByLabelText(/^SKU/, undefined, LAZY), 'KAJU-KATLI-500')
    await user.type(screen.getByLabelText(/^Name/), 'Another kaju katli')
    await user.type(screen.getByLabelText(/^Price \(/), '100')
    await user.click(screen.getByRole('button', { name: 'Add product' }))

    expect(await screen.findByText('A product with this SKU already exists.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^SKU/)).toHaveAttribute('aria-invalid', 'true')
    expect(catalogMock().products.filter((p) => p.sku === 'KAJU-KATLI-500')).toHaveLength(1)
  })

  it('updates the WhatsApp product card preview as you type', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/products/new`)
    const preview = (await screen.findByText('Interactive message preview', undefined, LAZY)).closest('figure')!
    expect(within(preview).getByText('Product name')).toBeInTheDocument()
    const buttons = within(preview).getByRole('list', { name: 'Reply buttons' })
    expect(within(buttons).getByText('Add to cart')).toBeInTheDocument()
    expect(within(buttons).getByText('Change qty')).toBeInTheDocument()
    expect(within(buttons).getByText('Back')).toBeInTheDocument()

    await user.type(screen.getByLabelText(/^Name/), 'Kesar peda')
    await user.type(screen.getByLabelText(/^Price \(/), '480')
    await user.type(screen.getByLabelText(/^Sale price/), '450')
    await user.type(screen.getByLabelText(/^Description/), 'Saffron peda, 500 g')

    expect(within(preview).getByText('Kesar peda')).toBeInTheDocument()
    expect(within(preview).getByText('₹450')).toBeInTheDocument()
    expect(within(preview).getByText('₹480')).toBeInTheDocument()
    expect(within(preview).getByText(/Saffron peda, 500 g/)).toBeInTheDocument()
    expect(within(preview).queryByText('Product name')).not.toBeInTheDocument()
  })

  it('rejects a photo smaller than 500×500 before uploading', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:mock-photo')
    URL.revokeObjectURL = vi.fn()
    class SmallImage {
      naturalWidth = 320
      naturalHeight = 240
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      set src(_value: string) {
        queueMicrotask(() => this.onload?.())
      }
    }
    vi.stubGlobal('Image', SmallImage)

    signIn()
    const { user } = renderDashboard(`${base}/products/${productId(11)}`)
    const dropzone = await screen.findByLabelText(/Drop a photo here or browse/, undefined, LAZY)
    await user.upload(dropzone, new File(['png'], 'hamper.png', { type: 'image/png' }))

    expect(await screen.findByText('The image is 320×240 px. Use one at least 500×500 px.')).toBeInTheDocument()
    expect(catalogMock().products.find((p) => p.id === productId(11))!.image_url).toBeFalsy()
  })

  it('deletes a product after confirming that past orders keep their snapshot', async () => {
    signIn()
    const { router, user } = renderDashboard(`${base}/products/${productId(8)}`)
    const heading = await screen.findByRole('heading', { level: 1 }, LAZY)
    const name = heading.textContent!
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    const dialog = await findDialog({ name: `Delete ${name}?` })
    expect(within(dialog).getByText(/Past orders keep their item names and prices/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Delete product' }))
    await waitFor(() => expect(router.state.location.pathname).toBe(base))
    expect(catalogMock().products.some((p) => p.id === productId(8))).toBe(false)
  })
})
