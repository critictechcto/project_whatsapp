import { useEffect, useState } from 'react'
import { ApiError, errorMessage } from '../../../../api/errors'

/** `value`, updated only after it stopped changing for `delayMs`. */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

/** User-facing text for a failed mutation; a 403 explains the role restriction. */
export function actionErrorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (error instanceof ApiError && error.status === 403) {
    return error.message && error.code !== 'http_403'
      ? error.message
      : "Your role in this workspace doesn't allow this action."
  }
  return errorMessage(error, fallback)
}
