import { CircleAlert, RefreshCw, Store, TriangleAlert, Unplug } from 'lucide-react'
import { useState } from 'react'
import { api, unwrap } from '../../../../api/client'
import { errorMessage, isApiError } from '../../../../api/errors'
import { Button, EmptyState, Skeleton, StatusBadge, Switch, useToast } from '../../../../components/app'
import { formatDateTime, formatRelative } from '../../../../lib/datetime'
import { formatNumber } from '../../../../lib/format'
import { useWorkspace } from '../../../../lib/workspace'
import { useInvalidateCatalog, useMetaCatalogs } from '../api'
import { CatalogLayout } from '../components/CatalogLayout'
import { ConnectCatalogDialog } from '../components/ConnectCatalogDialog'
import { PermissionsNotice } from '../components/PermissionsNotice'
import { ConfirmDialog, Note } from '../components/shared'
import { catalogStatusInfo } from '../lib/labels'
import type { CommerceSettings, MetaCatalog } from '../lib/types'

export function NativeCatalogPage() {
  const { can } = useWorkspace()
  const canManage = can('admin')
  const catalogs = useMetaCatalogs()
  const [connectOpen, setConnectOpen] = useState(false)
  const catalog = catalogs.data?.[0]

  let body: React.ReactNode
  if (catalogs.isPending) {
    body = <Skeleton className="h-64 w-full rounded-xl" />
  } else if (catalogs.isError) {
    body = (
      <EmptyState
        icon={<TriangleAlert />}
        title="The Meta catalog didn't load"
        description={errorMessage(catalogs.error)}
        action={
          <Button variant="secondary" onClick={() => void catalogs.refetch()}>
            Try again
          </Button>
        }
      />
    )
  } else if (!catalog) {
    body = (
      <EmptyState
        icon={<Store />}
        title="No Meta catalog connected"
        description={
          canManage
            ? 'Your store works in chat menus without one. Connect a catalog to also offer WhatsApp’s own catalog and cart.'
            : 'Your store works in chat menus without one. An admin can connect a Meta catalog.'
        }
        action={canManage && <Button onClick={() => setConnectOpen(true)}>Connect a Meta catalog</Button>}
      />
    )
  } else {
    body = <ConnectedCatalog catalog={catalog} canManage={canManage} />
  }

  return (
    <CatalogLayout tab="whatsapp">
      <Note>
        <p>
          WhatsApp&apos;s native catalog and cart are optional. Under Meta&apos;s current rules they need catalog permissions approved
          for your WhatsApp connection, a business that follows Meta&apos;s Commerce Policy, and each product passing Meta&apos;s review.
        </p>
        <p className="mt-1">
          Meta also needs a public photo for every product, so products without one aren&apos;t synced. Buyers can still shop from your
          chat menus while products are in review.
        </p>
      </Note>
      {body}
      <ConnectCatalogDialog open={connectOpen} onOpenChange={setConnectOpen} />
    </CatalogLayout>
  )
}

function ConnectedCatalog({ catalog, canManage }: { catalog: MetaCatalog; canManage: boolean }) {
  const { timeZone } = useWorkspace()
  const invalidate = useInvalidateCatalog()
  const { toast } = useToast()
  const [syncing, setSyncing] = useState(false)
  const [disconnectOpen, setDisconnectOpen] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)
  const [actionError, setActionError] = useState<unknown>(null)
  const status = catalogStatusInfo[catalog.status]

  const syncNow = async () => {
    setSyncing(true)
    setActionError(null)
    try {
      await unwrap(api.POST('/api/v1/catalog/meta-catalogs/{id}/sync/', { params: { path: { id: catalog.id } } }))
      toast({ title: 'Sync started', description: 'Counts update here as Meta processes your products.', tone: 'success' })
      void invalidate()
    } catch (error) {
      setActionError(error)
    } finally {
      setSyncing(false)
    }
  }

  const disconnect = async () => {
    setDisconnecting(true)
    try {
      await unwrap(api.DELETE('/api/v1/catalog/meta-catalogs/{id}/', { params: { path: { id: catalog.id } } }))
      toast({ title: 'Meta catalog disconnected', tone: 'success' })
      setDisconnectOpen(false)
      void invalidate()
    } catch (error) {
      toast({ title: "Couldn't disconnect the catalog", description: errorMessage(error), tone: 'error' })
    } finally {
      setDisconnecting(false)
    }
  }

  const counts = [
    { label: 'Synced', value: catalog.product_counts.synced },
    { label: 'Pending', value: catalog.product_counts.pending },
    { label: 'Failed', value: catalog.product_counts.failed },
    { label: 'Approved', value: catalog.product_counts.approved },
    { label: 'Rejected', value: catalog.product_counts.rejected },
  ]
  const permissionsMissing = catalog.status === 'permissions_missing' || isApiError(actionError, 'catalog_permissions_missing')

  return (
    <section aria-labelledby="meta-catalog-name" className="flex flex-col gap-5 rounded-xl border border-line bg-card p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="meta-catalog-name" className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
              {catalog.catalog_name}
            </h2>
            <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
          </div>
          <p className="mt-1 text-[13px] text-muted">
            <span className="font-mono">Catalog ID {catalog.catalog_id}</span> · {catalog.waba.name}
          </p>
        </div>
        {canManage && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" icon={<RefreshCw className="size-4" aria-hidden="true" />} loading={syncing} onClick={() => void syncNow()}>
              Sync now
            </Button>
            <Button variant="ghost" icon={<Unplug className="size-4" aria-hidden="true" />} onClick={() => setDisconnectOpen(true)}>
              Disconnect
            </Button>
          </div>
        )}
      </div>

      {permissionsMissing && <PermissionsNotice />}
      {actionError !== null && !permissionsMissing && (
        <p role="alert" className="text-[13px] text-signal">
          {errorMessage(actionError)}
        </p>
      )}
      {catalog.last_sync_error && (
        <div role="alert" className="flex items-start gap-2 rounded-lg border border-signal/25 bg-signal-soft/50 px-3 py-2.5 text-[13px] text-ink-2">
          <CircleAlert className="mt-0.5 size-4 shrink-0 text-signal" aria-hidden="true" />
          <span>
            <span className="font-medium text-signal">Last sync failed: </span>
            {catalog.last_sync_error}
          </span>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <p className="text-[13px] text-ink-2">
          Last synced{' '}
          {catalog.last_synced_at ? (
            <time dateTime={catalog.last_synced_at} title={formatDateTime(catalog.last_synced_at, timeZone)}>
              {formatRelative(catalog.last_synced_at)}
            </time>
          ) : (
            'never'
          )}
        </p>
        <dl aria-label="Product counts" className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {counts.map((count) => (
            <div key={count.label} className="rounded-lg border border-line-2 bg-paper/50 px-3 py-2.5">
              <dt className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">{count.label}</dt>
              <dd className="font-display text-xl font-semibold text-ink">{formatNumber(count.value)}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="flex flex-col gap-3 border-t border-line-2 pt-4">
        <div>
          <h3 className="font-display text-base font-semibold text-ink">WhatsApp numbers</h3>
          <p className="text-[13px] text-muted">
            {canManage ? 'Choose where buyers see the catalog and cart.' : 'Only admins and owners can change these settings.'}
          </p>
        </div>
        {catalog.phone_numbers.length ? (
          catalog.phone_numbers.map((settings) => (
            <NumberSettings key={settings.phone_number_id} catalog={catalog} settings={settings} canManage={canManage} onError={setActionError} />
          ))
        ) : (
          <p className="text-[13px] text-muted">No numbers in this WhatsApp Business Account yet.</p>
        )}
      </div>

      <ConfirmDialog
        open={disconnectOpen}
        onOpenChange={setDisconnectOpen}
        danger
        loading={disconnecting}
        title="Disconnect the Meta catalog?"
        description="Your store falls back to chat menus. The catalog and its products stay in your Meta business, and your products stay here."
        confirmLabel="Disconnect"
        onConfirm={() => void disconnect()}
      />
    </section>
  )
}

type NumberSettingsProps = {
  catalog: MetaCatalog
  settings: CommerceSettings
  canManage: boolean
  onError: (error: unknown) => void
}

function NumberSettings({ catalog, settings, canManage, onError }: NumberSettingsProps) {
  const invalidate = useInvalidateCatalog()
  const { toast } = useToast()
  const [saving, setSaving] = useState<'is_cart_enabled' | 'is_catalog_visible' | null>(null)

  const update = async (field: 'is_cart_enabled' | 'is_catalog_visible', value: boolean) => {
    setSaving(field)
    onError(null)
    try {
      await unwrap(
        api.PATCH('/api/v1/catalog/meta-catalogs/{id}/commerce-settings/', {
          params: { path: { id: catalog.id } },
          body: { phone_number_id: settings.phone_number_id, [field]: value },
        }),
      )
      await invalidate()
      toast({ title: 'WhatsApp commerce settings saved', tone: 'success' })
    } catch (error) {
      onError(error)
    } finally {
      setSaving(null)
    }
  }

  return (
    <section aria-label={`Settings for ${settings.display_phone_number}`} className="flex flex-col gap-3 rounded-lg border border-line-2 p-4">
      <p className="font-mono text-[13px] text-ink">{settings.display_phone_number}</p>
      <Switch
        label="Shopping cart"
        description="Buyers can add products to a WhatsApp cart and send it to you as an order."
        checked={Boolean(settings.is_cart_enabled)}
        disabled={!canManage || saving !== null}
        onCheckedChange={(checked) => void update('is_cart_enabled', checked)}
      />
      <Switch
        label="Catalog visible"
        description="Show the catalog on your WhatsApp business profile and in chats."
        checked={Boolean(settings.is_catalog_visible)}
        disabled={!canManage || saving !== null}
        onCheckedChange={(checked) => void update('is_catalog_visible', checked)}
      />
    </section>
  )
}
