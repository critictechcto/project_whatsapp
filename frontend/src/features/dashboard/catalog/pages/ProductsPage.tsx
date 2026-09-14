import { useQueryClient } from '@tanstack/react-query'
import { ArrowUpDown, Package, Plus, Search, TriangleAlert, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { api, unwrap } from '../../../../api/client'
import { errorMessage } from '../../../../api/errors'
import {
  Button,
  buttonClasses,
  EmptyState,
  Field,
  Input,
  Select,
  StatusBadge,
  Switch,
  Table,
  useToast,
  type Column,
} from '../../../../components/app'
import { formatPaise } from '../../../../lib/money'
import { useWorkspace } from '../../../../lib/workspace'
import { catalogKeys, useAllProducts, useCollections, useInvalidateCatalog, useMetaCatalogs, useProducts, type ProductFilters } from '../api'
import { CatalogLayout } from '../components/CatalogLayout'
import { ImportDialog } from '../components/ImportDialog'
import { ReorderDialog } from '../components/ReorderDialog'
import { ReviewBadge } from '../components/ReviewBadge'
import { availabilityLabels, reviewInfo } from '../lib/labels'
import { availabilityValues, reviewValues, type Product, type ProductAvailability, type MetaReviewStatus } from '../lib/types'
import { useDebouncedValue } from '../lib/useDebouncedValue'

const isAvailability = (value: string): value is ProductAvailability => (availabilityValues as readonly string[]).includes(value)
const isReview = (value: string): value is MetaReviewStatus => (reviewValues as readonly string[]).includes(value)

export function ProductsPage() {
  const { workspaceId, can } = useWorkspace()
  const canManage = can('admin')
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const collection = params.get('collection') ?? ''
  const active = params.get('active') ?? ''
  const rawAvailability = params.get('availability') ?? ''
  const rawReview = params.get('review') ?? ''

  const metaCatalogs = useMetaCatalogs()
  const catalogConnected = Boolean(metaCatalogs.data?.length)
  const collections = useCollections()

  const filters: ProductFilters = {
    search: q || undefined,
    collection: collection || undefined,
    isActive: active === 'true' ? true : active === 'false' ? false : undefined,
    availability: isAvailability(rawAvailability) ? rawAvailability : undefined,
    review: catalogConnected && isReview(rawReview) ? rawReview : undefined,
  }
  const hasFilters = Boolean(filters.search || filters.collection || filters.isActive !== undefined || filters.availability || filters.review)
  const products = useProducts(filters)

  const [searchText, setSearchText] = useState(q)
  const debouncedSearch = useDebouncedValue(searchText.trim(), 300)
  const updateParam = (key: string, value: string) =>
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous)
        if (value) next.set(key, value)
        else next.delete(key)
        return next
      },
      { replace: true },
    )

  useEffect(() => {
    if (debouncedSearch !== q) updateParam('q', debouncedSearch)
    // Only the debounced text drives the URL; `q` changes as a result.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch])

  const clearFilters = () => {
    setSearchText('')
    setParams(new URLSearchParams(), { replace: true })
  }

  const [importOpen, setImportOpen] = useState(false)
  const [reorderOpen, setReorderOpen] = useState(false)
  const allProducts = useAllProducts(reorderOpen)
  const invalidate = useInvalidateCatalog()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [toggling, setToggling] = useState<ReadonlySet<string>>(new Set())

  const setActive = async (product: Product, isActive: boolean) => {
    setToggling((current) => new Set(current).add(product.id))
    try {
      await unwrap(api.PATCH('/api/v1/catalog/products/{id}/', { params: { path: { id: product.id } }, body: { is_active: isActive } }))
      await queryClient.invalidateQueries({ queryKey: catalogKeys.all(workspaceId) })
      toast({ title: `${product.name} ${isActive ? 'is active' : 'is hidden from buyers'}`, tone: 'success' })
    } catch (error) {
      toast({ title: "Couldn't update the product", description: errorMessage(error), tone: 'error' })
    } finally {
      setToggling((current) => {
        const next = new Set(current)
        next.delete(product.id)
        return next
      })
    }
  }

  const columns: Column<Product>[] = [
    {
      id: 'product',
      header: 'Product',
      className: 'min-w-[16rem]',
      cell: (product) => (
        <div className="flex items-center gap-3">
          <div className="size-11 shrink-0 overflow-hidden rounded-md border border-line-2 bg-paper-2">
            {product.image_url ? (
              <img src={product.image_url} alt="" className="size-full object-cover" />
            ) : (
              <div className="grid size-full place-items-center text-muted" aria-hidden="true">
                <Package className="size-4" />
              </div>
            )}
          </div>
          <div className="min-w-0">
            <Link to={`/app/w/${workspaceId}/catalog/products/${product.id}`} className="font-medium text-ink underline-offset-2 hover:underline">
              {product.name}
            </Link>
            <p className="font-mono text-[12px] text-muted">{product.sku}</p>
          </div>
        </div>
      ),
    },
    { id: 'price', header: 'Price', cell: (product) => <PriceCell product={product} /> },
    {
      id: 'stock',
      header: 'Stock',
      hideOnMobile: true,
      cell: (product) =>
        product.stock_qty === null ? <span className="text-muted">Not tracked</span> : <span className="font-mono text-[13px] text-ink">{product.stock_qty}</span>,
    },
    {
      id: 'availability',
      header: 'Availability',
      hideOnMobile: true,
      cell: (product) => {
        const soldOut = product.availability === 'out_of_stock' || product.stock_qty === 0
        return <StatusBadge tone={soldOut ? 'amber' : 'green'}>{soldOut ? availabilityLabels.out_of_stock : availabilityLabels.in_stock}</StatusBadge>
      },
    },
    {
      id: 'active',
      header: 'Active',
      cell: (product) =>
        canManage ? (
          <Switch
            hideLabel
            label={`Active: ${product.name}`}
            checked={product.is_active}
            disabled={toggling.has(product.id)}
            onCheckedChange={(checked) => void setActive(product, checked)}
          />
        ) : (
          <StatusBadge tone={product.is_active ? 'green' : 'neutral'}>{product.is_active ? 'Active' : 'Inactive'}</StatusBadge>
        ),
    },
    {
      id: 'collection',
      header: 'Collection',
      hideOnMobile: true,
      cell: (product) => (product.collection ? <span className="text-ink-2">{product.collection.name}</span> : <span className="text-muted">—</span>),
    },
    ...(catalogConnected
      ? [{ id: 'review', header: 'Meta review', hideOnMobile: true, cell: (product: Product) => <ReviewBadge product={product} /> } satisfies Column<Product>]
      : []),
  ]

  const actions = canManage && (
    <>
      <Button variant="secondary" icon={<Upload className="size-4" aria-hidden="true" />} onClick={() => setImportOpen(true)}>
        Import CSV
      </Button>
      <Button variant="secondary" icon={<ArrowUpDown className="size-4" aria-hidden="true" />} onClick={() => setReorderOpen(true)}>
        Reorder
      </Button>
      <Link to={`/app/w/${workspaceId}/catalog/products/new`} className={buttonClasses('primary')}>
        <Plus className="size-4" aria-hidden="true" />
        Add product
      </Link>
    </>
  )

  return (
    <CatalogLayout tab="products" actions={actions}>
      <section aria-label="Filters" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.4fr)_repeat(4,minmax(0,1fr))]">
        <Field label="Search products" hideLabel>
          <Input
            type="search"
            prefix={<Search className="size-4" aria-hidden="true" />}
            placeholder="Search name or SKU"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
          />
        </Field>
        <Field label="Collection" hideLabel>
          <Select value={collection} onChange={(event) => updateParam('collection', event.target.value)}>
            <option value="">All collections</option>
            <option value="none">No collection</option>
            {(collections.data ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Active" hideLabel>
          <Select
            value={active}
            onChange={(event) => updateParam('active', event.target.value)}
            placeholder="Active and inactive"
            options={[
              { value: 'true', label: 'Active only' },
              { value: 'false', label: 'Inactive only' },
            ]}
          />
        </Field>
        <Field label="Availability" hideLabel>
          <Select
            value={filters.availability ?? ''}
            onChange={(event) => updateParam('availability', event.target.value)}
            placeholder="Any availability"
            options={availabilityValues.map((value) => ({ value, label: availabilityLabels[value] }))}
          />
        </Field>
        {catalogConnected && (
          <Field label="Meta review" hideLabel>
            <Select
              value={filters.review ?? ''}
              onChange={(event) => updateParam('review', event.target.value)}
              placeholder="Any review status"
              options={reviewValues.map((value) => ({ value, label: reviewInfo[value].label }))}
            />
          </Field>
        )}
      </section>

      {products.isError ? (
        <EmptyState
          icon={<TriangleAlert />}
          title="Products didn't load"
          description={errorMessage(products.error)}
          action={
            <Button variant="secondary" onClick={() => void products.refetch()}>
              Try again
            </Button>
          }
        />
      ) : (
        <Table
          caption="Products"
          columns={columns}
          rows={products.items}
          getRowId={(product) => product.id}
          loading={products.isPending}
          hasNextPage={products.hasNextPage}
          isFetchingNextPage={products.isFetchingNextPage}
          onLoadMore={() => void products.fetchNextPage()}
          empty={
            hasFilters ? (
              <EmptyState
                icon={<Search />}
                title="No products match these filters"
                action={
                  <Button variant="secondary" onClick={clearFilters}>
                    Clear filters
                  </Button>
                }
              />
            ) : (
              <EmptyState
                icon={<Package />}
                title="No products yet"
                description={
                  canManage
                    ? 'Add products with a name, price and photo, or import them from a spreadsheet. Prices are in rupees and include GST.'
                    : 'An admin can add products or import them from a spreadsheet.'
                }
                action={
                  canManage && (
                    <div className="flex flex-wrap justify-center gap-2">
                      <Button variant="secondary" onClick={() => setImportOpen(true)}>
                        Import CSV
                      </Button>
                      <Link to={`/app/w/${workspaceId}/catalog/products/new`} className={buttonClasses('primary')}>
                        Add product
                      </Link>
                    </div>
                  )
                }
              />
            )
          }
        />
      )}

      <ImportDialog open={importOpen} onOpenChange={setImportOpen} />
      <ReorderDialog
        open={reorderOpen}
        onOpenChange={setReorderOpen}
        title="Reorder products"
        description="Buyers see products in this order in your WhatsApp store."
        loading={allProducts.isPending}
        items={allProducts.data?.map((product) => ({ id: product.id, label: product.name, detail: product.sku }))}
        onSave={async (ids) => {
          await unwrap(api.POST('/api/v1/catalog/products/reorder/', { body: { ids } }))
          await invalidate()
          toast({ title: 'Product order saved', tone: 'success' })
        }}
      />
    </CatalogLayout>
  )
}

function PriceCell({ product }: { product: Product }) {
  const onSale = product.sale_price_paise !== null && product.sale_price_paise < product.price_paise
  if (!onSale) return <span className="whitespace-nowrap text-ink">{formatPaise(product.price_paise)}</span>
  return (
    <span className="flex flex-col whitespace-nowrap leading-tight">
      <span className="text-ink">
        <span className="sr-only">Sale price </span>
        {formatPaise(product.sale_price_paise ?? 0)}
      </span>
      <s className="text-[12.5px] text-muted">
        <span className="sr-only">Regular price </span>
        {formatPaise(product.price_paise)}
      </s>
    </span>
  )
}
