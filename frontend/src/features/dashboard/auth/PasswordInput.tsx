import { Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'
import { Input, type InputProps } from '../../../components/app'
import { cn } from '../../../lib/cn'

/** Password field with a show/hide toggle. Use inside `<Field>` like `Input`. */
export function PasswordInput({ className, ...props }: Omit<InputProps, 'type' | 'prefix'>) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="relative">
      <Input {...props} type={visible ? 'text' : 'password'} className={cn('pr-11', className)} />
      <button
        type="button"
        onClick={() => setVisible((current) => !current)}
        aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible}
        className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-md text-muted hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25"
      >
        {visible ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
      </button>
    </div>
  )
}
