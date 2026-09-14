import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http as mswHttp } from 'msw'
import { describe, expect, it } from 'vitest'
import { dispatch } from '../../../lib/realtime/registry'
import { db } from '../../../mocks/db'
import { server } from '../../../mocks/node'
import { ids } from '../../../mocks/seed'
import { apiUrl } from '../../../mocks/utils'
import { renderDashboard, signIn } from '../../../test/render'
import { inboxMockIds, inboxState } from './mockData'

const base = `/app/w/${ids.sharmaSweets}/inbox`

function messagesRegion() {
  return screen.findByRole('region', { name: /^Messages with/ })
}

function conversationLinks() {
  return within(screen.getByRole('list', { name: 'Conversations' })).getAllByRole('link')
}

async function findMessageRow(messageId: string) {
  return waitFor(() => {
    const row = document.querySelector<HTMLElement>(`[data-message-id="${messageId}"]`)
    expect(row).not.toBeNull()
    return row!
  })
}

describe('conversation list', () => {
  it('filters by view, unread and search, and keeps filters in the URL', async () => {
    signIn()
    const { router, user } = renderDashboard(base)

    expect(await screen.findByRole('heading', { level: 1, name: 'Inbox' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: /Ananya Khan/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Vihaan Verma/ })).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Mine' }))
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get('view')).toBe('mine'))
    await waitFor(() => expect(screen.queryByRole('link', { name: /Vihaan Verma/ })).not.toBeInTheDocument())
    expect(screen.getByRole('link', { name: /Ananya Khan/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Meera Banerjee/ })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Unread only' }))
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get('unread')).toBe('1'))
    await waitFor(() => expect(conversationLinks().every((link) => /unread/.test(link.textContent ?? ''))).toBe(true))

    await user.click(screen.getByRole('button', { name: 'Unread only' }))
    await user.click(screen.getByRole('tab', { name: 'Open' }))
    await waitFor(() => expect(router.state.location.search).toBe(''))

    await user.type(screen.getByRole('searchbox', { name: 'Search conversations' }), 'Kavya')
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get('q')).toBe('Kavya'))
    await waitFor(() => expect(conversationLinks()).toHaveLength(1))
    expect(conversationLinks()[0]).toHaveTextContent('Kavya Agarwal')
  })

  it('opens the next conversation with the j shortcut', async () => {
    signIn()
    const { router, user } = renderDashboard(base)
    await screen.findByRole('link', { name: /Ananya Khan/ })

    await user.keyboard('j')
    await waitFor(() => expect(router.state.location.pathname).toBe(`${base}/${inboxMockIds.ananya}`))
    expect(await messagesRegion()).toBeInTheDocument()
  })

  it('starts a conversation with a contact', async () => {
    signIn()
    const { router, user } = renderDashboard(base)

    await user.click(await screen.findByRole('button', { name: 'New conversation' }))
    const dialog = await screen.findByRole('dialog', { name: 'New conversation' })
    await user.type(within(dialog).getByRole('combobox'), 'Aarav')
    await user.click(await screen.findByRole('option', { name: /Aarav Patel/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Open conversation' }))

    await waitFor(() => expect(router.state.location.pathname).toMatch(new RegExp(`^${base}/[0-9a-f-]{36}$`)))
    expect(await screen.findByRole('heading', { level: 2, name: 'Aarav Patel' })).toBeInTheDocument()
  })
})

describe('thread and composer', () => {
  it('shows an optimistic bubble, sends one Idempotency-Key and follows server status', async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const keys: string[] = []
    server.use(
      mswHttp.post(apiUrl('/api/v1/inbox/conversations/:id/messages/'), async ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key') ?? '')
        await gate
        return undefined
      }),
    )

    signIn()
    const { user } = renderDashboard(`${base}/${inboxMockIds.ananya}`)
    const region = await messagesRegion()
    const composer = await screen.findByRole('textbox', { name: 'Reply' })

    await user.type(composer, 'Kal milte hain{Enter}')

    const pending = await within(region).findByText('Kal milte hain')
    expect(within(pending.closest('li')!).getByRole('img', { name: 'Sending' })).toBeInTheDocument()
    expect(composer).toHaveValue('')
    await waitFor(() => expect(keys).toHaveLength(1))
    expect(keys[0]).not.toBe('')

    act(() => release())

    const sent = await waitFor(() => {
      const message = inboxState().messages.get(inboxMockIds.ananya)?.at(-1)
      expect(message?.text).toBe('Kal milte hain')
      return message!
    })
    const row = await findMessageRow(sent.id)
    await waitFor(() => expect(within(region).getAllByText('Kal milte hain')).toHaveLength(1))

    act(() =>
      dispatch({
        v: 1,
        type: 'message.status',
        workspace_id: ids.sharmaSweets,
        data: { conversation_id: inboxMockIds.ananya, message_id: sent.id, status: 'sent' },
      }),
    )
    expect(await within(row).findByRole('img', { name: 'Sent' })).toBeInTheDocument()
    expect(keys).toHaveLength(1)
  })

  it('updates a tick when a realtime status arrives', async () => {
    signIn()
    renderDashboard(`${base}/${inboxMockIds.ananya}`)
    await messagesRegion()

    const row = await findMessageRow(inboxMockIds.ananyaDelivered)
    expect(within(row).getByRole('img', { name: 'Delivered' })).toBeInTheDocument()

    act(() =>
      dispatch({
        v: 1,
        type: 'message.status',
        workspace_id: ids.sharmaSweets,
        data: { conversation_id: inboxMockIds.ananya, message_id: inboxMockIds.ananyaDelivered, status: 'read' },
      }),
    )

    expect(await within(await findMessageRow(inboxMockIds.ananyaDelivered)).findByRole('img', { name: 'Read' })).toBeInTheDocument()
  })

  it('disables free-form replies when the window is closed and sends a template', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/${inboxMockIds.meera}`)
    await messagesRegion()

    expect(
      await screen.findByText(/WhatsApp only allows template messages 24 hours after the customer's last message/),
    ).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Reply' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Attach file' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Send template' }))
    const dialog = await screen.findByRole('dialog', { name: 'Send a template' })
    await user.click(within(dialog).getByRole('combobox', { name: 'Template' }))
    // Templates mocks also seed a Hindi order_shipped; pick the non-Hindi one.
    const templateOptions = await screen.findAllByRole('option', { name: /order_shipped/ })
    await user.click(templateOptions.find((option) => !option.textContent?.includes('· hi'))!)

    const header = await within(dialog).findByLabelText(/^Header/)
    await user.type(header, '4521')
    const bodyFields = within(dialog).getAllByLabelText(/^Body/)
    for (const [index, value] of ['Meera', '1 kg Kaju Katli', '14 Sep'].entries()) {
      await user.type(bodyFields[index], value)
    }
    await user.type(within(dialog).getByLabelText(/URL suffix/), '4521')
    await user.click(within(dialog).getByRole('button', { name: 'Send template' }))

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Send a template' })).not.toBeInTheDocument())
    await waitFor(() => {
      const message = inboxState().messages.get(inboxMockIds.meera)?.at(-1)
      expect(message?.type).toBe('template')
      expect(message?.text).toContain('Namaste Meera')
    })
    expect(await screen.findAllByText('Template · order_shipped')).not.toHaveLength(0)
  })

  it('explains a 409 from the API inline', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/${inboxMockIds.aditya}`)
    const region = await messagesRegion()
    expect(screen.getByText('This contact has opted out.')).toBeInTheDocument()

    await user.type(await screen.findByRole('textbox', { name: 'Reply' }), 'Hello ji{Enter}')

    expect(await within(region).findByRole('alert')).toHaveTextContent('This contact has opted out, so messages to them are blocked.')
    expect(within(region).getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    await user.click(within(region).getByRole('button', { name: 'Discard' }))
    await waitFor(() => expect(within(region).queryByText('Hello ji')).not.toBeInTheDocument())
  })

  it('rejects attachments WhatsApp does not accept', async () => {
    signIn()
    renderDashboard(`${base}/${inboxMockIds.ananya}`)
    await messagesRegion()
    const input = await screen.findByLabelText('Attachment file')

    fireEvent.change(input, { target: { files: [new File(['MZ'], 'setup.exe', { type: 'application/x-msdownload' })] } })
    expect(await screen.findByText(/setup\.exe can't be sent on WhatsApp/)).toBeInTheDocument()

    const big = new File([new Uint8Array(6 * 1024 * 1024)], 'rasmalai.png', { type: 'image/png' })
    fireEvent.change(input, { target: { files: [big] } })
    expect(await screen.findByText('rasmalai.png is 6 MB. WhatsApp accepts JPEG or PNG images up to 5 MB.')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })
})

describe('conversation actions', () => {
  it('assigns to me and closes the conversation', async () => {
    signIn()
    const { user } = renderDashboard(`${base}/${inboxMockIds.vihaan}`)
    await messagesRegion()

    await user.click(await screen.findByRole('button', { name: 'Assign to me' }))
    await waitFor(() =>
      expect(inboxState().conversations.find((conversation) => conversation.id === inboxMockIds.vihaan)?.assignee_id).toBe(ids.demoUser),
    )
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Assign to me' })).not.toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(await screen.findByRole('button', { name: 'Reopen' })).toBeInTheDocument()
    expect(inboxState().conversations.find((conversation) => conversation.id === inboxMockIds.vihaan)?.status).toBe('closed')
  })

  it('marks an unread conversation as read when opened', async () => {
    signIn()
    renderDashboard(`${base}/${inboxMockIds.kavya}`)
    await messagesRegion()
    await waitFor(() =>
      expect(inboxState().conversations.find((conversation) => conversation.id === inboxMockIds.kavya)?.unread_count).toBe(0),
    )
  })

  it('is read-only for viewers', async () => {
    const membership = db.memberships.find((m) => m.workspace_id === ids.sharmaSweets && m.user_id === ids.arjun)!
    membership.role = 'viewer'
    signIn(ids.arjun)
    renderDashboard(`${base}/${inboxMockIds.ananya}`)
    await messagesRegion()

    expect(await screen.findByText(/You have view-only access/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New conversation' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument()
  })
})

describe('mobile navigation', () => {
  it('goes back from a thread to the list and keeps the filters', async () => {
    signIn()
    const { router, user } = renderDashboard(`${base}/${inboxMockIds.ananya}?view=mine`)
    await messagesRegion()

    await user.click(screen.getByRole('link', { name: 'Back to conversations' }))
    await waitFor(() => expect(router.state.location.pathname).toBe(base))
    expect(router.state.location.search).toBe('?view=mine')
    expect(screen.getByText('Pick a conversation')).toBeInTheDocument()

    await user.click(await screen.findByRole('link', { name: /Ananya Khan/ }))
    await waitFor(() => expect(router.state.location.pathname).toBe(`${base}/${inboxMockIds.ananya}`))
  })
})
