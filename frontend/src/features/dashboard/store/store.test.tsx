import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Role } from '../../../lib/roles'
import { db } from '../../../mocks/db'
import { ids } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'

const storePath = `/app/w/${ids.sharmaSweets}/store`

function setRole(role: Role) {
  const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.demoUser)
  if (!membership) throw new Error('seed membership missing')
  membership.role = role
}

describe('store', () => {
  it('shows Store in the nav and renders the page for admins', async () => {
    setRole('admin')
    signIn()
    renderDashboard(storePath)

    expect(await screen.findByRole('heading', { level: 1, name: 'Store' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: "Your store isn't set up yet" })).toBeInTheDocument()

    const nav = screen.getByRole('navigation', { name: 'Workspace' })
    expect(within(nav).getByRole('link', { name: 'Store' })).toHaveAttribute('href', storePath)
  })

  it('hides Store from agents and blocks the route', async () => {
    setRole('agent')
    signIn()
    renderDashboard(storePath)

    expect(await screen.findByRole('heading', { name: "You don't have access to this page" })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Workspace' })
    expect(within(nav).queryByRole('link', { name: 'Store' })).not.toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: 'Orders' })).toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: 'Catalog' })).toBeInTheDocument()
  })
})
