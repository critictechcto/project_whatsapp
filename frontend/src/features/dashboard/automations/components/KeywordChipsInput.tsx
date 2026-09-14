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
  /** Names a chip in the remove button, e.g. `Remove pincode 302001`. Default `keyword`. */
  itemName?: string
  placeholder?: string
  /** Applied to each entry before validation, e.g. lower-casing. */
  normalize?: (entry: string) => string
  /** Returns a message for an entry that can't be added; the entry stays in the input. */
  validate?: (entry: string) => string | null
  inputMode?: 'text' | 'numeric'
}

/**
 * Free-text chips: Enter or comma adds an entry, Backspace on an empty input removes the last one.
 * Candidate for `components/app` (used by automations and the store settings).
 */
export function KeywordChipsInput({
  label,
  value,
  onChange,
  error,
  hint,
  disabled,
  required,
  max = 50,
  itemName = 'keyword',
  placeholder = 'price',
  normalize,
  validate,
  inputMode,
}: KeywordChipsInputProps) {
  const id = useId()
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const [draft, setDraft] = useState('')
  const [draftError, setDraftError] = useState<string | null>(null)

  const add = (raw: string) => {
    const entries = raw
      .split(',')
      .map((entry) => (normalize ? normalize(entry.trim()) : entry.trim()))
      .filter(Boolean)
    const rejected: string[] = []
    let message: string | null = null
    const next = [...value]
    for (const entry of entries) {
      const problem = validate?.(entry) ?? null
      if (problem) {
        rejected.push(entry)
        message ??= problem
        continue
      }
      if (next.length >= max) break
      if (!next.some((existing) => existing.toLowerCase() === entry.toLowerCase())) next.push(entry)
    }
    setDraft(rejected.join(', '))
    setDraftError(message)
    if (next.length !== value.length) onChange(next)
  }

  const shownError = draftError ?? error
  const describedBy = [hint ? hintId : null, shownError ? errorId : null].filter(Boolean).join(' ') || undefined

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
          shownError ? 'border-signal' : 'border-line',
          disabled && 'opacity-60',
        )}
      >
        {value.length > 0 && (
          <ul aria-label={`${label} added`} className="contents">
            {value.map((entry) => (
              <li key={entry} className="inline-flex items-center gap-1 rounded-full bg-accent-soft py-0.5 pl-2.5 pr-1 font-mono text-[12px] text-accent-2">
                {entry}
                <button
                  type="button"
                  aria-label={`Remove ${itemName} ${entry}`}
                  disabled={disabled}
                  onClick={() => onChange(value.filter((item) => item !== entry))}
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
          inputMode={inputMode}
          placeholder={value.length ? 'Add another' : placeholder}
          aria-invalid={shownError ? true : undefined}
          aria-describedby={describedBy}
          onChange={(event) => {
            const next = event.target.value
            setDraftError(null)
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
      {shownError && (
        <p id={errorId} className="text-[13px] text-signal">
          {shownError}
        </p>
      )}
    </div>
  )
}
