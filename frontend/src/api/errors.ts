import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'

/** Every API error body: `{"error": {"code", "message", "details"}}`. */
export type ErrorEnvelope = {
  error: {
    code: string
    message: string
    details: unknown
  }
}

export function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false
  const error = (value as { error: unknown }).error
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { code?: unknown }).code === 'string' &&
    typeof (error as { message?: unknown }).message === 'string'
  )
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(status: number, body: unknown) {
    const envelope = isErrorEnvelope(body) ? body.error : null
    super(envelope?.message ?? `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.code = envelope?.code ?? (status === 0 ? 'network_error' : `http_${status}`)
    this.details = envelope?.details ?? null
  }

  static async fromResponse(response: Response): Promise<ApiError> {
    const body: unknown = await response.clone().json().catch(() => null)
    return new ApiError(response.status, body)
  }

  /** Field errors from a validation (`invalid`) response, flattened to dotted paths. */
  get fieldErrors(): Record<string, string> {
    return this.code === 'invalid' ? flattenDetails(this.details) : {}
  }
}

export function isApiError(error: unknown, code?: string): error is ApiError {
  return error instanceof ApiError && (code === undefined || error.code === code)
}

const NON_FIELD_KEYS = new Set(['non_field_errors', '__all__', 'detail'])

/**
 * Flattens DRF validation details into `{ "path.to.field": "first message" }`.
 * - `{ email: ["Taken."] }` → `{ email: "Taken." }`
 * - `{ address: { city: ["Required."] } }` → `{ "address.city": "Required." }`
 * - `{ items: [{}, { name: ["Required."] }] }` → `{ "items.1.name": "Required." }`
 * - `non_field_errors` / `__all__` / top-level string arrays → key `""`.
 */
export function flattenDetails(details: unknown, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {}

  const put = (key: string, message: string) => {
    if (!(key in out)) out[key] = message
  }

  const walk = (value: unknown, path: string) => {
    if (value === null || value === undefined) return
    if (typeof value === 'string') {
      put(path, value)
      return
    }
    if (Array.isArray(value)) {
      if (value.every((item) => typeof item === 'string')) {
        if (value.length) put(path, value[0] as string)
        return
      }
      value.forEach((item, index) => walk(item, path ? `${path}.${index}` : String(index)))
      return
    }
    if (typeof value === 'object') {
      for (const [key, child] of Object.entries(value)) {
        const childPath = NON_FIELD_KEYS.has(key) ? path : path ? `${path}.${key}` : key
        walk(child, childPath)
      }
    }
  }

  walk(details, prefix)
  return out
}

/** A human-readable message for any thrown value. */
export function errorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (error instanceof ApiError) {
    if (error.code === 'invalid') return flattenDetails(error.details)[''] ?? 'Please check the highlighted fields.'
    return error.message
  }
  if (error instanceof TypeError) return 'Could not reach the server. Check your connection and try again.'
  if (error instanceof Error && error.message) return error.message
  return fallback
}

export type ApplyFormErrorsOptions = {
  /** Map API field paths onto form field names, e.g. `{ phone_e164: 'phone' }`. */
  fieldMap?: Record<string, string>
  /** Form fields that exist. Errors for other paths go to `root.server`. Omit to accept every path. */
  fields?: readonly string[]
}

/**
 * Maps an API error onto react-hook-form. Field errors land on their fields; everything else
 * (other codes, non-field errors, unknown fields) lands on `root.server` so the form can render it.
 * Returns true when at least one field error was applied.
 */
export function applyApiErrorToForm<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  options: ApplyFormErrorsOptions = {},
): boolean {
  const setRoot = (message: string) => setError('root.server' as Path<T>, { type: 'server', message })

  if (!(error instanceof ApiError) || error.code !== 'invalid') {
    setRoot(errorMessage(error))
    return false
  }

  let applied = false
  const leftovers: string[] = []
  const errors = flattenDetails(error.details)

  for (const [apiPath, message] of Object.entries(errors)) {
    const field = options.fieldMap?.[apiPath] ?? apiPath
    const known = field !== '' && (!options.fields || options.fields.includes(field))
    if (known) {
      setError(field as Path<T>, { type: 'server', message }, { shouldFocus: !applied })
      applied = true
    } else {
      leftovers.push(message)
    }
  }

  if (leftovers.length) setRoot(leftovers.join(' '))
  else if (!applied) setRoot(error.message)
  return applied
}
