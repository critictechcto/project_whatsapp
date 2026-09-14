import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { CircleAlert, CircleCheck, Info, X } from 'lucide-react'
import { cn } from '../../lib/cn'
import { ToastContext, type ToastOptions } from './toastContext'

type ToastItem = ToastOptions & { id: string }

const icons = {
  success: <CircleCheck className="size-4 text-accent" aria-hidden="true" />,
  error: <CircleAlert className="size-4 text-signal" aria-hidden="true" />,
  info: <Info className="size-4 text-muted" aria-hidden="true" />,
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
    const timer = timers.current.get(id)
    if (timer) clearTimeout(timer)
    timers.current.delete(id)
  }, [])

  const toast = useCallback(
    (options: ToastOptions) => {
      const id = crypto.randomUUID()
      const tone = options.tone ?? 'info'
      setToasts((current) => [...current.slice(-3), { ...options, tone, id }])
      const duration = options.duration ?? (tone === 'error' ? 8000 : 5000)
      if (duration > 0) timers.current.set(id, setTimeout(() => dismiss(id), duration))
      return id
    },
    [dismiss],
  )

  useEffect(() => {
    const map = timers.current
    return () => {
      for (const timer of map.values()) clearTimeout(timer)
    }
  }, [])

  const api = useMemo(() => ({ toast, dismiss }), [toast, dismiss])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-4 bottom-4 z-[70] flex flex-col items-center gap-2 sm:inset-x-auto sm:right-5 sm:items-end">
        {/* Polite region for info/success; errors are announced assertively. */}
        <div aria-live="polite" className="contents">
          {toasts.filter((t) => t.tone !== 'error').map((t) => <ToastCard key={t.id} toast={t} onDismiss={dismiss} />)}
        </div>
        <div aria-live="assertive" className="contents">
          {toasts.filter((t) => t.tone === 'error').map((t) => <ToastCard key={t.id} toast={t} onDismiss={dismiss} />)}
        </div>
      </div>
    </ToastContext.Provider>
  )
}

function ToastCard({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: string) => void }) {
  return (
    <div
      className={cn(
        'fade-up pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border bg-card px-4 py-3 shadow-lg',
        toast.tone === 'error' ? 'border-signal/30' : 'border-line',
      )}
    >
      <span className="mt-0.5">{icons[toast.tone ?? 'info']}</span>
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-medium text-ink">{toast.title}</p>
        {toast.description && <p className="mt-0.5 text-muted">{toast.description}</p>}
      </div>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
        className="grid size-6 place-items-center rounded text-muted hover:bg-ink/5 hover:text-ink"
      >
        <X className="size-3.5" aria-hidden="true" />
      </button>
    </div>
  )
}
