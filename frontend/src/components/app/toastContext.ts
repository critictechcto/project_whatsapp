import { createContext, useContext, type ReactNode } from 'react'

export type ToastTone = 'success' | 'error' | 'info'

export type ToastOptions = {
  title: ReactNode
  description?: ReactNode
  tone?: ToastTone
  /** Milliseconds; 0 keeps it until dismissed. Default 5000 (errors 8000). */
  duration?: number
}

export type ToastApi = {
  toast: (options: ToastOptions) => string
  dismiss: (id: string) => void
}

export const ToastContext = createContext<ToastApi | null>(null)

/** `const { toast } = useToast(); toast({ title: 'Template submitted', tone: 'success' })` */
export function useToast(): ToastApi {
  const value = useContext(ToastContext)
  if (!value) throw new Error('useToast() must be used inside <ToastProvider>')
  return value
}
