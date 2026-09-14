import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ids } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'

describe('orders', () => {
  it('shows Orders in the nav and renders the page', async () => {
    signIn()
    renderDashboard(`/app/w/${ids.sharmaSweets}/orders`)

    expect(await screen.findByRole('heading', { level: 1, name: 'Orders' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'No orders yet' })).toBeInTheDocument()

    const nav = screen.getByRole('navigation', { name: 'Workspace' })
    expect(within(nav).getByRole('link', { name: 'Orders' })).toHaveAttribute('href', `/app/w/${ids.sharmaSweets}/orders`)
  })
})
