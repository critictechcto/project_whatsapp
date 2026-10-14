import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { ids } from '../../../../mocks/seed'
import { server } from '../../../../mocks/node'
import { findDialog, renderDashboard, signIn } from '../../../../test/render'
import { LARGE_SCREEN_QUERY, resolveSteps } from './steps'

const originalMatchMedia = window.matchMedia

/** jsdom has no layout; the tour decides anchored vs centred from this media query. */
function setLargeScreen(large: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: large && query === LARGE_SCREEN_QUERY,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia
}

/** Records the bodies of PATCHes to the onboarding endpoint. */
function recordPatches() {
  const bodies: unknown[] = []
  const listener = ({ request }: { request: Request }) => {
    if (request.method === 'PATCH' && new URL(request.url).pathname === '/api/v1/workspaces/onboarding/') {
      void request
        .clone()
        .json()
        .then((body) => bodies.push(body))
    }
  }
  server.events.on('request:start', listener)
  return { bodies, stop: () => server.events.removeListener('request:start', listener) }
}

let patches: ReturnType<typeof recordPatches>

beforeEach(() => {
  patches = recordPatches()
})

afterEach(() => {
  patches.stop()
  window.matchMedia = originalMatchMedia
})

async function startTour() {
  signIn()
  const view = renderDashboard(`/app/w/${ids.sharmaSweets}`)
  await view.user.click(await screen.findByRole('button', { name: /Account menu for/ }))
  await view.user.click(await screen.findByRole('menuitem', { name: 'Take the tour' }))
  const dialog = await findDialog({ name: 'Inbox' })
  return { ...view, dialog }
}

describe('dashboard tour', () => {
  it('starts from the user menu anchored to Inbox and moves with Next and Back', async () => {
    setLargeScreen(true)
    const { user, dialog } = await startTour()

    expect(dialog).toHaveAttribute('data-tour-anchor', 'inbox')
    expect(within(dialog).getByText('1 of 5')).toBeInTheDocument()
    expect(screen.getByTestId('tour-spotlight')).toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: 'Back' })).not.toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Next' }))
    expect(await screen.findByRole('dialog', { name: 'Contacts' })).toHaveAttribute('data-tour-anchor', 'contacts')
    expect(screen.getByText('2 of 5')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Back' }))
    expect(await screen.findByRole('dialog', { name: 'Inbox' })).toBeInTheDocument()
    // Back is gone on the first step; focus stays inside the popover.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Next' })).toHaveFocus())

    // Tab stays inside the popover.
    const popover = screen.getByRole('dialog', { name: 'Inbox' })
    for (let i = 0; i < 3; i++) {
      await user.tab()
      await waitFor(() => expect(popover).toContainElement(document.activeElement as HTMLElement))
    }
  })

  it('records the tour as completed when finished', async () => {
    setLargeScreen(true)
    const { user } = await startTour()

    for (const title of ['Contacts', 'Templates', 'Campaigns', 'WhatsApp']) {
      await user.click(screen.getByRole('button', { name: 'Next' }))
      expect(await screen.findByRole('dialog', { name: title })).toBeInTheDocument()
    }
    expect(screen.getByText('5 of 5')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toHaveAttribute('data-tour-anchor', 'whatsapp')
    await user.click(screen.getByRole('button', { name: 'Done' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(patches.bodies).toEqual([{ tour_completed: true }]))
  })

  it('skips with the Skip button or Escape, and records it', async () => {
    const { user, dialog } = await startTour()
    await user.click(within(dialog).getByRole('button', { name: 'Skip tour' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(patches.bodies).toEqual([{ tour_completed: true }]))

    // Replaying starts again at step 1; Escape skips.
    await user.click(screen.getByRole('button', { name: /Account menu for/ }))
    await user.click(await screen.findByRole('menuitem', { name: 'Take the tour' }))
    await findDialog({ name: 'Inbox' })
    expect(screen.getByText('1 of 5')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(patches.bodies).toHaveLength(2))
  })

  it('shows centred cards without an anchor on small screens', async () => {
    setLargeScreen(false)
    const { dialog } = await startTour()
    expect(dialog).not.toHaveAttribute('data-tour-anchor')
    expect(within(dialog).getByText('1 of 5')).toBeInTheDocument()
    expect(screen.queryByTestId('tour-spotlight')).not.toBeInTheDocument()
  })

  it('skips steps whose nav item is not on screen', async () => {
    setLargeScreen(true)
    signIn()
    const { user } = renderDashboard(`/app/w/${ids.sharmaSweets}`)
    const nav = await screen.findByRole('navigation', { name: 'Workspace' })
    // Stand-in for an item the role can't see: the sidebar doesn't render it.
    within(nav).getByRole('link', { name: 'Contacts' }).closest('li')?.remove()

    await user.click(screen.getByRole('button', { name: /Account menu for/ }))
    await user.click(await screen.findByRole('menuitem', { name: 'Take the tour' }))
    await findDialog({ name: 'Inbox' })
    expect(screen.getByText('1 of 4')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByRole('dialog', { name: 'Templates' })).toBeInTheDocument()
  })
})

describe('resolveSteps', () => {
  function sidebar(items: string[]) {
    const root = document.createElement('nav')
    for (const id of items) {
      const link = document.createElement('a')
      link.dataset.tour = id
      root.append(link)
    }
    return root
  }

  it('falls back to Settings when the WhatsApp item is missing on a large screen', () => {
    const steps = resolveSteps('agent', true, sidebar(['inbox', 'contacts', 'templates', 'campaigns', 'settings']))
    expect(steps.map((step) => step.target)).toEqual(['inbox', 'contacts', 'templates', 'campaigns', 'settings'])
  })

  it('ignores the DOM on small screens and returns nothing when no item is on a large one', () => {
    expect(resolveSteps('viewer', false, sidebar([]))).toHaveLength(5)
    expect(resolveSteps('viewer', true, sidebar([]))).toEqual([])
  })
})
