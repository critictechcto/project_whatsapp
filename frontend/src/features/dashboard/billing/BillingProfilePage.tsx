import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm } from '../../../api/errors'
import type { Schemas } from '../../../api/types'
import { Button, Field, Input, PageHeader, PageSpinner, Select, useToast } from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { FormError } from '../auth/FormError'
import { useMe } from '../auth/session'
import { actionErrorMessage } from '../settings/ui/hooks'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import { billingProfileSchema, GST_STATES, normalizeGstin, stateFromGstin, type BillingProfileValues } from './gst'
import { billingKeys, profileKey, useBillingProfile } from './queries'

const stateOptions = GST_STATES.map((state) => ({ value: state.code, label: `${state.name} (${state.code})` }))

export function BillingProfilePage() {
  const { workspaceId } = useWorkspace()
  const profile = useBillingProfile()

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        eyebrow={
          <Link to={`/app/w/${workspaceId}/billing`} className="inline-flex items-center gap-1 hover:text-ink">
            <ArrowLeft className="size-3" aria-hidden="true" /> Billing
          </Link>
        }
        title="Billing details"
        description="These appear on your tax invoices."
      />
      {profile.isPending ? (
        <PageSpinner label="Loading billing details" />
      ) : profile.isError ? (
        <Notice
          tone="danger"
          role="alert"
          title="Couldn't load billing details"
          action={
            <Button variant="secondary" size="sm" onClick={() => void profile.refetch()}>
              Try again
            </Button>
          }
        >
          {actionErrorMessage(profile.error)}
        </Notice>
      ) : (
        <BillingProfileForm profile={profile.data} />
      )}
    </div>
  )
}

function BillingProfileForm({ profile }: { profile: Schemas['BillingProfile'] }) {
  const { workspaceId, can } = useWorkspace()
  const canEdit = can('owner')
  const me = useMe()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { toast } = useToast()
  const [params] = useSearchParams()
  const resumeCheckout = params.get('next') === 'plans'

  const {
    register,
    handleSubmit,
    setValue,
    getValues,
    setError,
    reset,
    formState: { errors, isSubmitting, isSubmitted, isDirty },
  } = useForm<BillingProfileValues>({
    resolver: zodResolver(billingProfileSchema),
    defaultValues: {
      legal_name: profile.legal_name,
      gstin: profile.gstin,
      email: profile.email || me.data?.email || '',
      address_line1: profile.address_line1,
      address_line2: profile.address_line2,
      city: profile.city,
      state_code: profile.state_code,
      postal_code: profile.postal_code,
    },
  })

  const onSubmit = handleSubmit(async (values) => {
    try {
      const saved = await unwrap(
        api.PATCH('/api/v1/billing/billing-profile/', { body: { ...values, gstin: normalizeGstin(values.gstin) } }),
      )
      queryClient.setQueryData(profileKey(workspaceId), saved)
      void queryClient.invalidateQueries({ queryKey: billingKeys.all(workspaceId), predicate: (query) => query.queryKey[3] !== 'profile' })
      toast({ title: 'Billing details saved', tone: 'success' })
      if (resumeCheckout) {
        const next = new URLSearchParams({ plan: params.get('plan') ?? '', interval: params.get('interval') ?? 'monthly', resume: '1' })
        navigate(`/app/w/${workspaceId}/billing/plans?${next}`)
      } else {
        reset({ ...saved })
      }
    } catch (error) {
      applyApiErrorToForm(error, setError, {
        fields: ['legal_name', 'gstin', 'email', 'address_line1', 'address_line2', 'city', 'state_code', 'postal_code'],
      })
      if (!Object.keys(errors).length) {
        const message = actionErrorMessage(error)
        if (message && (error as { status?: number }).status === 403) setError('root.server', { message })
      }
    }
  })

  return (
    <>
      {resumeCheckout && canEdit && (
        <Notice tone="info" title="Add your billing details to continue">
          Razorpay checkout opens after you save. Invoices include these details and the GST charged.
        </Notice>
      )}
      {!canEdit && <Notice title="View only">Only the workspace owner can change billing details.</Notice>}

      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
        <FormError message={errors.root?.server?.message} />
        <SectionCard id="billing-business" title="Business">
          <fieldset disabled={!canEdit} className="grid gap-4 sm:grid-cols-2">
            <Field label="Legal name" hint="As registered for GST, or your business name." error={errors.legal_name?.message} required className="sm:col-span-2">
              <Input autoComplete="organization" {...register('legal_name')} />
            </Field>
            <Field
              label="GSTIN"
              hint="Optional. Leave blank if you aren't GST-registered. With a GSTIN on the invoice, you may be able to claim input tax credit."
              error={errors.gstin?.message}
            >
              <Input
                className="font-mono uppercase"
                maxLength={15}
                autoComplete="off"
                placeholder="29ABCDE1234F1Z5"
                {...register('gstin', {
                  onChange: (event: { target: { value: string } }) => {
                    const code = stateFromGstin(event.target.value)
                    if (code && getValues('state_code') !== code) setValue('state_code', code, { shouldDirty: true, shouldValidate: isSubmitted })
                  },
                })}
              />
            </Field>
            <Field label="Invoice email" hint="Invoices and payment receipts go here." error={errors.email?.message} required>
              <Input type="email" autoComplete="email" {...register('email')} />
            </Field>
          </fieldset>
        </SectionCard>

        <SectionCard id="billing-address" title="Address" description="Your state decides whether GST is charged as CGST and SGST, or as IGST.">
          <fieldset disabled={!canEdit} className="grid gap-4 sm:grid-cols-2">
            <Field label="Address line 1" error={errors.address_line1?.message} required className="sm:col-span-2">
              <Input autoComplete="address-line1" {...register('address_line1')} />
            </Field>
            <Field label="Address line 2" error={errors.address_line2?.message} className="sm:col-span-2">
              <Input autoComplete="address-line2" {...register('address_line2')} />
            </Field>
            <Field label="City" error={errors.city?.message} required>
              <Input autoComplete="address-level2" {...register('city')} />
            </Field>
            <Field label="State" error={errors.state_code?.message} required>
              <Select options={stateOptions} placeholder="Choose a state" {...register('state_code')} />
            </Field>
            <Field label="PIN code" error={errors.postal_code?.message} required>
              <Input inputMode="numeric" maxLength={6} autoComplete="postal-code" {...register('postal_code')} />
            </Field>
          </fieldset>
        </SectionCard>

        {canEdit && (
          <div className="flex justify-end gap-2">
            <Link to={`/app/w/${workspaceId}/billing`} className="inline-flex h-10 items-center rounded-lg px-4 text-sm font-medium text-ink-2 hover:bg-ink/5">
              Cancel
            </Link>
            <Button type="submit" loading={isSubmitting} disabled={!isDirty && !resumeCheckout}>
              {resumeCheckout ? 'Save and continue' : 'Save billing details'}
            </Button>
          </div>
        )}
      </form>
    </>
  )
}
