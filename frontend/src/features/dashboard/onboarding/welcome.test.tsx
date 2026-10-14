import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { site } from '../../../config/site'
import { db, type MockMembership } from '../../../mocks/db'
import { ids } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'
import { onboardingKeys, type Onboarding } from './api'
import { mockOnboardingFlags, setMockWorkspaceGoals } from './mocks'

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

  it('saves several goals, previews the plan and orders the home checklist', async () => {
    const { id } = newWorkspace()
    signIn()
    const { user } = renderDashboard(`/app/w/${id}`)
    const dialog = await findWelcome()

    await user.click(within(dialog).getByRole('button', { name: 'Get started' }))
    const group = await within(dialog).findByRole('group', { name: 'What do you want to do first?' })
    const support = within(group).getByRole('checkbox', { name: /Reply to customers faster/ })
    const marketing = within(group).getByRole('checkbox', { name: /Send offers and updates/ })
    const sell = within(group).getByRole('checkbox', { name: /Sell products on WhatsApp/ })
    await user.click(support)
    await user.click(marketing)
    await user.click(sell)
    expect(support).toBeChecked()
    expect(marketing).toBeChecked()
    // A second click clears a choice.
    await user.click(sell)
    expect(sell).not.toBeChecked()

    await user.click(within(dialog).getByRole('button', { name: 'Continue' }))
    const plan = await within(dialog).findByRole('list', { name: 'Setup steps' })
    // Marketing's first steps, then support's, then the rest.
    expect(stepTitles(plan)).toEqual([
      'Connect WhatsApp',
      'Add contacts',
      'Create a template',
      'Send your first campaign',
      'Invite your team',
      'Set up an automation',
    ])
    expect(within(dialog).getByText("What you'll need to connect WhatsApp")).toBeInTheDocument()

    // Back keeps the choices.
    await user.click(within(dialog).getByRole('button', { name: 'Back' }))
    expect(await within(dialog).findByRole('checkbox', { name: /Reply to customers faster/ })).toBeChecked()
    expect(within(dialog).getByRole('checkbox', { name: /Send offers and updates/ })).toBeChecked()
    await user.click(within(dialog).getByRole('button', { name: 'Continue' }))

    await user.click(await within(dialog).findByRole('button', { name: 'Take a quick tour' }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: welcomeName })).not.toBeInTheDocument())
    await user.keyboard('{Escape}')

    const section = (await screen.findByRole('heading', { level: 2, name: 'Get started' }, { timeout: 10_000 })).closest('section')!
    await waitFor(() => expect(stepTitles(section.querySelector('ol')!).slice(0, 3)).toEqual(['Connect WhatsApp', 'Add contacts', 'Create a template']))
  })

  it('ends with only the tour button, which starts the tour', async () => {
    const { id, membership } = newWorkspace()
    signIn()
    const { user } = renderDashboard(`/app/w/${id}`)
    const dialog = await findWelcome()
    await user.click(within(dialog).getByRole('button', { name: 'Get started' }))
    await user.click(await within(dialog).findByRole('button', { name: 'Continue' }))
    await within(dialog).findByRole('list', { name: 'Setup steps' })

    expect(within(dialog).queryByRole('button', { name: 'Connect WhatsApp' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: 'Go to dashboard' })).not.toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Take a quick tour' }))

    expect(await screen.findByRole('dialog', { name: 'Inbox' }, { timeout: 10_000 })).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: welcomeName })).not.toBeInTheDocument()
    await waitFor(() => expect(mockOnboardingFlags(membership).welcome_completed).toBe(true))
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
    expect(within(dialog).queryByRole('checkbox')).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: 'Go to dashboard' })).not.toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Take a quick tour' }))
    expect(await screen.findByRole('dialog', { name: 'Inbox' }, { timeout: 10_000 })).toBeInTheDocument()
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

describe('settings goals', () => {
  it('lets admins choose several goals', async () => {
    signIn()
    const { user } = renderDashboard(`/app/w/${ids.sharmaSweets}/settings`)
    const sell = await screen.findByRole('checkbox', { name: /Sell products on WhatsApp/ }, { timeout: 10_000 })
    expect(sell).not.toBeChecked()
    await user.click(sell)
    expect(await screen.findByText('Goals saved')).toBeInTheDocument()
    await waitFor(() => expect(sell).toBeChecked())
    const support = screen.getByRole('checkbox', { name: /Reply to customers faster/ })
    await waitFor(() => expect(support).toBeEnabled())
    await user.click(support)
    await waitFor(() => expect(support).toBeChecked())
    expect(sell).toBeChecked()
  })

  it('shows the goals read-only to agents', async () => {
    setMockWorkspaceGoals(ids.sharmaSweets, ['marketing', 'sell'])
    signIn(ids.arjun)
    renderDashboard(`/app/w/${ids.sharmaSweets}/settings`)
    const general = (await screen.findByRole('heading', { name: 'General' }, { timeout: 10_000 })).closest('section')!
    expect(await within(general).findByText('Sell products on WhatsApp, Send offers and updates')).toBeInTheDocument()
    expect(within(general).queryByRole('checkbox')).not.toBeInTheDocument()
  })
})
