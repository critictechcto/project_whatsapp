import { useEffect, useId, useState } from 'react'
import { Link } from 'react-router'
import { api, unwrap } from '../../../../api/client'
import { ApiError, errorMessage, isApiError } from '../../../../api/errors'
import { Button, Dialog, Field, Input, Select, Skeleton, useToast } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { useWorkspace } from '../../../../lib/workspace'
import { useAvailableCatalogs, useInvalidateCatalog, useWhatsAppAccounts } from '../api'
import { FormError } from './shared'
import { PermissionsNotice } from './PermissionsNotice'

type Props = { open: boolean; onOpenChange: (open: boolean) => void }

export function ConnectCatalogDialog({ open, onOpenChange }: Props) {
  const [busy, setBusy] = useState(false)
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      dismissible={!busy}
      title="Connect a Meta catalog"
      description="Pick the WhatsApp Business Account, then use a catalog from your Meta business or create a new one. We keep it in sync with your products."
    >
      {open && <ConnectForm onClose={() => onOpenChange(false)} onBusyChange={setBusy} />}
    </Dialog>
  )
}

type Mode = 'existing' | 'create'

function ConnectForm({ onClose, onBusyChange }: { onClose: () => void; onBusyChange: (busy: boolean) => void }) {
  const { workspaceId } = useWorkspace()
  const invalidate = useInvalidateCatalog()
  const { toast } = useToast()
  const accounts = useWhatsAppAccounts()
  const [wabaId, setWabaId] = useState('')
  const [mode, setMode] = useState<Mode>('existing')
  const [catalogId, setCatalogId] = useState('')
  const [name, setName] = useState('')
  const [fieldError, setFieldError] = useState<string>()
  const [error, setError] = useState<unknown>(null)
  const [submitting, setSubmitting] = useState(false)
  const radioName = useId()

  const accountList = accounts.data ?? []
  const selectedWaba = wabaId || accountList[0]?.id || ''
  const available = useAvailableCatalogs(selectedWaba, mode === 'existing')

  useEffect(() => {
    onBusyChange(submitting)
  }, [submitting, onBusyChange])

  const permissionsMissing = isApiError(error, 'catalog_permissions_missing') || isApiError(available.error, 'catalog_permissions_missing')

  const submit = async () => {
    setFieldError(undefined)
    setError(null)
    if (mode === 'existing' && !catalogId) {
      setFieldError('Choose a catalog.')
      return
    }
    if (mode === 'create' && !name.trim()) {
      setFieldError('Enter a name for the new catalog.')
      return
    }
    setSubmitting(true)
    try {
      await unwrap(
        api.POST('/api/v1/catalog/meta-catalogs/', {
          body: mode === 'existing' ? { waba_id: selectedWaba, catalog_id: catalogId } : { waba_id: selectedWaba, create_name: name.trim() },
        }),
      )
      void invalidate()
      toast({ title: 'Meta catalog connected', description: 'Products with a photo start syncing now.', tone: 'success' })
      onClose()
    } catch (err) {
      setError(err)
      if (err instanceof ApiError) {
        const fields = err.fieldErrors
        const message = fields.catalog_id ?? fields.create_name ?? fields.waba_id
        if (message) setFieldError(message)
      }
      setSubmitting(false)
    }
  }

  if (accounts.isPending) {
    return (
      <div aria-busy="true" className="flex flex-col gap-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }

  if (!accountList.length) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm text-ink-2">Connect a WhatsApp Business Account before connecting a Meta catalog.</p>
        <div className="-mx-5 -mb-4 flex justify-end gap-2 border-t border-line-2 px-5 py-3.5">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Link to={`/app/w/${workspaceId}/whatsapp`} className="inline-flex h-10 items-center rounded-md bg-ink px-4 text-sm font-medium text-paper hover:bg-ink-2">
            Connect WhatsApp
          </Link>
        </div>
      </div>
    )
  }

  const showFormError = error !== null && !permissionsMissing && !fieldError

  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        void submit()
      }}
    >
      {permissionsMissing && <PermissionsNotice />}
      {showFormError && <FormError message={errorMessage(error)} />}

      <Field label="WhatsApp Business Account">
        <Select
          value={selectedWaba}
          onChange={(event) => {
            setWabaId(event.target.value)
            setCatalogId('')
          }}
          options={accountList.map((account) => ({ value: account.id, label: account.name || account.waba_id }))}
        />
      </Field>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-[13px] font-medium text-ink">Catalog</legend>
        {(['existing', 'create'] as const).map((value) => (
          <label key={value} className="flex cursor-pointer items-start gap-2.5 text-sm text-ink">
            <input
              type="radio"
              name={`${radioName}-mode`}
              value={value}
              checked={mode === value}
              onChange={() => {
                setMode(value)
                setFieldError(undefined)
              }}
              className="mt-0.5 size-4 accent-accent"
            />
            {value === 'existing' ? 'Use a catalog from my Meta business' : 'Create a new catalog'}
          </label>
        ))}
      </fieldset>

      {mode === 'existing' ? (
        <fieldset className="flex flex-col gap-1.5" aria-describedby={fieldError ? `${radioName}-error` : undefined}>
          <legend className="sr-only">Available catalogs</legend>
          {available.isFetching && !available.data ? (
            <div aria-busy="true" className="flex flex-col gap-1.5">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : available.isError ? (
            !permissionsMissing && <FormError message={errorMessage(available.error)} />
          ) : available.data?.length ? (
            available.data.map((catalog) => (
              <label
                key={catalog.id}
                className={cn(
                  'flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2.5 text-sm',
                  catalogId === catalog.id ? 'border-accent bg-accent-soft/40' : 'border-line-2 hover:border-ink/30',
                )}
              >
                <input
                  type="radio"
                  name={`${radioName}-catalog`}
                  value={catalog.id}
                  checked={catalogId === catalog.id}
                  onChange={() => setCatalogId(catalog.id)}
                  className="size-4 accent-accent"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-ink">{catalog.name}</span>
                  <span className="block font-mono text-[11.5px] text-muted">ID {catalog.id}</span>
                </span>
              </label>
            ))
          ) : (
            <p className="text-[13px] text-muted">No catalogs found in your Meta business. Create a new one instead.</p>
          )}
          {fieldError && (
            <p id={`${radioName}-error`} className="text-[13px] text-signal">
              {fieldError}
            </p>
          )}
        </fieldset>
      ) : (
        <Field label="New catalog name" required error={fieldError} hint="Created in the Meta business that owns this WhatsApp Business Account.">
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Sharma Sweets products" />
        </Field>
      )}

      <div className="-mx-5 -mb-4 mt-1 flex flex-wrap justify-end gap-2 border-t border-line-2 px-5 py-3.5">
        <Button variant="secondary" onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" loading={submitting}>
          {mode === 'existing' ? 'Connect catalog' : 'Create and connect'}
        </Button>
      </div>
    </form>
  )
}
