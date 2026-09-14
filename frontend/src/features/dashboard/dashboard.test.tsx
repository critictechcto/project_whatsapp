import { act, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { getActiveWorkspaceId } from '../../api/client'
import { createQueryClient } from '../../api/queryClient'
import { DEMO_EMAIL, DEMO_PASSWORD, ids } from '../../mocks/seed'
import { renderDashboard, signIn } from '../../test/render'
import { navItems } from './registry'
import { enterWorkspace } from './shell/workspaceSwitch'

describe('route guards', () => {
  it('sends signed-out users to login and remembers where they were going', async () => {
    const target = `/app/w/${ids.sharmaSweets}/inbox`
    const { router } = renderDashboard(target)

    expect(await screen.findByRole('heading', { name: 'Log in' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app/login')
    expect(new URLSearchParams(router.state.location.search).get('next')).toBe(target)
  })

  it('logs in and continues to the requested page', async () => {
    const target = `/app/w/${ids.sharmaSweets}/inbox`
    const { router, user } = renderDashboard(target)

    await user.type(await screen.findByLabelText(/^Email/), DEMO_EMAIL)
    await user.type(screen.getByLabelText(/^Password/), DEMO_PASSWORD)
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Inbox' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(target)
  })

  it('sends signed-in users from login to their workspace home', async () => {
    signIn()
    const { router } = renderDashboard('/app/login')
    expect(await screen.findByRole('heading', { level: 1, name: 'Welcome, Rohan' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(`/app/w/${ids.sharmaSweets}`)
  })

  it('shows "not found" for a workspace the user is not a member of', async () => {
    signIn()
    renderDashboard(`/app/w/${ids.anandTextiles}`)
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })
})

describe('API errors in forms', () => {
  it('shows a field error from the error envelope on the register form', async () => {
    const { user } = renderDashboard('/app/register')
    await user.type(await screen.findByLabelText(/^Your name/), 'Rohan Sharma')
    await user.type(screen.getByLabelText(/^Work email/), DEMO_EMAIL)
    await user.type(screen.getByLabelText(/^Password/), 'long-enough-password')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText('A user with that email already exists.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^Work email/)).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows a non-field error as a form alert on login', async () => {
    const { user } = renderDashboard('/app/login')
    await user.type(await screen.findByLabelText(/^Email/), DEMO_EMAIL)
    await user.type(screen.getByLabelText(/^Password/), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('No active account found with the given credentials')
  })
})

describe('app shell', () => {
  it('renders every nav area', async () => {
    signIn()
    const { user } = renderDashboard(`/app/w/${ids.sharmaSweets}`)
    const nav = await screen.findByRole('navigation', { name: 'Workspace' })

    for (const item of navItems) {
      await user.click(within(nav).getByRole('link', { name: item.label }))
      const expected = item.id === 'home' ? 'Welcome, Rohan' : item.label
      expect(await screen.findByRole('heading', { level: 1, name: expected })).toBeInTheDocument()
    }
  })
})

describe('workspace switch', () => {
  it('drops the previous workspace queries and activates the new workspace', async () => {
    signIn()
    const { router, queryClient } = renderDashboard(`/app/w/${ids.sharmaSweets}`)
    await screen.findByRole('heading', { level: 1, name: 'Welcome, Rohan' })
    const sharmaQueries = () => queryClient.getQueryCache().findAll({ queryKey: ['ws', ids.sharmaSweets] })
    await waitFor(() => expect(sharmaQueries().length).toBeGreaterThan(0))

    await act(() => router.navigate(`/app/w/${ids.kaveriClinic}`))

    await waitFor(() => expect(getActiveWorkspaceId()).toBe(ids.kaveriClinic))
    expect(await screen.findByText('Kaveri Dental Clinic', { selector: 'header p' })).toBeInTheDocument()
    expect(sharmaQueries()).toHaveLength(0)
  })

  it('keeps the cache when re-entering the same workspace', () => {
    const queryClient = createQueryClient()
    queryClient.setQueryData(['ws', 'a', 'contacts', 'list', {}], { results: [] })
    enterWorkspace(queryClient, 'a')
    enterWorkspace(queryClient, 'a')
    expect(queryClient.getQueryData(['ws', 'a', 'contacts', 'list', {}])).toBeDefined()

    queryClient.setQueryData(['workspaces'], [])
    enterWorkspace(queryClient, 'b')
    expect(queryClient.getQueryData(['ws', 'a', 'contacts', 'list', {}])).toBeUndefined()
    // Non-workspace queries (me, workspaces) survive.
    expect(queryClient.getQueryData(['workspaces'])).toBeDefined()
  })
})
