import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { server } from '../../../mocks/node'
import { DEMO_EMAIL, DEMO_INVITE_TOKEN, ids } from '../../../mocks/seed'
import { http, validationError } from '../../../mocks/utils'
import { renderDashboard, signIn } from '../../../test/render'

describe('login', () => {
  it('maps field errors from the API onto the form', async () => {
    server.use(
      http.post('/api/v1/auth/token/', ({ response }) =>
        response.untyped(validationError({ email: ['This account has been deactivated.'] })),
      ),
    )
    const { user } = renderDashboard('/app/login')
    await user.type(await screen.findByLabelText(/^Email/), DEMO_EMAIL)
    await user.type(screen.getByLabelText(/^Password/), 'demo12345')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByText('This account has been deactivated.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^Email/)).toHaveAttribute('aria-invalid', 'true')
  })

  it('validates on the client before calling the API', async () => {
    const { user } = renderDashboard('/app/login')
    await user.type(await screen.findByLabelText(/^Email/), 'not-an-email')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument()
    expect(screen.getByText('Enter your password.')).toBeInTheDocument()
  })

  it('explains why the user was sent back to login', async () => {
    renderDashboard('/app/login?reason=session_expired')
    expect(await screen.findByText('Your session expired. Log in again to continue.')).toBeInTheDocument()
  })
})

describe('accept invitation', () => {
  it('asks signed-out users to log in first', async () => {
    renderDashboard(`/app/invitations/accept?token=${DEMO_INVITE_TOKEN}`)
    expect(await screen.findByRole('heading', { name: "You've been invited" })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Log in to accept' })).toHaveAttribute(
      'href',
      expect.stringContaining(encodeURIComponent(`token=${DEMO_INVITE_TOKEN}`)),
    )
  })

  it('shows a clear state for an expired or invalid invitation', async () => {
    signIn()
    const { user } = renderDashboard('/app/invitations/accept?token=expired-token')
    await user.click(await screen.findByRole('button', { name: 'Accept invitation' }))
    expect(await screen.findByRole('heading', { name: "This invitation can't be used" })).toBeInTheDocument()
  })

  it('tells the user when the invitation was sent to another email', async () => {
    signIn()
    const { user } = renderDashboard('/app/invitations/accept?token=sharma-invite-token')
    await user.click(await screen.findByRole('button', { name: 'Accept invitation' }))
    expect(await screen.findByRole('heading', { name: 'This invitation is for another email' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Log out and switch account' })).toBeInTheDocument()
  })

  it('joins the workspace and opens it', async () => {
    signIn()
    const { user, router } = renderDashboard(`/app/invitations/accept?token=${DEMO_INVITE_TOKEN}`)
    await user.click(await screen.findByRole('button', { name: 'Accept invitation' }))
    await waitFor(() => expect(router.state.location.pathname).toBe(`/app/w/${ids.anandTextiles}`))
    expect(await screen.findByText(/You joined/)).toBeInTheDocument()
  })
})
