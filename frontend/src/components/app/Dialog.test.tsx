import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { Dialog } from './Dialog'

function Harness({ dismissible = true }: { dismissible?: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open dialog
      </button>
      <button type="button">Outside</button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        dismissible={dismissible}
        title="Rename workspace"
        footer={<button type="button">Save</button>}
      >
        <label>
          Name <input />
        </label>
      </Dialog>
    </>
  )
}

const focusInside = (dialog: HTMLElement) => waitFor(() => expect(dialog).toContainElement(document.activeElement as HTMLElement))

describe('Dialog', () => {
  it('traps focus inside and closes on Escape, returning focus to the trigger', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const trigger = screen.getByRole('button', { name: 'Open dialog' })

    await user.click(trigger)
    const dialog = await screen.findByRole('dialog', { name: 'Rename workspace' })
    await focusInside(dialog)

    for (let i = 0; i < 5; i++) {
      await user.tab()
      await focusInside(dialog)
    }
    await user.tab({ shift: true })
    await focusInside(dialog)
    // The rest of the page is hidden from assistive tech while the dialog is open.
    expect(screen.queryByRole('button', { name: 'Outside' })).not.toBeInTheDocument()
    expect(screen.getByText('Outside')).not.toHaveFocus()

    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('ignores Escape while not dismissible', async () => {
    const user = userEvent.setup()
    render(<Harness dismissible={false} />)
    await user.click(screen.getByRole('button', { name: 'Open dialog' }))
    const dialog = await screen.findByRole('dialog', { name: 'Rename workspace' })

    await user.keyboard('{Escape}')
    expect(dialog).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument()
  })
})
