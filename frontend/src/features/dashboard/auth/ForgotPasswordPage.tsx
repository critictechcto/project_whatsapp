import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'
import { z } from 'zod'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm, isApiError } from '../../../api/errors'
import { Button } from '../../../components/app/Button'
import { Field } from '../../../components/app/Field'
import { Input } from '../../../components/app/Input'
import { buttonClasses } from '../../../components/app/styles'
import { Notice } from '../settings/ui/Notice'
import { AuthLayout, AuthLink } from './AuthLayout'
import { FormError } from './FormError'

const schema = z.object({
  email: z.email('Enter a valid email address.'),
})

type ForgotValues = z.infer<typeof schema>

/** `/app/forgot-password`: asks for a reset link. The answer is the same whether or not the account exists. */
export function ForgotPasswordPage() {
  const [sentTo, setSentTo] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ForgotValues>({ resolver: zodResolver(schema), defaultValues: { email: '' } })

  const onSubmit = handleSubmit(async ({ email }) => {
    try {
      await unwrap(api.POST('/api/v1/auth/password/reset/', { body: { email } }))
      setSentTo(email)
    } catch (error) {
      if (isApiError(error) && error.status === 429) {
        setError('root.server', {
          type: 'server',
          message: 'Too many reset requests. Wait a little while, then try again.',
        })
        return
      }
      applyApiErrorToForm(error, setError, { fields: ['email'] })
    }
  })

  const footer = (
    <>
      Remembered it? <AuthLink to="/app/login">Back to log in</AuthLink>
    </>
  )

  if (sentTo) {
    return (
      <AuthLayout title="Check your email">
        <div className="flex flex-col gap-4">
          <Notice role="status" tone="success">
            If an account exists for <strong className="font-medium text-ink">{sentTo}</strong>, we've sent a reset link.
            It expires in 1 hour.
          </Notice>
          <p className="text-sm text-muted">No email after a few minutes? Check your spam folder, or try another address.</p>
          <div className="flex flex-col gap-2.5">
            <Link to="/app/login" className={buttonClasses('primary', 'md', 'w-full')}>
              Back to log in
            </Link>
            <Button variant="secondary" className="w-full" onClick={() => setSentTo(null)}>
              Use another email
            </Button>
          </div>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Reset your password"
      description="Enter your account email and we'll send you a link to choose a new password."
      footer={footer}
    >
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4" aria-busy={isSubmitting || undefined}>
        <FormError message={errors.root?.server?.message} />
        <Field label="Email" error={errors.email?.message} required>
          <Input type="email" autoComplete="email" inputMode="email" {...register('email')} />
        </Field>
        <Button type="submit" loading={isSubmitting} className="mt-1 w-full">
          Send reset link
        </Button>
      </form>
    </AuthLayout>
  )
}
