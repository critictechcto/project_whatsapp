import { X } from 'lucide-react'
import { useId, useState } from 'react'
import { cn } from '../../../../lib/cn'

type KeywordChipsInputProps = {
  label: string
  value: readonly string[]
  onChange: (value: string[]) => void
  error?: string
  hint?: string
  disabled?: boolean
  required?: boolean
  max?: number
}

/** Free-text chips: Enter or comma adds a keyword, Backspace on an empty input removes the last one. */
export function KeywordChipsInput({ label, value, onChange, error, hint, disabled, required, max = 50 }: KeywordChipsInputProps) {
  const id = useId()
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const [draft, setDraft] = useState('')

  const add = (raw: string) => {
    const words = raw
      .split(',')
      .map((word) => word.trim())
      .filter(Boolean)
    setDraft('')
    if (!words.length) return
    const next = [...value]
    for (const word of words) {
      if (next.length >= max) break
      if (!next.some((keyword) => keyword.toLowerCase() === word.toLowerCase())) next.push(word)
    }
    if (next.length !== value.length) onChange(next)
  }

  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-ink">
        {label}
        {required && (
          <span aria-hidden="true" className="text-signal">
            {' '}
            *
          </span>
        )}
      </label>
      <div
        className={cn(
          'flex min-h-10 flex-wrap items-center gap-1.5 rounded-lg border bg-card px-2 py-1.5 focus-within:border-ink/40',
          error ? 'border-signal' : 'border-line',
          disabled && 'opacity-60',
        )}
      >
        {value.length > 0 && (
          <ul aria-label={`${label} added`} className="contents">
            {value.map((keyword) => (
              <li key={keyword} className="inline-flex items-center gap-1 rounded-full bg-accent-soft py-0.5 pl-2.5 pr-1 font-mono text-[12px] text-accent-2">
                {keyword}
                <button
                  type="button"
                  aria-label={`Remove keyword ${keyword}`}
                  disabled={disabled}
                  onClick={() => onChange(value.filter((item) => item !== keyword))}
                  className="rounded-full p-0.5 hover:bg-accent/15"
                >
                  <X className="size-3" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}
        <input
          id={id}
          value={draft}
          disabled={disabled}
          placeholder={value.length ? 'Add another' : 'price'}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={(event) => {
            const next = event.target.value
            if (next.includes(',')) add(next)
            else setDraft(next)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              add(draft)
            } else if (event.key === 'Backspace' && !draft && value.length) {
              onChange(value.slice(0, -1))
            }
          }}
          onBlur={() => add(draft)}
          className="h-7 min-w-28 flex-1 bg-transparent px-1 text-sm text-ink outline-none placeholder:text-muted"
        />
      </div>
      {hint && (
        <p id={hintId} className="text-[12.5px] text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-[13px] text-signal">
          {error}
        </p>
      )}
    </div>
  )
}
