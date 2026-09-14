import { act, renderHook } from '@testing-library/react'
import { useForm } from 'react-hook-form'
import { describe, expect, it } from 'vitest'
import { ApiError, applyApiErrorToForm, errorMessage, flattenDetails } from './errors'

function validationError(details: unknown) {
  return new ApiError(400, { error: { code: 'invalid', message: 'Invalid input.', details } })
}

type Values = { email: string; full_name: string; phone: string }

function useTestForm() {
  const form = useForm<Values>({ defaultValues: { email: '', full_name: '', phone: '' } })
  // Subscribe to errors so re-renders expose them.
  void form.formState.errors
  return form
}

describe('flattenDetails', () => {
  it('flattens DRF details to dotted paths, keeping the first message', () => {
    expect(
      flattenDetails({
        email: ['Enter a valid email address.', 'Second message.'],
        address: { city: ['This field is required.'] },
        non_field_errors: ['Pick a plan first.'],
      }),
    ).toMatchObject({
      email: 'Enter a valid email address.',
      'address.city': 'This field is required.',
      '': 'Pick a plan first.',
    })
  })
})

describe('applyApiErrorToForm', () => {
  it('puts field errors on fields and unknown ones on root.server', () => {
    const { result } = renderHook(useTestForm)
    let applied = false
    act(() => {
      applied = applyApiErrorToForm(
        validationError({ email: ['A user with that email already exists.'], plan: ['Unknown plan.'] }),
        result.current.setError,
        { fields: ['email', 'full_name', 'phone'] },
      )
    })

    expect(applied).toBe(true)
    expect(result.current.formState.errors.email?.message).toBe('A user with that email already exists.')
    expect(result.current.formState.errors.root?.server?.message).toBe('Unknown plan.')
  })

  it('maps API field names onto form field names', () => {
    const { result } = renderHook(useTestForm)
    act(() => {
      applyApiErrorToForm(validationError({ phone_e164: ['Enter a valid Indian mobile number.'] }), result.current.setError, {
        fieldMap: { phone_e164: 'phone' },
        fields: ['email', 'full_name', 'phone'],
      })
    })
    expect(result.current.formState.errors.phone?.message).toBe('Enter a valid Indian mobile number.')
    expect(result.current.formState.errors.root).toBeUndefined()
  })

  it('shows non-validation errors as a form-level message', () => {
    const { result } = renderHook(useTestForm)
    let applied = true
    act(() => {
      applied = applyApiErrorToForm(
        new ApiError(401, { error: { code: 'no_active_account', message: 'No active account found.', details: null } }),
        result.current.setError,
      )
    })
    expect(applied).toBe(false)
    expect(result.current.formState.errors.root?.server?.message).toBe('No active account found.')
  })
})

describe('ApiError', () => {
  it('falls back to a status code when the body is not an envelope', () => {
    const error = new ApiError(502, '<html>Bad gateway</html>')
    expect(error.code).toBe('http_502')
    expect(errorMessage(error)).toBe('Request failed with status 502')
  })
})
