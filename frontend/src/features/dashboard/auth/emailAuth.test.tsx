import { screen, waitFor } from '@testing-library/react'
import { HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { tokenStore } from '../../../lib/auth/tokens'
import { db } from '../../../mocks/db'
import { RESET_TOKEN_PREFIX, VERIFY_TOKEN_PREFIX } from '../../../mocks/handlers/auth'
import { server } from '../../../mocks/node'
import { DEMO_EMAIL, ids } from '../../../mocks/seed'
import { readMockSession } from '../../../mocks/session'
import { errorResponse, http } from '../../../mocks/utils'
import { renderDashboard, signIn } from '../../../test/render'
import { VERIFY_BANNER_DISMISSED_KEY } from '../shell/EmailVerificationBanner'

const demoUser = () => db.users.find((user) => user.id === ids.demoUser)!
const workspacePath = `/app/w/${ids.sharmaSweets}`

beforeEach(() => {
  window.sessionStorage.clear()
})

describe('login', () => {
  it('links to forgot password', async () => {
    renderDashboard('/app/login')
    expect(await screen.findByRole('link', { name: 'Forgot password?' })).toHaveAttribute('href', '/app/forgot-password')
  })

  it('confirms a password reset', async () => {
    renderDashboard('/app/login?reason=password_reset')
    expect(await screen.findByText('Your password has been reset. Log in with your new password.')).toBeInTheDocument()
  })
})

describe('forgot password', () => {
  it('shows the same confirmation whether or not the account exists', async () => {
    const { user } = renderDashboard('/app/forgot-password')
    await user.type(await screen.findByLabelText(/^Email/), 'nobody@example.com')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))

    expect(await screen.findByText(/If an account exists for/)).toHaveTextContent(
      "If an account exists for nobody@example.com, we've sent a reset link. It expires in 1 hour.",
    )
    expect(screen.getByRole('link', { name: 'Back to log in' })).toHaveAttribute('href', '/app/login')
  })

  it('explains throttling', async () => {
    server.use(
      http.post('/api/v1/auth/password/reset/', ({ response }) =>
        response.untyped(errorResponse(429, 'throttled', 'Request was throttled.')),
      ),
    )
    const { user } = renderDashboard('/app/forgot-password')
    await user.type(await screen.findByLabelText(/^Email/), DEMO_EMAIL)
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/Too many reset requests/)
  })
})

describe('reset password', () => {
  it('sets the new password and sends the user to log in with a notice', async () => {
    signIn()
    const { user, router } = renderDashboard(`/app/reset-password?token=${RESET_TOKEN_PREFIX}${ids.demoUser}`)
    await user.type(await screen.findByLabelText(/^New password/), 'fresh-password-1')
    await user.type(screen.getByLabelText(/^Confirm new password/), 'fresh-password-1')
    await user.click(screen.getByRole('button', { name: 'Set new password' }))

    expect(await screen.findByText('Your password has been reset. Log in with your new password.')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/app/login')
    expect(demoUser().password).toBe('fresh-password-1')
    // Every session was revoked: locally and in the mock "cookie".
    expect(tokenStore.hasSession()).toBe(false)
    expect(readMockSession()).toBeNull()
  })

  it('checks the passwords match before calling the API', async () => {
    const { user } = renderDashboard(`/app/reset-password?token=${RESET_TOKEN_PREFIX}${ids.demoUser}`)
    await user.type(await screen.findByLabelText(/^New password/), 'fresh-password-1')
    await user.type(screen.getByLabelText(/^Confirm new password/), 'fresh-password-2')
    await user.click(screen.getByRole('button', { name: 'Set new password' }))
    expect(await screen.findByText("The passwords don't match.")).toBeInTheDocument()
  })

  it('shows password validator errors on the field', async () => {
    server.use(
      http.post('/api/v1/auth/password/reset/confirm/', ({ response }) =>
        response.untyped(
          errorResponse(400, 'invalid', 'Invalid input.', { new_password: ['This password is too common.'] }),
        ),
      ),
    )
    const { user } = renderDashboard(`/app/reset-password?token=${RESET_TOKEN_PREFIX}${ids.demoUser}`)
    await user.type(await screen.findByLabelText(/^New password/), 'password123')
    await user.type(screen.getByLabelText(/^Confirm new password/), 'password123')
    await user.click(screen.getByRole('button', { name: 'Set new password' }))

    expect(await screen.findByText('This password is too common.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^New password/)).toHaveAttribute('aria-invalid', 'true')
  })

  it('explains an invalid or expired link', async () => {
    const { user } = renderDashboard('/app/reset-password?token=used-token')
    await user.type(await screen.findByLabelText(/^New password/), 'fresh-password-1')
    await user.type(screen.getByLabelText(/^Confirm new password/), 'fresh-password-1')
    await user.click(screen.getByRole('button', { name: 'Set new password' }))

    expect(await screen.findByRole('heading', { name: 'This link is invalid or has expired' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Request a new link' })).toHaveAttribute('href', '/app/forgot-password')
  })

  it('treats a missing token as an invalid link', async () => {
    renderDashboard('/app/reset-password')
    expect(await screen.findByRole('heading', { name: 'This link is invalid or has expired' })).toBeInTheDocument()
  })
})

describe('verify email', () => {
  it('confirms the email and hides the reminder banner', async () => {
    demoUser().email_verified_at = null
    signIn()
    const { user, router } = renderDashboard(`/app/verify-email?token=${VERIFY_TOKEN_PREFIX}${ids.demoUser}`)

    expect(await screen.findByRole('heading', { name: 'Email confirmed' })).toBeInTheDocument()
    expect(demoUser().email_verified_at).not.toBeNull()

    await user.click(screen.getByRole('link', { name: 'Go to the dashboard' }))
    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/app\/w\//))
    expect(await screen.findByRole('navigation', { name: 'Workspace' })).toBeInTheDocument()
    expect(screen.queryByText('Confirm your email')).not.toBeInTheDocument()
  })

  it('works signed out and sends the user to log in', async () => {
    demoUser().email_verified_at = null
    renderDashboard(`/app/verify-email?token=${VERIFY_TOKEN_PREFIX}${ids.demoUser}`)
    expect(await screen.findByRole('heading', { name: 'Email confirmed' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Log in' })).toHaveAttribute('href', '/app/login')
  })

  it('offers a new link for an invalid token when signed in', async () => {
    let requests = 0
    server.use(
      http.post('/api/v1/auth/email/verify/request/', ({ response }) => {
        requests += 1
        return response.untyped(new HttpResponse(null, { status: 204 }))
      }),
    )
    demoUser().email_verified_at = null
    signIn()
    const { user } = renderDashboard('/app/verify-email?token=expired-token')

    expect(await screen.findByRole('heading', { name: 'This link is invalid or has expired' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Send a new link' }))
    expect(await screen.findByText('Sent — check your inbox')).toBeInTheDocument()
    expect(requests).toBe(1)
    expect(screen.getByRole('button', { name: 'Send a new link' })).toBeDisabled()
  })

  it('asks signed-out users to log in for a new link', async () => {
    renderDashboard('/app/verify-email?token=expired-token')
    expect(await screen.findByRole('heading', { name: 'This link is invalid or has expired' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send a new link' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Log in' })).toBeInTheDocument()
  })
})

describe('email verification banner', () => {
  it('reminds an unverified user and resends the email', async () => {
    let requests = 0
    server.use(
      http.post('/api/v1/auth/email/verify/request/', ({ response }) => {
        requests += 1
        return response.untyped(new HttpResponse(null, { status: 204 }))
      }),
    )
    demoUser().email_verified_at = null
    signIn()
    const { user } = renderDashboard(workspacePath)

    const banner = await screen.findByText('Confirm your email')
    expect(banner.closest('[role="status"]')).toHaveTextContent(`we sent a link to ${DEMO_EMAIL}`)
    await user.click(screen.getByRole('button', { name: 'Resend email' }))

    expect(await screen.findByText('Sent — check your inbox')).toBeInTheDocument()
    expect(requests).toBe(1)
    expect(screen.getByRole('button', { name: 'Resend email' })).toBeDisabled()
  })

  it('explains throttling', async () => {
    server.use(
      http.post('/api/v1/auth/email/verify/request/', ({ response }) =>
        response.untyped(errorResponse(429, 'throttled', 'Request was throttled.')),
      ),
    )
    demoUser().email_verified_at = null
    signIn()
    const { user } = renderDashboard(workspacePath)
    await user.click(await screen.findByRole('button', { name: 'Resend email' }))
    expect(await screen.findByText('Too many requests, try again later')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Resend email' })).toBeEnabled()
  })

  it('can be dismissed for the session', async () => {
    demoUser().email_verified_at = null
    signIn()
    const { user } = renderDashboard(workspacePath)
    await user.click(await screen.findByRole('button', { name: 'Dismiss email reminder' }))
    expect(screen.queryByText('Confirm your email')).not.toBeInTheDocument()
    expect(window.sessionStorage.getItem(VERIFY_BANNER_DISMISSED_KEY)).toBe(ids.demoUser)
  })

  it('is absent for a verified user', async () => {
    signIn()
    renderDashboard(workspacePath)
    expect(await screen.findByRole('navigation', { name: 'Workspace' })).toBeInTheDocument()
    expect(screen.queryByText('Confirm your email')).not.toBeInTheDocument()
  })
})
