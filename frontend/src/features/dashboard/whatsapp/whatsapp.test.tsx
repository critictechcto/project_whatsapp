import { screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ids } from '../../../mocks/seed'
import { renderDashboard, signIn } from '../../../test/render'

// Tests run in live API mode, so replace the Facebook SDK with a launcher that succeeds at once.
vi.mock('../../../lib/integrations/facebook', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../lib/integrations/facebook')>()
  return {
    ...actual,
    useFacebookSdk: () => ({
      ready: true,
      error: null,
      launcher: {
        launch: async () => ({
          code: 'test-code',
          waba_id: '109283746501928',
          phone_number_id: '110293847561029',
          business_id: '564738291056473',
        }),
      },
    }),
  }
})

describe('WhatsApp', () => {
  it('shows connected numbers with quality and limits', async () => {
    signIn()
    renderDashboard(`/app/w/${ids.sharmaSweets}/whatsapp`)
    expect(await screen.findByRole('heading', { level: 1, name: 'WhatsApp' })).toBeInTheDocument()
    expect((await screen.findAllByText('+91 98290 11223')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Default').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Actions for +91 98290 11223' })).toBeInTheDocument()
  })

  it('connects a number with Embedded Signup and follows setup to completion', async () => {
    signIn()
    const { user } = renderDashboard(`/app/w/${ids.kaveriClinic}/whatsapp`)
    await user.click(await screen.findByRole('button', { name: 'Connect WhatsApp' }))

    const dialog = await screen.findByRole('dialog', { name: 'Connect WhatsApp' })
    const start = within(dialog).getByRole('button', { name: 'Continue with Facebook' })
    await vi.waitFor(() => expect(start).toBeEnabled())
    await user.click(start)

    expect(await within(dialog).findByText('WhatsApp is connected', {}, { timeout: 10_000 })).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Done' }))

    expect(await screen.findByText('Kaveri Dental Clinic', { selector: 'h2, h3' })).toBeInTheDocument()
  })
})
