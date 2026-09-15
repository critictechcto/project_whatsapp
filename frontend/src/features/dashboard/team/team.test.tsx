import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { db } from '../../../mocks/db'
import { server } from '../../../mocks/node'
import { ids } from '../../../mocks/seed'
import { errorResponse, http } from '../../../mocks/utils'
import { findDialog, renderDashboard, signIn } from '../../../test/render'

const teamPath = `/app/w/${ids.sharmaSweets}/team`

describe('team', () => {
  it('lists members with their roles', async () => {
    signIn()
    renderDashboard(teamPath)
    expect(await screen.findByRole('heading', { level: 1, name: 'Team' })).toBeInTheDocument()
    expect(await screen.findByText('Priya Nair')).toBeInTheDocument()
    expect(screen.getByText('Arjun Mehta')).toBeInTheDocument()
    expect(screen.getByLabelText('Owner role is locked')).toBeInTheDocument()
  })

  it('invites a teammate and shows the pending invitation', async () => {
    signIn()
    const { user } = renderDashboard(teamPath)
    await user.click(await screen.findByRole('button', { name: 'Invite teammate' }))

    const dialog = await findDialog({ name: 'Invite a teammate' })
    await user.type(within(dialog).getByLabelText(/^Email/), 'neha.gupta@sharmasweets.in')
    await user.selectOptions(within(dialog).getByLabelText(/^Role/), 'agent')
    await user.click(within(dialog).getByRole('button', { name: 'Send invitation' }))

    expect(await screen.findByText(/Invitation sent to neha\.gupta@sharmasweets\.in/)).toBeInTheDocument()
    expect(await screen.findByRole('tab', { name: /Invitations/, selected: true })).toBeInTheDocument()
    expect((await screen.findAllByText('neha.gupta@sharmasweets.in')).length).toBeGreaterThan(0)
  })

  it('rejects an invite for an existing member on the email field', async () => {
    signIn()
    const { user } = renderDashboard(teamPath)
    await user.click(await screen.findByRole('button', { name: 'Invite teammate' }))
    const dialog = await findDialog({ name: 'Invite a teammate' })
    await user.type(within(dialog).getByLabelText(/^Email/), 'priya.nair@sharmasweets.in')
    await user.click(within(dialog).getByRole('button', { name: 'Send invitation' }))

    expect(await within(dialog).findByText('This person is already a member of the workspace.')).toBeInTheDocument()
    expect(within(dialog).getByLabelText(/^Email/)).toHaveAttribute('aria-invalid', 'true')
  })

  it('hides management actions from viewers', async () => {
    const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.demoUser)
    if (!membership) throw new Error('seed membership missing')
    membership.role = 'viewer'
    signIn()
    const { user } = renderDashboard(teamPath)

    expect(await screen.findByText('Priya Nair')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Invite teammate' })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: /Invitations/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Actions for Priya Nair' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Actions for Arjun Mehta' })).not.toBeInTheDocument()

    // A viewer can still leave the workspace, and that's the only action offered.
    await user.click(screen.getByRole('button', { name: 'Actions for Rohan Sharma' }))
    expect(await screen.findByRole('menuitem', { name: 'Leave workspace' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Change role' })).not.toBeInTheDocument()
  })

  it('shows the reason when the API refuses a role change', async () => {
    server.use(
      http.patch('/api/v1/workspaces/members/{id}/', ({ response }) =>
        response.untyped(errorResponse(403, 'permission_denied', 'Only the owner can change roles right now.')),
      ),
    )
    signIn()
    const { user } = renderDashboard(teamPath)
    await user.click(await screen.findByRole('button', { name: 'Actions for Priya Nair' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Change role' }))

    const dialog = await findDialog({ name: 'Change role for Priya Nair' })
    await user.click(within(dialog).getByRole('radio', { name: /^Agent/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Save role' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Only the owner can change roles right now.')
  })
})
