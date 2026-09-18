import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { db } from '../../../mocks/db'
import { server } from '../../../mocks/node'
import { ids } from '../../../mocks/seed'
import { errorResponse, http } from '../../../mocks/utils'
import { fill, findDialog, renderDashboard, signIn } from '../../../test/render'

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
    await fill(user, within(dialog).getByLabelText(/^Email/), 'neha.gupta@sharmasweets.in')
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
    await fill(user, within(dialog).getByLabelText(/^Email/), 'priya.nair@sharmasweets.in')
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

  it('lets an admin change a member role from the Role column', async () => {
    signIn(ids.priya)
    const { user } = renderDashboard(teamPath)
    const roleButton = await screen.findByRole('button', { name: 'Change role for Arjun Mehta, currently Agent' })
    await user.click(roleButton)

    const dialog = await findDialog({ name: 'Change role for Arjun Mehta' })
    await user.click(within(dialog).getByRole('radio', { name: /^Viewer/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Save role' }))

    expect(await screen.findByText('Arjun Mehta is now Viewer.')).toBeInTheDocument()
    expect(
      await screen.findByRole('button', { name: 'Change role for Arjun Mehta, currently Viewer' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('offers no role button for the owner or yourself', async () => {
    signIn(ids.priya)
    renderDashboard(teamPath)
    expect(await screen.findByRole('button', { name: /^Change role for Arjun Mehta/ })).toBeInTheDocument()
    // Rohan is the owner (locked) and Priya is the signed-in admin.
    expect(screen.queryByRole('button', { name: /^Change role for Rohan Sharma/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Change role for Priya Nair/ })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Owner role is locked')).toBeInTheDocument()
  })

  it('offers no role buttons to agents', async () => {
    signIn(ids.arjun)
    renderDashboard(teamPath)
    expect(await screen.findByText('Priya Nair')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Change role for/ })).not.toBeInTheDocument()
  })

  it('offers no role buttons to viewers', async () => {
    const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.demoUser)
    if (!membership) throw new Error('seed membership missing')
    membership.role = 'viewer'
    signIn()
    renderDashboard(teamPath)
    expect(await screen.findByText('Priya Nair')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Change role for/ })).not.toBeInTheDocument()
  })

  it('changes the role of a pending invitation by sending a fresh invite', async () => {
    signIn()
    const { user } = renderDashboard(teamPath)
    await user.click(await screen.findByRole('tab', { name: /Invitations/ }))
    await user.click(await screen.findByRole('button', { name: 'Change role for kavya.iyer@gmail.com, currently Agent' }))

    const dialog = await findDialog({ name: 'Change invited role' })
    expect(within(dialog).getByText(/fresh invitation with the new role/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('radio', { name: /^Admin/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Send new invitation' }))

    expect(await screen.findByText('Invitation updated for kavya.iyer@gmail.com')).toBeInTheDocument()
    expect(
      await screen.findByRole('button', { name: 'Change role for kavya.iyer@gmail.com, currently Admin' }),
    ).toBeInTheDocument()
    // The new role reached the API, and the fresh invitation replaced the open one.
    const open = db.invitations.filter((i) => i.email === 'kavya.iyer@gmail.com' && i.status === 'pending')
    expect(open).toHaveLength(1)
    expect(open[0].role).toBe('admin')
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
