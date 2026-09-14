import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useNavigate, useSearchParams } from 'react-router'
import { z } from 'zod'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm } from '../../../api/errors'
import { Button } from '../../../components/app/Button'
import { Field } from '../../../components/app/Field'
import { Input } from '../../../components/app/Input'
import { site } from '../../../config/site'
import { AuthLayout, AuthLink } from './AuthLayout'
import { FormError } from './FormError'
import { safeNext, startSession } from './session'

const schema = z.object({
  full_name: z.string().trim().min(1, 'Enter your name.').max(150),
  email: z.email('Enter a valid email address.'),
  password: z.string().min(8, 'Use at least 8 characters.'),
})

type RegisterValues = z.infer<typeof schema>

export function RegisterPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(schema), defaultValues: { full_name: '', email: '', password: '' } })

  const onSubmit = handleSubmit(async (values) => {
    try {
      const { tokens } = await unwrap(api.POST('/api/v1/auth/register/', { body: values }))
      await startSession(queryClient, tokens)
      navigate(next ?? '/app/workspaces/new', { replace: true })
    } catch (error) {
      applyApiErrorToForm(error, setError, { fields: ['full_name', 'email', 'password'] })
    }
  })

  const loginHref = next ? `/app/login?next=${encodeURIComponent(next)}` : '/app/login'

  return (
    <AuthLayout
      title="Create your account"
      description={`Start your ${site.trialDays}-day free trial. No card needed.`}
      footer={
        <>
          Already have an account? <AuthLink to={loginHref}>Log in</AuthLink>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <FormError message={errors.root?.server?.message} />
        <Field label="Your name" error={errors.full_name?.message} required>
          <Input autoComplete="name" {...register('full_name')} />
        </Field>
        <Field label="Work email" error={errors.email?.message} required>
          <Input type="email" autoComplete="email" {...register('email')} />
        </Field>
        <Field label="Password" hint="At least 8 characters." error={errors.password?.message} required>
          <Input type="password" autoComplete="new-password" {...register('password')} />
        </Field>
        <Button type="submit" loading={isSubmitting} className="mt-1 w-full">
          Create account
        </Button>
      </form>
    </AuthLayout>
  )
}
