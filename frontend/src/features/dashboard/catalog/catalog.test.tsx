import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ids } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'

describe('catalog', () => {
  it('shows Catalog in the nav and renders the page', async () => {
    signIn()
    renderDashboard(`/app/w/${ids.sharmaSweets}/catalog`)

    expect(await screen.findByRole('heading', { level: 1, name: 'Catalog' })).toBeInTheDocument()
    expect(screen.getByText(/Products you sell on WhatsApp/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'No products yet' })).toBeInTheDocument()

    const nav = screen.getByRole('navigation', { name: 'Workspace' })
    expect(within(nav).getByRole('link', { name: 'Catalog' })).toHaveAttribute('href', `/app/w/${ids.sharmaSweets}/catalog`)
  })
})
