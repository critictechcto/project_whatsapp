import type { InputHTMLAttributes, ReactNode, Ref, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '../../lib/cn'
import { useFieldControl } from './fieldContext'
import { controlClasses } from './styles'

export type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'prefix'> & {
  ref?: Ref<HTMLInputElement>
  /** Icon or text inside the left edge, e.g. a search icon or "+91". */
  prefix?: ReactNode
}

export function Input({ className, prefix, ref, ...rest }: InputProps) {
  const props = useFieldControl(rest)
  if (!prefix) return <input ref={ref} className={cn(controlClasses, 'h-10', className)} {...props} />
  return (
    <div className="relative">
      <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-muted">{prefix}</span>
      <input ref={ref} className={cn(controlClasses, 'h-10 pl-9', className)} {...props} />
    </div>
  )
}

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & { ref?: Ref<HTMLTextAreaElement> }

export function Textarea({ className, rows = 4, ref, ...rest }: TextareaProps) {
  const props = useFieldControl(rest)
  return <textarea ref={ref} rows={rows} className={cn(controlClasses, 'py-2 leading-relaxed', className)} {...props} />
}

export type SelectOption = { value: string; label: string; disabled?: boolean }

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  ref?: Ref<HTMLSelectElement>
  options?: readonly SelectOption[]
  /** Adds an empty first option. */
  placeholder?: string
}

/** Native `<select>`: best keyboard, mobile and screen-reader support for single choice. */
export function Select({ className, options, placeholder, children, ref, ...rest }: SelectProps) {
  const props = useFieldControl(rest)
  return (
    <div className="relative">
      <select ref={ref} className={cn(controlClasses, 'h-10 appearance-none pr-9', className)} {...props}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options?.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
        {children}
      </select>
      <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
    </div>
  )
}
