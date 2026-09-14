import { createContext, useContext, type AriaAttributes } from 'react'

export type FieldContextValue = {
  id: string
  describedBy: string | undefined
  invalid: boolean
  required: boolean
}

export const FieldContext = createContext<FieldContextValue | null>(null)

type ControlProps = {
  id?: string
  'aria-describedby'?: string
  'aria-invalid'?: AriaAttributes['aria-invalid']
  required?: boolean
}

/** Fills id / aria attributes from the surrounding `<Field>`; explicit props win. */
export function useFieldControl<P extends ControlProps>(props: P): P {
  const field = useContext(FieldContext)
  if (!field) return props
  return {
    ...props,
    id: props.id ?? field.id,
    'aria-describedby': props['aria-describedby'] ?? field.describedBy,
    'aria-invalid': props['aria-invalid'] ?? (field.invalid || undefined),
    required: props.required ?? (field.required || undefined),
  }
}
