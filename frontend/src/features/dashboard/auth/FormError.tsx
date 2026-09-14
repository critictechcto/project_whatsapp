import { CircleAlert } from 'lucide-react'

/** Form-level error (react-hook-form `errors.root.server`). */
export function FormError({ message }: { message: string | undefined }) {
  if (!message) return null
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-signal/25 bg-signal-soft/60 px-3 py-2.5 text-sm text-signal">
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  )
}
