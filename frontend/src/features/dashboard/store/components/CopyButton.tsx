import { Check, Copy } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button, type ButtonSize, type ButtonVariant } from '../../../../components/app'

type CopyButtonProps = {
  value: string
  /** Visible label, e.g. "Copy link". */
  label?: string
  /** Accessible name when it differs from the label, e.g. "Copy webhook URL". */
  'aria-label'?: string
  variant?: ButtonVariant
  size?: ButtonSize
}

/** Copies `value` to the clipboard and confirms for two seconds. Candidate for `components/app`. */
export function CopyButton({ value, label = 'Copy', variant = 'secondary', size = 'sm', ...aria }: CopyButtonProps) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')

  useEffect(() => {
    if (state === 'idle') return
    const timer = setTimeout(() => setState('idle'), 2000)
    return () => clearTimeout(timer)
  }, [state])

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setState('copied')
    } catch {
      setState('failed')
    }
  }

  return (
    <>
      <Button
        variant={variant}
        size={size}
        aria-label={aria['aria-label']}
        icon={state === 'copied' ? <Check className="size-4" aria-hidden="true" /> : <Copy className="size-4" aria-hidden="true" />}
        onClick={() => void copy()}
      >
        {state === 'copied' ? 'Copied' : label}
      </Button>
      <span role="status" className="sr-only">
        {state === 'copied' ? 'Copied to the clipboard' : state === 'failed' ? "Couldn't copy. Select the text and copy it instead." : ''}
      </span>
    </>
  )
}
