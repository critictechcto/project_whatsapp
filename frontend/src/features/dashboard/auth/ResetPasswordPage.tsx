import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { z } from 'zod'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm, isApiError } from '../../../api/errors'
import { Button } from '../../../components/app/Button'
import { Field } from '../../../components/app/Field'
import { buttonClasses } from '../../../components/app/styles'
import { tokenStore } from '../../../lib/auth/tokens'
import { AuthLayout, AuthLink } from './AuthLayout'
import { FormError } from './FormError'
import { PasswordInput } from './PasswordInput'
import { endSessionLocally } from './session'

const schema = z
  .object({
    new_password: z.string().min(8, 'Use at least 8 characters.'),
    confirm_password: z.string().min(1, 'Enter the new password again.'),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    path: ['confirm_password'],
    message: "The passwords don't match.",
  })

type ResetValues = z.infer<typeof schema>

/** True when the API rejected the link itself (used, expired or made up). */
function isTokenError(error: unknown): boolean {
  return isApiError(error, 'invalid') && 'token' in error.fieldErrors
}

function InvalidLink() {
  return (
    <AuthLayout
      title="This link is invalid or has expired"
      description="Reset links work once and expire after 1 hour. Request a new one to choose a password."
      footer={<AuthLink to="/app/login">Back to log in</AuthLink>}
    >
      <Link to="/app/forgot-password" className={buttonClasses('primary', 'md', 'w-full')}>
        Request a new link
      </Link>
    </AuthLayout>
  )
}

/** `/app/reset-password?token=…` from the reset email. A successful reset signs out every session. */
export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [linkInvalid, setLinkInvalid] = useState(false)

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ResetValues>({ resolver: zodResolver(schema), defaultValues: { new_password: '', confirm_password: '' } })

  const onSubmit = handleSubmit(async ({ new_password }) => {
    try {
      await unwrap(api.POST('/api/v1/auth/password/reset/confirm/', { body: { token, new_password } }))
      // The server revoked every session; drop this tab's (and other tabs') local state to match.
      if (tokenStore.hasSession()) endSessionLocally(queryClient)
      navigate('/app/login?reason=password_reset', { replace: true })
    } catch (error) {
      if (isTokenError(error)) {
        setLinkInvalid(true)
        return
      }
      applyApiErrorToForm(error, setError, { fields: ['new_password'] })
    }
  })

  if (!token || linkInvalid) return <InvalidLink />

  return (
    <AuthLayout
      title="Choose a new password"
      description="After the change you'll be logged out everywhere, so log in again with the new password."
      footer={<AuthLink to="/app/login">Back to log in</AuthLink>}
    >
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4" aria-busy={isSubmitting || undefined}>
        <FormError message={errors.root?.server?.message} />
        <Field label="New password" hint="At least 8 characters." error={errors.new_password?.message} required>
          <PasswordInput autoComplete="new-password" {...register('new_password')} />
        </Field>
        <Field label="Confirm new password" error={errors.confirm_password?.message} required>
          <PasswordInput autoComplete="new-password" {...register('confirm_password')} />
        </Field>
        <Button type="submit" loading={isSubmitting} className="mt-1 w-full">
          Set new password
        </Button>
      </form>
    </AuthLayout>
  )
}
