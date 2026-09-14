import { ArrowUpDown, FolderOpen, Pencil, Plus, Trash2, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { api, unwrap } from '../../../../api/client'
import { errorMessage } from '../../../../api/errors'
import { Button, EmptyState, StatusBadge, Switch, Table, useToast, type Column } from '../../../../components/app'
import { formatNumber } from '../../../../lib/format'
import { useWorkspace } from '../../../../lib/workspace'
import { useCollections, useInvalidateCatalog } from '../api'
import { CatalogLayout } from '../components/CatalogLayout'
import { CollectionFormDialog } from '../components/CollectionFormDialog'
import { ReorderDialog } from '../components/ReorderDialog'
import { ConfirmDialog } from '../components/shared'
import type { Collection } from '../lib/types'

export function CollectionsPage() {
  const { can } = useWorkspace()
  const canManage = can('admin')
  const collections = useCollections()
  const invalidate = useInvalidateCatalog()
  const { toast } = useToast()

  const [editing, setEditing] = useState<Collection | undefined>()
  const [formOpen, setFormOpen] = useState(false)
  const [reorderOpen, setReorderOpen] = useState(false)
  const [deleting, setDeleting] = useState<Collection | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [toggling, setToggling] = useState<string | null>(null)

  const openForm = (collection?: Collection) => {
    setEditing(collection)
    setFormOpen(true)
  }

  const setActive = async (collection: Collection, isActive: boolean) => {
    setToggling(collection.id)
    try {
      await unwrap(api.PATCH('/api/v1/catalog/collections/{id}/', { params: { path: { id: collection.id } }, body: { is_active: isActive } }))
      await invalidate()
    } catch (error) {
      toast({ title: "Couldn't update the collection", description: errorMessage(error), tone: 'error' })
    } finally {
      setToggling(null)
    }
  }

  const confirmDelete = async () => {
    if (!deleting) return
    setDeleteBusy(true)
    try {
      await unwrap(api.DELETE('/api/v1/catalog/collections/{id}/', { params: { path: { id: deleting.id } } }))
      await invalidate()
      toast({ title: `Deleted ${deleting.name}`, tone: 'success' })
      setDeleting(null)
    } catch (error) {
      toast({ title: "Couldn't delete the collection", description: errorMessage(error), tone: 'error' })
    } finally {
      setDeleteBusy(false)
    }
  }

  const columns: Column<Collection>[] = [
    {
      id: 'name',
      header: 'Collection',
      className: 'min-w-[14rem]',
      cell: (collection) => (
        <div className="min-w-0">
          <p className="font-medium text-ink">{collection.name}</p>
          {collection.description && <p className="text-[13px] text-muted">{collection.description}</p>}
        </div>
      ),
    },
    { id: 'count', header: 'Products', cell: (collection) => <span className="font-mono text-[13px] text-ink">{formatNumber(collection.product_count)}</span> },
    {
      id: 'active',
      header: 'Active',
      cell: (collection) =>
        canManage ? (
          <Switch
            hideLabel
            label={`Active: ${collection.name}`}
            checked={collection.is_active}
            disabled={toggling === collection.id}
            onCheckedChange={(checked) => void setActive(collection, checked)}
          />
        ) : (
          <StatusBadge tone={collection.is_active ? 'green' : 'neutral'}>{collection.is_active ? 'Active' : 'Inactive'}</StatusBadge>
        ),
    },
    ...(canManage
      ? [
          {
            id: 'actions',
            header: <span className="sr-only">Actions</span>,
            align: 'right',
            cell: (collection: Collection) => (
              <div className="flex justify-end gap-1">
                <Button variant="ghost" size="icon-sm" aria-label={`Edit ${collection.name}`} onClick={() => openForm(collection)}>
                  <Pencil className="size-4" aria-hidden="true" />
                </Button>
                <Button variant="ghost" size="icon-sm" aria-label={`Delete ${collection.name}`} onClick={() => setDeleting(collection)}>
                  <Trash2 className="size-4" aria-hidden="true" />
                </Button>
              </div>
            ),
          } satisfies Column<Collection>,
        ]
      : []),
  ]

  const actions = canManage && (
    <>
      <Button
        variant="secondary"
        icon={<ArrowUpDown className="size-4" aria-hidden="true" />}
        onClick={() => setReorderOpen(true)}
        disabled={(collections.data?.length ?? 0) < 2}
      >
        Reorder
      </Button>
      <Button icon={<Plus className="size-4" aria-hidden="true" />} onClick={() => openForm()}>
        New collection
      </Button>
    </>
  )

  const deletingCount = deleting?.product_count ?? 0

  return (
    <CatalogLayout tab="collections" actions={actions}>
      <p className="text-[13px] text-muted">
        Buyers pick a collection from a WhatsApp list, so names are limited to 24 characters and descriptions to 72.
      </p>
      {collections.isError ? (
        <EmptyState
          icon={<TriangleAlert />}
          title="Collections didn't load"
          description={errorMessage(collections.error)}
          action={
            <Button variant="secondary" onClick={() => void collections.refetch()}>
              Try again
            </Button>
          }
        />
      ) : (
        <Table
          caption="Collections"
          columns={columns}
          rows={collections.data ?? []}
          getRowId={(collection) => collection.id}
          loading={collections.isPending}
          empty={
            <EmptyState
              icon={<FolderOpen />}
              title="No collections yet"
              description="Group products into collections like Sweets or Gift boxes so buyers find them quickly."
              action={canManage && <Button onClick={() => openForm()}>New collection</Button>}
            />
          }
        />
      )}

      <CollectionFormDialog open={formOpen} onOpenChange={setFormOpen} collection={editing} />
      <ReorderDialog
        open={reorderOpen}
        onOpenChange={setReorderOpen}
        title="Reorder collections"
        description="Buyers see collections in this order in your WhatsApp store menu."
        loading={collections.isPending}
        items={collections.data?.map((collection) => ({ id: collection.id, label: collection.name }))}
        onSave={async (ids) => {
          await unwrap(api.POST('/api/v1/catalog/collections/reorder/', { body: { ids } }))
          await invalidate()
          toast({ title: 'Collection order saved', tone: 'success' })
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        danger
        loading={deleteBusy}
        title={`Delete ${deleting?.name ?? 'collection'}?`}
        description={
          deletingCount
            ? `Its ${formatNumber(deletingCount)} ${deletingCount === 1 ? 'product stays' : 'products stay'} in your catalog without a collection.`
            : 'No products are in this collection.'
        }
        confirmLabel="Delete collection"
        onConfirm={() => void confirmDelete()}
      />
    </CatalogLayout>
  )
}
