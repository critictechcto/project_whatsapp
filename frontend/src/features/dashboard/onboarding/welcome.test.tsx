import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { site } from '../../../config/site'
import { db, type MockMembership } from '../../../mocks/db'
import { ids } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'
import { onboardingKeys, type Onboarding } from './api'
import { mockOnboardingFlags, setMockWorkspaceGoal } from './mocks'

/** A workspace created in this session: its owner hasn't seen the welcome flow. */
function newWorkspace(): { id: string; membership: MockMembership } {
  const now = new Date().toISOString()
  const id = '6b2e8d0f-4c3a-4f7b-9e21-3d5c7f9a1b01'
  db.workspaces.push({ id, name: 'Lakshmi Silks', slug: 'lakshmi-silks', time_zone: 'Asia/Kolkata', created_at: now })
  const membership: MockMembership = { id: '6b2e8d0f-4c3a-4f7b-9e21-3d5c7f9a1b02', workspace_id: id, user_id: ids.demoUser, role: 'owner', created_at: now }
  db.memberships.push(membership)
  return { id, membership }
}

/** Arjun (agent in Sharma Sweets) joined just now. */
function newAgent(): MockMembership {
  const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.arjun)!
  membership.created_at = new Date().toISOString()
  return membership
}

function mockReducedMotion(reduce: boolean) {
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: reduce && query.includes('prefers-reduced-motion: reduce'),
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList,
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

const welcomeName = `Welcome to ${site.name}, Rohan.`

async function findWelcome(name: string | RegExp = welcomeName) {
  return screen.findByRole('dialog', { name }, { timeout: 10_000 })
}

function stepTitles(list: HTMLElement) {
  return within(list)
    .getAllByRole('listitem')
    .map((item) => item.querySelector('.font-medium')?.textContent)
}

describe('welcome flow', () => {
  it('shows on a new workspace and Skip marks it seen', async () => {
    const { id, membership } = newWorkspace()
    signIn()
    const { user, queryClient } = renderDashboard(`/app/w/${id}`)

    const dialog = await findWelcome()
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(within(dialog).getByText(/official WhatsApp Business Platform/)).toBeInTheDocument()
    expect(within(dialog).getByText('Step 1 of 3')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Skip' }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: welcomeName })).not.toBeInTheDocument())
    await waitFor(() => expect(mockOnboardingFlags(membership).welcome_completed).toBe(true))

    await queryClient.refetchQueries({ queryKey: onboardingKeys.all(id) })
    expect(queryClient.getQueryData<Onboarding>(onboardingKeys.all(id))?.welcome_completed).toBe(true)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes on Escape', async () => {
    const { id, membership } = newWorkspace()
    signIn()
    const { user } = renderDashboard(`/app/w/${id}`)
    await findWelcome()
    await waitFor(() => expect(screen.getByRole('dialog')).toContainElement(document.activeElement as HTMLElement))
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(mockOnboardingFlags(membership).welcome_completed).toBe(true))
  })

  it('does not show for seeded members', async () => {
    signIn()
    const { queryClient } = renderDashboard(`/app/w/${ids.sharmaSweets}`)
    await screen.findByRole('heading', { level: 1, name: 'Welcome, Rohan' }, { timeout: 10_000 })
    await waitFor(() => expect(queryClient.getQueryData(onboardingKeys.all(ids.sharmaSweets))).toBeDefined())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('saves the goal, previews the plan and orders the home checklist', async () => {
    const { id } = newWorkspace()
    signIn()
    const { user } = renderDashboard(`/app/w/${id}`)
    const dialog = await findWelcome()

    await user.click(within(dialog).getByRole('button', { name: 'Get started' }))
    const group = await within(dialog).findByRole('radiogroup', { name: 'What do you want to do first?' })
    const support = within(group).getByRole('radio', { name: /Reply to customers faster/ })
    await user.click(support)
    expect(support).toBeChecked()
    // Arrow keys move between the cards.
    await user.keyboard('{ArrowUp}')
    expect(within(group).getByRole('radio', { name: /Send offers and updates/ })).toBeChecked()
    await user.keyboard('{ArrowDown}')
    expect(support).toBeChecked()

    await user.click(within(dialog).getByRole('button', { name: 'Continue' }))
    const plan = await within(dialog).findByRole('list', { name: 'Setup steps' })
    expect(stepTitles(plan).slice(0, 4)).toEqual(['Connect WhatsApp', 'Invite your team', 'Set up an automation', 'Add contacts'])
    expect(within(dialog).getByText("What you'll need to connect WhatsApp")).toBeInTheDocument()

    // Back keeps the choice.
    await user.click(within(dialog).getByRole('button', { name: 'Back' }))
    expect(await within(dialog).findByRole('radio', { name: /Reply to customers faster/ })).toBeChecked()
    await user.click(within(dialog).getByRole('button', { name: 'Continue' }))

    await user.click(await within(dialog).findByRole('button', { name: 'Go to dashboard' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    const section = (await screen.findByRole('heading', { level: 2, name: 'Get started' }, { timeout: 10_000 })).closest('section')!
    await waitFor(() => expect(stepTitles(section.querySelector('ol')!).slice(0, 3)).toEqual(['Connect WhatsApp', 'Invite your team', 'Set up an automation']))
  })

  it('Connect WhatsApp closes the flow and opens the WhatsApp page', async () => {
    const { id } = newWorkspace()
    signIn()
    const { user, router } = renderDashboard(`/app/w/${id}`)
    const dialog = await findWelcome()
    await user.click(within(dialog).getByRole('button', { name: 'Get started' }))
    await user.click(await within(dialog).findByRole('button', { name: 'Continue' }))
    await user.click(await within(dialog).findByRole('button', { name: 'Connect WhatsApp' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(router.state.location.pathname).toBe(`/app/w/${id}/whatsapp`))
  })

  it('gives invited teammates a shorter flow without the goal step', async () => {
    const membership = newAgent()
    signIn(ids.arjun)
    const { user } = renderDashboard(`/app/w/${ids.sharmaSweets}`)
    const dialog = await findWelcome(`Welcome to ${site.name}, Arjun.`)
    expect(within(dialog).getByText('Step 1 of 2')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Continue' }))
    expect(await within(dialog).findByRole('heading', { name: 'You joined Sharma Sweets as an agent' })).toBeInTheDocument()
    expect(within(dialog).getByText(/reply to customer chats/)).toBeInTheDocument()
    expect(within(dialog).queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: 'Connect WhatsApp' })).not.toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Go to dashboard' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(mockOnboardingFlags(membership).welcome_completed).toBe(true))
  })

  it('animates the chat scene, and renders it final with reduced motion', async () => {
    const first = newWorkspace()
    signIn()
    const animated = renderDashboard(`/app/w/${first.id}`)
    const dialog = await findWelcome()
    expect(dialog.querySelectorAll('.chat-pop')).toHaveLength(3)
    animated.unmount()

    mockReducedMotion(true)
    renderDashboard(`/app/w/${first.id}`)
    const still = await findWelcome()
    expect(still.querySelector('.chat-pop, .fade-up')).toBeNull()
    expect(within(still).getByText('Hi! Is this available?')).toBeInTheDocument()
    expect(within(still).getByText('Order confirmed')).toBeInTheDocument()
  })
})

describe('settings main goal', () => {
  it('lets admins change the goal', async () => {
    signIn()
    const { user } = renderDashboard(`/app/w/${ids.sharmaSweets}/settings`)
    const select = await screen.findByRole('combobox', { name: 'Main goal' }, { timeout: 10_000 })
    expect(select).toHaveValue('')
    await user.selectOptions(select, 'sell')
    expect(await screen.findByText('Main goal saved')).toBeInTheDocument()
    expect(select).toHaveValue('sell')
  })

  it('shows the goal read-only to agents', async () => {
    setMockWorkspaceGoal(ids.sharmaSweets, 'marketing')
    signIn(ids.arjun)
    renderDashboard(`/app/w/${ids.sharmaSweets}/settings`)
    const general = (await screen.findByRole('heading', { name: 'General' }, { timeout: 10_000 })).closest('section')!
    expect(await within(general).findByText('Send offers and updates')).toBeInTheDocument()
    expect(within(general).queryByRole('combobox')).not.toBeInTheDocument()
  })
})
