import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Combobox } from './Combobox'

const cities = [
  { value: 'mumbai', label: 'Mumbai' },
  { value: 'pune', label: 'Pune' },
  { value: 'jaipur', label: 'Jaipur' },
]

function Harness({ onChange }: { onChange: (value: string[]) => void }) {
  const [value, setValue] = useState<string[]>([])
  return (
    <Combobox
      multiple
      aria-label="Cities"
      options={cities}
      value={value}
      onChange={(next) => {
        setValue(next)
        onChange(next)
      }}
    />
  )
}

describe('Combobox', () => {
  it('supports the full keyboard flow for multi-select', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<Harness onChange={onChange} />)
    const input = screen.getByRole('combobox', { name: 'Cities' })

    await user.tab()
    expect(input).toHaveFocus()
    expect(input).toHaveAttribute('aria-expanded', 'false')

    await user.keyboard('{ArrowDown}')
    expect(input).toHaveAttribute('aria-expanded', 'true')
    const options = screen.getAllByRole('option')
    expect(input).toHaveAttribute('aria-activedescendant', options[0].id)

    await user.keyboard('{ArrowDown}')
    expect(input).toHaveAttribute('aria-activedescendant', options[1].id)

    await user.keyboard('{Enter}')
    expect(onChange).toHaveBeenLastCalledWith(['pune'])
    expect(screen.getByRole('button', { name: 'Remove Pune' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Pune' })).toHaveAttribute('aria-selected', 'true')

    await user.keyboard('{Escape}')
    expect(input).toHaveAttribute('aria-expanded', 'false')

    await user.keyboard('{Backspace}')
    expect(onChange).toHaveBeenLastCalledWith([])
    expect(screen.queryByRole('button', { name: 'Remove Pune' })).not.toBeInTheDocument()
  })

  it('filters by typing and wraps around with ArrowUp', async () => {
    const user = userEvent.setup()
    render(<Harness onChange={vi.fn()} />)
    const input = screen.getByRole('combobox', { name: 'Cities' })

    await user.tab()
    await user.keyboard('jai')
    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual(['Jaipur'])

    await user.clear(input)
    await user.keyboard('{ArrowUp}')
    const options = screen.getAllByRole('option')
    expect(input).toHaveAttribute('aria-activedescendant', options[options.length - 1].id)
  })
})
