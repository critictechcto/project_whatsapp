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
import { AuthLayout, AuthLink } from './AuthLayout'
import { DemoCredentials } from './DemoCredentials'
import { FormError } from './FormError'
import { safeNext, startSession } from './session'

const schema = z.object({
  email: z.email('Enter a valid email address.'),
  password: z.string().min(1, 'Enter your password.'),
})

type LoginValues = z.infer<typeof schema>

export function LoginPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))

  const {
    register,
    handleSubmit,
    setError,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(schema), defaultValues: { email: '', password: '' } })

  const onSubmit = handleSubmit(async (values) => {
    try {
      const tokens = await unwrap(api.POST('/api/v1/auth/token/', { body: values }))
      await startSession(queryClient, tokens)
      navigate(next ?? '/app', { replace: true })
    } catch (error) {
      applyApiErrorToForm(error, setError, { fields: ['email', 'password'] })
    }
  })

  const registerHref = next ? `/app/register?next=${encodeURIComponent(next)}` : '/app/register'

  return (
    <AuthLayout
      title="Log in"
      description="Welcome back. Log in to your workspace."
      footer={
        <>
          New here? <AuthLink to={registerHref}>Create an account</AuthLink>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <DemoCredentials
          onUse={(email, password) => {
            setValue('email', email, { shouldValidate: true })
            setValue('password', password, { shouldValidate: true })
          }}
        />
        <FormError message={errors.root?.server?.message} />
        <Field label="Email" error={errors.email?.message} required>
          <Input type="email" autoComplete="email" {...register('email')} />
        </Field>
        <Field label="Password" error={errors.password?.message} required>
          <Input type="password" autoComplete="current-password" {...register('password')} />
        </Field>
        <Button type="submit" loading={isSubmitting} className="mt-1 w-full">
          Log in
        </Button>
      </form>
    </AuthLayout>
  )
}
