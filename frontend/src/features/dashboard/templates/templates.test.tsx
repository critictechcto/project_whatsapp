import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { db } from '../../../mocks/db'
import { server } from '../../../mocks/node'
import { ids, seedTemplates } from '../../../mocks/seed'
import { http, validationError } from '../../../mocks/utils'
import { findDialog, renderDashboard, signIn } from '../../../test/render'
import { rejectionInfo, statusExplanations } from './lib/constants'

const base = `/app/w/${ids.sharmaSweets}/templates`
const rejected = seedTemplates.find((template) => template.status === 'REJECTED')!
const approved = seedTemplates.find((template) => template.status === 'APPROVED')!

async function openBuilder() {
  signIn()
  const view = renderDashboard(`${base}/new`)
  await screen.findByRole('heading', { level: 1, name: 'New template' }, { timeout: 10_000 })
  return view
}

describe('templates list', () => {
  it('shows rejected templates with a friendly reason', async () => {
    signIn()
    renderDashboard(base)
    const link = await screen.findByRole('link', { name: rejected.name }, { timeout: 10_000 })
    const row = link.closest('tr')!
    expect(within(row).getByText(`${rejectionInfo('INVALID_FORMAT').label}.`)).toBeInTheDocument()
    expect(within(row).getByText(rejectionInfo('INVALID_FORMAT').explanation)).toBeInTheDocument()
  })

  it('filters by status', async () => {
    signIn()
    const { user } = renderDashboard(base)
    await screen.findByRole('link', { name: rejected.name }, { timeout: 10_000 })
    await user.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'REJECTED')
    await waitFor(() => expect(screen.queryByRole('link', { name: approved.name })).not.toBeInTheDocument())
    expect(screen.getByRole('link', { name: rejected.name })).toBeInTheDocument()
  })

  it('syncs from Meta and reports what was queued', async () => {
    signIn()
    const { user } = renderDashboard(base)
    await user.click(await screen.findByRole('button', { name: 'Sync from Meta' }, { timeout: 10_000 }))
    expect(await screen.findByText(/Sync started for 1 WhatsApp account/)).toBeInTheDocument()
  })
})

describe('template detail', () => {
  it('explains the rejection reason', async () => {
    signIn()
    renderDashboard(`${base}/${rejected.id}`)
    expect(await screen.findByText(`Rejected by Meta: ${rejectionInfo('INVALID_FORMAT').label}`, {}, { timeout: 10_000 })).toBeInTheDocument()
  })

  it('links approved templates to a new campaign', async () => {
    signIn()
    renderDashboard(`${base}/${approved.id}`)
    const link = await screen.findByRole('link', { name: 'Use in campaign' }, { timeout: 10_000 })
    expect(link).toHaveAttribute('href', `/app/w/${ids.sharmaSweets}/campaigns/new?template=${approved.id}`)
  })
})

describe('template builder', () => {
  it('auto-formats the name', async () => {
    const { user } = await openBuilder()
    const name = screen.getByRole('textbox', { name: /^Name/ })
    await user.type(name, 'Order Shipped-Update!')
    expect(name).toHaveValue('order_shipped_update')
  })

  it('requires sequential variable numbers', async () => {
    const { user } = await openBuilder()
    await user.type(screen.getByRole('textbox', { name: /^Name/ }), 'order_update')
    await user.click(screen.getByRole('textbox', { name: /^Message text/ }))
    await user.paste('Hi {{1}}, your {{3}} is ready.')
    await user.click(screen.getByRole('button', { name: 'Submit for review' }))

    const summary = await screen.findByRole('alert')
    expect(summary).toHaveTextContent(/Fix \d+ problems? before submitting/)
    expect(within(summary).getByText(/numbered sequentially/)).toBeInTheDocument()
  })

  it('requires an example for every variable', async () => {
    const { user } = await openBuilder()
    await user.type(screen.getByRole('textbox', { name: /^Name/ }), 'order_update')
    await user.click(screen.getByRole('textbox', { name: /^Message text/ }))
    await user.paste('Namaste {{1}}, your order of {{2}} is ready.')
    await user.type(screen.getByRole('textbox', { name: /Example for \{\{1\}\}/ }), 'Ananya')
    await user.click(screen.getByRole('button', { name: 'Submit for review' }))

    expect(await screen.findAllByText('Enter an example value for {{2}}.')).not.toHaveLength(0)
    expect(screen.queryByText('Enter an example value for {{1}}.')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /Example for \{\{2\}\}/ })).toHaveAttribute('aria-invalid', 'true')
  })

  it('inserts the next variable at the cursor', async () => {
    const { user } = await openBuilder()
    const body = screen.getByRole('textbox', { name: /^Message text/ })
    await user.click(body)
    await user.paste('Hello ')
    await user.click(screen.getByRole('button', { name: 'Add variable {{1}}' }))
    expect(body).toHaveValue('Hello {{1}}')
    expect(screen.getByRole('button', { name: 'Add variable {{2}}' })).toBeInTheDocument()
  })

  it('disables adding buttons at the limits', async () => {
    const { user } = await openBuilder()
    const add = (name: string) => screen.getByRole('button', { name })

    await user.click(add('Visit website'))
    await user.click(add('Visit website'))
    expect(add('Visit website')).toBeDisabled()

    await user.click(add('Call phone number'))
    expect(add('Call phone number')).toBeDisabled()
    await user.click(add('Copy offer code'))
    expect(add('Copy offer code')).toBeDisabled()

    for (let i = 0; i < 6; i += 1) await user.click(add('Quick reply'))
    expect(screen.getByText(/^10\/10 buttons/)).toBeInTheDocument()
    expect(add('Quick reply')).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Remove button 1' }))
    expect(add('Quick reply')).toBeEnabled()
  })

  it('updates the live preview with example values', async () => {
    const { user } = await openBuilder()
    const preview = screen.getByRole('complementary', { name: 'Preview' })
    await user.click(screen.getByRole('textbox', { name: /^Message text/ }))
    await user.paste('Namaste {{1}}, your order is ready.')
    expect(within(preview).getByText('{{1}}')).toBeInTheDocument()

    await user.type(screen.getByRole('textbox', { name: /Example for \{\{1\}\}/ }), 'Ananya')
    expect(within(preview).getByText('Namaste Ananya, your order is ready.')).toBeInTheDocument()

    await user.type(screen.getByRole('textbox', { name: /^Footer text/ }), 'Sharma Sweets, Jaipur')
    expect(within(preview).getByText('Sharma Sweets, Jaipur')).toBeInTheDocument()
  })

  it('maps nested server errors onto the matching fields', async () => {
    server.use(
      http.post('/api/v1/templates/', ({ response }) =>
        response.untyped(
          validationError({
            name: ['A template with this name and language already exists.'],
            components: [{}, { buttons: [{ url: ['Enter a valid URL.'] }] }],
          }),
        ),
      ),
    )
    const { user } = await openBuilder()
    await user.type(screen.getByRole('textbox', { name: /^Name/ }), 'order_update')
    await user.click(screen.getByRole('textbox', { name: /^Message text/ }))
    await user.paste('Namaste {{1}}, your order is ready.')
    await user.type(screen.getByRole('textbox', { name: /Example for \{\{1\}\}/ }), 'Ananya')
    await user.click(screen.getByRole('button', { name: 'Visit website' }))
    await user.type(screen.getByRole('textbox', { name: /^Button text/ }), 'Track order')
    await user.type(screen.getByRole('textbox', { name: /^Website URL/ }), 'https://sharmasweets.in/track')
    await user.click(screen.getByRole('button', { name: 'Submit for review' }))

    await waitFor(() => expect(screen.getByRole('textbox', { name: /^Website URL/ })).toHaveAttribute('aria-invalid', 'true'))
    expect(screen.getAllByText('Enter a valid URL.')).not.toHaveLength(0)
    expect(screen.getByRole('textbox', { name: /^Name/ })).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getAllByText('A template with this name and language already exists.')).not.toHaveLength(0)
  })

  it('creates a template and shows it pending review', async () => {
    const { user, router } = await openBuilder()
    await user.type(screen.getByRole('textbox', { name: /^Name/ }), 'order_update')
    await user.click(screen.getByRole('textbox', { name: /^Message text/ }))
    await user.paste('Namaste {{1}}, your order is ready for pickup.')
    await user.type(screen.getByRole('textbox', { name: /Example for \{\{1\}\}/ }), 'Ananya')
    await user.click(screen.getByRole('button', { name: 'Submit for review' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'order_update' }, { timeout: 10_000 })).toBeInTheDocument()
    expect(router.state.location.pathname).toMatch(new RegExp(`^${base}/[0-9a-f-]{36}$`))
    expect(screen.getByText(statusExplanations.PENDING ?? "")).toBeInTheDocument()
    expect(screen.getAllByText('In review')).not.toHaveLength(0)
  })
})

describe('roles', () => {
  function makeArjunViewer() {
    const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.arjun)!
    membership.role = 'viewer'
    signIn(ids.arjun)
  }

  it("hides create, sync and delete from viewers", async () => {
    makeArjunViewer()
    renderDashboard(base)
    await screen.findByRole('link', { name: rejected.name }, { timeout: 10_000 })
    expect(screen.queryByRole('link', { name: /New template/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sync from Meta' })).not.toBeInTheDocument()
  })

  it('shows viewers a read-only detail page', async () => {
    makeArjunViewer()
    renderDashboard(`${base}/${rejected.id}`)
    await screen.findByRole('heading', { level: 1, name: rejected.name }, { timeout: 10_000 })
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Submit for review' })).not.toBeInTheDocument()
  })

  it('blocks the builder route for viewers', async () => {
    makeArjunViewer()
    renderDashboard(`${base}/new`)
    expect(await screen.findByRole('heading', { name: "You don't have access to this page" }, { timeout: 10_000 })).toBeInTheDocument()
  })

  it('lets admins delete with a warning about reusing the name', async () => {
    signIn()
    const { user, router } = renderDashboard(`${base}/${approved.id}`)
    await user.click(await screen.findByRole('button', { name: 'Delete' }, { timeout: 10_000 }))
    const dialog = await findDialog()
    expect(within(dialog).getByText(/can't create a new template named/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Delete template' }))
    await waitFor(() => expect(router.state.location.pathname).toBe(base))
  })
})
