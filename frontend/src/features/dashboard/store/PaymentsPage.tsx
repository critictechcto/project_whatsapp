import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { Link } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm, errorMessage, isApiError } from '../../../api/errors'
import { Button, Field, Input, PageSpinner, StatusBadge, useToast } from '../../../components/app'
import { formatDateTime, formatRelative } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { RadioCards } from '../campaigns/components/RadioCards'
import { ConfirmDialog } from '../settings/ui/ConfirmDialog'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import { storeQueryKeys, usePaymentAccount, type PaymentAccount, type PaymentProvider } from './api'
import { CopyButton } from './components/CopyButton'
import { Disclosure } from './components/Disclosure'
import { StoreFrame } from './components/StoreNav'
import {
  accountStatusInfo,
  accountToForm,
  formToAccountPatch,
  hasSavedKeys,
  modeLabels,
  paymentsSchema,
  providerInfo,
  razorpayModeFromKey,
  type PaymentsFormValues,
} from './payments'

const providers: PaymentProvider[] = ['razorpay', 'cashfree']

export function PaymentsPage() {
  const { workspaceId } = useWorkspace()
  const account = usePaymentAccount(workspaceId)

  return (
    <StoreFrame description="Take online payments through your own Razorpay or Cashfree account. Buyers pay you directly; UpChatz never holds the money.">
      {account.isPending ? (
        <PageSpinner />
      ) : account.isError ? (
        <Notice
          tone="danger"
          role="alert"
          title="Couldn't load payment settings"
          action={
            <Button variant="secondary" size="sm" onClick={() => void account.refetch()}>
              Try again
            </Button>
          }
        >
          {errorMessage(account.error)}
        </Notice>
      ) : (
        <PaymentsEditor account={account.data} />
      )}
    </StoreFrame>
  )
}

function useAccountCache() {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  return {
    set: (account: PaymentAccount) => {
      queryClient.setQueryData(storeQueryKeys.payments(workspaceId), account)
      void queryClient.invalidateQueries({ queryKey: storeQueryKeys.checklist(workspaceId) })
    },
    refetch: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: storeQueryKeys.payments(workspaceId) }),
        queryClient.invalidateQueries({ queryKey: storeQueryKeys.checklist(workspaceId) }),
      ]),
  }
}

function PaymentsEditor({ account }: { account: PaymentAccount }) {
  const { workspaceId, can } = useWorkspace()
  const { toast } = useToast()
  const cache = useAccountCache()
  const [provider, setProvider] = useState<PaymentProvider>(account.provider ?? 'razorpay')
  const [pendingProvider, setPendingProvider] = useState<PaymentProvider | null>(null)
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)
  const [verifyError, setVerifyError] = useState<string | null>(null)

  const sameProvider = provider === (account.provider ?? 'razorpay')
  const hasSecret = sameProvider && account.has_key_secret
  const info = providerInfo[provider]

  const {
    control,
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isDirty, isSubmitting },
  } = useForm<PaymentsFormValues>({ resolver: zodResolver(paymentsSchema(provider, hasSecret)), defaultValues: accountToForm(account) })
  const keyId = useWatch({ control, name: 'key_id' })

  const switchProvider = useMutation({
    mutationFn: (next: PaymentProvider) => unwrap(api.PATCH('/api/v1/payments/account/', { body: { provider: next } })),
    onSuccess: (saved, next) => {
      cache.set(saved)
      setProvider(next)
      setPendingProvider(null)
      reset(accountToForm(saved))
      toast({ title: `Switched to ${providerInfo[next].name}`, description: 'Your saved keys were cleared.' })
    },
    onError: (error) => {
      setPendingProvider(null)
      toast({ title: "Couldn't switch the gateway", description: errorMessage(error), tone: 'error' })
    },
  })

  const verify = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/payments/account/verify/')),
    onMutate: () => setVerifyError(null),
    onSuccess: (saved) => {
      cache.set(saved)
      toast({ title: `Connected to ${providerInfo[provider].name}`, tone: 'success' })
    },
    onError: (error) => {
      if (isApiError(error, 'payment_account_invalid')) {
        void cache.refetch()
        return
      }
      if (isApiError(error, 'invalid') && applyApiErrorToForm(error, setError, { fields: ['key_id', 'key_secret', 'mode'] })) return
      setVerifyError(errorMessage(error))
    },
  })

  const disconnect = useMutation({
    mutationFn: () => unwrap(api.DELETE('/api/v1/payments/account/')),
    onSuccess: async () => {
      setConfirmDisconnect(false)
      await cache.refetch()
      setProvider('razorpay')
      reset(accountToForm(undefined))
      toast({ title: 'Gateway disconnected', description: 'Buyers can only pay cash on delivery until you connect one again.' })
    },
    onError: (error) => {
      setConfirmDisconnect(false)
      toast({ title: "Couldn't disconnect", description: errorMessage(error), tone: 'error' })
    },
  })

  function chooseProvider(next: PaymentProvider) {
    if (next === provider) return
    if (next === account.provider) {
      setProvider(next)
      reset(accountToForm(account))
    } else if (hasSavedKeys(account)) {
      setPendingProvider(next)
    } else {
      setProvider(next)
      reset({ key_id: '', key_secret: '', mode: '' })
    }
  }

  const onSubmit = handleSubmit(async (values) => {
    setVerifyError(null)
    try {
      const saved = await unwrap(api.PATCH('/api/v1/payments/account/', { body: formToAccountPatch(provider, values) }))
      cache.set(saved)
      reset(accountToForm(saved))
      toast({ title: 'Keys saved', description: `Verify them to start taking payments through ${info.name}.` })
    } catch (error) {
      applyApiErrorToForm(error, setError, { fields: ['key_id', 'key_secret', 'mode'] })
    }
  })

  const status = sameProvider ? (account.status ?? 'not_configured') : 'not_configured'
  const statusInfo = accountStatusInfo[status]
  const derivedMode = provider === 'razorpay' ? razorpayModeFromKey(keyId) : null
  const canVerify = sameProvider && Boolean(account.key_id) && account.has_key_secret && !isDirty

  return (
    <div className="flex flex-col gap-6">
      {status === 'not_configured' && (
        <Notice
          title="No gateway connected"
          action={
            <Link to={`/app/w/${workspaceId}/store/settings`} className="text-[13px] text-accent-2 underline underline-offset-4">
              Cash on delivery settings
            </Link>
          }
        >
          Until you connect Razorpay or Cashfree, buyers can only pay cash on delivery, if it's turned on in store settings.
        </Notice>
      )}

      <SectionCard
        id="payment-gateway"
        title="Payment gateway"
        description="Choose your gateway, paste your API keys, then verify. We create a payment link on your account for each online order."
        actions={<StatusBadge tone={statusInfo.tone}>{statusInfo.label}</StatusBadge>}
      >
        <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-5">
          <RadioCards
            legend="Gateway"
            value={provider}
            onChange={chooseProvider}
            options={providers.map((value) => ({ value, label: providerInfo[value].name, description: providerInfo[value].description }))}
          />

          <Notice tone="success" title="No webhook setup needed — we confirm payments automatically.">
            When a buyer pays, we confirm the payment as they return from the payment page, and keep checking with {info.name} until the
            link expires.
          </Notice>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={info.keyLabel} hint={info.whereToFind} error={errors.key_id?.message} required>
              <Input {...register('key_id')} autoComplete="off" spellCheck={false} placeholder={info.keyPlaceholder} className="font-mono text-[13px]" />
            </Field>
            <Field
              label={info.secretLabel}
              hint={hasSecret ? 'Saved. It is never shown again; type a new one only to replace it.' : 'Stored encrypted and never shown again.'}
              error={errors.key_secret?.message}
              required={!hasSecret}
            >
              <Input
                {...register('key_secret')}
                type="password"
                autoComplete="new-password"
                spellCheck={false}
                placeholder={hasSecret ? 'Saved' : ''}
                className="font-mono text-[13px]"
              />
            </Field>
          </div>

          {provider === 'razorpay' ? (
            <p className="text-[13px] text-muted" aria-live="polite">
              {derivedMode ? (
                <>
                  Mode: <span className="font-medium text-ink">{modeLabels[derivedMode]}</span>, from your key.{' '}
                  {derivedMode === 'test' ? 'Buyers will see Razorpay test checkout; no real money moves.' : 'Buyers pay real money.'}
                </>
              ) : (
                'Mode comes from your key: rzp_test_ keys are test mode, rzp_live_ keys are live.'
              )}
            </p>
          ) : (
            <Controller
              control={control}
              name="mode"
              render={({ field }) => (
                <RadioCards
                  legend="Mode"
                  value={field.value}
                  onChange={field.onChange}
                  error={errors.mode?.message}
                  options={[
                    { value: 'test', label: 'Test (sandbox)', description: 'Keys from the Cashfree sandbox. No real money moves.' },
                    { value: 'live', label: 'Live', description: 'Keys from your production Cashfree account.' },
                  ]}
                />
              )}
            />
          )}

          {status === 'verified' && account.verified_at && (
            <p className="text-[13px] text-muted">
              Verified <time dateTime={account.verified_at} title={formatDateTime(account.verified_at)}>{formatRelative(account.verified_at)}</time>
              {account.mode ? ` in ${modeLabels[account.mode].toLowerCase()} mode` : ''}.
            </p>
          )}
          {status === 'invalid' && (
            <Notice tone="danger" role="alert" title={`${info.name} didn't accept these keys`}>
              {account.last_error || 'Check the keys and try again.'}
            </Notice>
          )}
          {verifyError && (
            <Notice tone="danger" role="alert">
              {verifyError}
            </Notice>
          )}
          {errors.root?.server?.message && (
            <Notice tone="danger" role="alert">
              {errors.root.server.message}
            </Notice>
          )}

          <div className="flex flex-col-reverse gap-2 border-t border-line-2 pt-4 sm:flex-row sm:items-center sm:justify-end">
            {isDirty && sameProvider && account.key_id && <span className="text-[13px] text-muted sm:mr-auto">Save your changes before verifying.</span>}
            <Button variant="secondary" disabled={!canVerify} loading={verify.isPending} onClick={() => verify.mutate()}>
              Verify
            </Button>
            <Button type="submit" loading={isSubmitting}>
              Save keys
            </Button>
          </div>
        </form>
      </SectionCard>

      <WebhookSection account={account} provider={provider} />

      {sameProvider && hasSavedKeys(account) && (
        <SectionCard
          id="payment-disconnect"
          tone="danger"
          title="Disconnect gateway"
          description="Removes your keys from UpChatz. Payment links already sent keep working on your gateway."
          actions={
            can('owner') ? (
              <Button variant="danger" size="sm" onClick={() => setConfirmDisconnect(true)}>
                Disconnect {info.name}
              </Button>
            ) : undefined
          }
        >
          {!can('owner') && <p className="text-[13px] text-muted">Only the workspace owner can disconnect the gateway.</p>}
        </SectionCard>
      )}

      <ConfirmDialog
        open={pendingProvider !== null}
        onOpenChange={(open) => !open && setPendingProvider(null)}
        title={pendingProvider ? `Switch to ${providerInfo[pendingProvider].name}?` : 'Switch gateway?'}
        description={`Your saved ${providerInfo[account.provider ?? 'razorpay'].name} keys will be cleared, and online payments stop until you verify the new gateway.`}
        confirmLabel="Switch and clear keys"
        loading={switchProvider.isPending}
        onConfirm={() => pendingProvider && switchProvider.mutate(pendingProvider)}
      />
      <ConfirmDialog
        open={confirmDisconnect}
        onOpenChange={setConfirmDisconnect}
        title={`Disconnect ${info.name}?`}
        description="Buyers will only be able to pay cash on delivery until you connect a gateway again."
        confirmLabel="Disconnect"
        loading={disconnect.isPending}
        onConfirm={() => disconnect.mutate()}
      />
    </div>
  )
}

function WebhookSection({ account, provider }: { account: PaymentAccount; provider: PaymentProvider }) {
  const { toast } = useToast()
  const cache = useAccountCache()
  const [secret, setSecret] = useState('')
  const [secretError, setSecretError] = useState<string | null>(null)
  const [confirmRotate, setConfirmRotate] = useState(false)
  const info = providerInfo[provider]
  const ready = provider === account.provider && Boolean(account.webhook_url)

  const saveSecret = useMutation({
    mutationFn: (value: string) => unwrap(api.PATCH('/api/v1/payments/account/', { body: { webhook_secret: value } })),
    onMutate: () => setSecretError(null),
    onSuccess: (saved) => {
      cache.set(saved)
      setSecret('')
      toast({ title: 'Webhook secret saved', tone: 'success' })
    },
    onError: (error) => setSecretError(isApiError(error, 'invalid') ? (error.fieldErrors.webhook_secret ?? errorMessage(error)) : errorMessage(error)),
  })

  const rotate = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/payments/account/rotate-webhook/')),
    onSuccess: (saved) => {
      cache.set(saved)
      setConfirmRotate(false)
      toast({ title: 'New webhook URL ready', description: `Update it in your ${info.name} webhook settings.` })
    },
    onError: (error) => {
      setConfirmRotate(false)
      toast({ title: "Couldn't rotate the URL", description: errorMessage(error), tone: 'error' })
    },
  })

  return (
    <Disclosure title="Faster confirmation (optional)" description="Add a webhook in your gateway so payments are confirmed the moment buyers pay.">
      <div className="flex flex-col gap-4 text-sm">
        <p className="text-muted">Payments are confirmed without this. A webhook only makes confirmation faster.</p>
        {!ready ? (
          <p className="text-muted">Save your {info.name} keys first to get your webhook URL.</p>
        ) : (
          <>
            <Field label="Webhook URL" hint={`Paste this in ${info.name}'s webhook settings.`}>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input readOnly value={account.webhook_url} className="font-mono text-[13px]" onFocus={(event) => event.target.select()} />
                <CopyButton value={account.webhook_url} aria-label="Copy webhook URL" />
              </div>
            </Field>
            <div>
              <p className="text-[13px] font-medium text-ink">Events to select</p>
              <ul aria-label="Webhook events" className="mt-1 flex flex-wrap gap-1.5">
                {account.webhook_events.map((event) => (
                  <li key={event} className="rounded-md bg-paper-2 px-2 py-0.5 font-mono text-[12px] text-ink">
                    {event}
                  </li>
                ))}
              </ul>
            </div>
            {provider === 'razorpay' ? (
              <form
                noValidate
                className="flex flex-col gap-2"
                onSubmit={(event) => {
                  event.preventDefault()
                  if (!secret.trim()) {
                    setSecretError('Enter the secret you set on the webhook in Razorpay.')
                    return
                  }
                  saveSecret.mutate(secret.trim())
                }}
              >
                <Field
                  label="Webhook secret"
                  hint={account.has_webhook_secret ? 'Saved. Type a new one only to replace it.' : 'The secret you enter when creating the webhook in Razorpay.'}
                  error={secretError ?? undefined}
                >
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Input
                      type="password"
                      autoComplete="new-password"
                      value={secret}
                      placeholder={account.has_webhook_secret ? 'Saved' : ''}
                      onChange={(event) => setSecret(event.target.value)}
                      className="font-mono text-[13px]"
                    />
                    <Button type="submit" variant="secondary" loading={saveSecret.isPending}>
                      Save secret
                    </Button>
                  </div>
                </Field>
              </form>
            ) : (
              <p className="text-[13px] text-muted">Cashfree signs webhooks with your secret key, so there's no separate webhook secret.</p>
            )}
            <div className="flex flex-wrap items-center gap-3 border-t border-line-2 pt-4">
              <Button variant="secondary" size="sm" onClick={() => setConfirmRotate(true)}>
                Rotate URL
              </Button>
              <span className="text-[13px] text-muted">Use this if the URL was shared by mistake.</span>
            </div>
          </>
        )}
      </div>
      <ConfirmDialog
        open={confirmRotate}
        onOpenChange={setConfirmRotate}
        title="Rotate the webhook URL?"
        description={`The current URL stops working straight away. Paste the new one in ${info.name}; payments are still confirmed automatically meanwhile.`}
        confirmLabel="Rotate URL"
        loading={rotate.isPending}
        onConfirm={() => rotate.mutate()}
      />
    </Disclosure>
  )
}
