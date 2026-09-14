import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Trash2, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router'
import { api, unwrap } from '../../../../api/client'
import { ApiError, applyApiErrorToForm, errorMessage } from '../../../../api/errors'
import {
  Button,
  Checkbox,
  EmptyState,
  Field,
  Input,
  InteractiveMessagePreview,
  PageHeader,
  PageSpinner,
  Select,
  StatusBadge,
  Switch,
  Textarea,
  useToast,
} from '../../../../components/app'
import { parseRupeesToPaise } from '../../../../lib/money'
import { useWorkspace } from '../../../../lib/workspace'
import { catalogKeys, uploadProductImage, useCollections, useMetaCatalogs, useProduct } from '../api'
import { ImageField } from '../components/ImageField'
import { ReviewBadge } from '../components/ReviewBadge'
import { CharCount, ConfirmDialog, FormError, Note } from '../components/shared'
import { availabilityLabels, syncInfo } from '../lib/labels'
import { productCardMessage } from '../lib/preview'
import {
  DESCRIPTION_MAX,
  productDefaults,
  productFieldMap,
  productFormFields,
  productSchema,
  toProductBody,
  type ProductFormMode,
  type ProductFormValues,
} from '../lib/productForm'
import { availabilityValues, type Product } from '../lib/types'

export function ProductEditorPage() {
  const { productId } = useParams()
  const product = useProduct(productId)
  const { workspaceId } = useWorkspace()

  if (productId && product.isPending) return <PageSpinner label="Loading product" />
  if (productId && product.isError) {
    return (
      <EmptyState
        icon={<TriangleAlert />}
        title={product.error instanceof ApiError && product.error.status === 404 ? 'Product not found' : "This product didn't load"}
        description={errorMessage(product.error)}
        action={
          <Link to={`/app/w/${workspaceId}/catalog`} className="text-sm font-medium text-accent-2 underline-offset-2 hover:underline">
            Back to catalog
          </Link>
        }
      />
    )
  }
  return <ProductEditor key={product.data?.id ?? 'new'} product={product.data} />
}

function objectUrl(file: File): string | null {
  return typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : null
}

function ProductEditor({ product }: { product: Product | undefined }) {
  const mode: ProductFormMode = product ? 'edit' : 'create'
  const { workspaceId, can } = useWorkspace()
  const canManage = can('admin')
  const base = `/app/w/${workspaceId}/catalog`
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const collections = useCollections()
  const metaCatalogs = useMetaCatalogs()
  const catalogConnected = Boolean(metaCatalogs.data?.length)

  const {
    control,
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<ProductFormValues>({ resolver: zodResolver(productSchema(mode)), defaultValues: productDefaults(product) })
  const [name, price, salePrice, description, trackStock] = useWatch({ control, name: ['name', 'price', 'salePrice', 'description', 'trackStock'] })

  // Photo: uploaded right away when editing; kept until the product exists when creating.
  const [pending, setPending] = useState<{ file: File; url: string | null } | null>(null)
  const [uploading, setUploading] = useState(false)
  const [imageError, setImageError] = useState<string>()
  const pendingUrl = useRef<string | null>(null)
  useEffect(() => () => {
    if (pendingUrl.current) URL.revokeObjectURL?.(pendingUrl.current)
  }, [])

  const setPendingFile = (file: File | null) => {
    if (pendingUrl.current) URL.revokeObjectURL?.(pendingUrl.current)
    const url = file ? objectUrl(file) : null
    pendingUrl.current = url
    setPending(file ? { file, url } : null)
  }

  const storeProduct = (saved: Product) => {
    queryClient.setQueryData(catalogKeys.detail(workspaceId, saved.id), saved)
    void queryClient.invalidateQueries({ queryKey: catalogKeys.lists(workspaceId) })
    void queryClient.invalidateQueries({ queryKey: catalogKeys.custom(workspaceId, 'meta-catalogs') })
    void queryClient.invalidateQueries({ queryKey: catalogKeys.custom(workspaceId, 'collections') })
  }

  const uploadError = (error: unknown) => (error instanceof ApiError ? (error.fieldErrors.file ?? errorMessage(error)) : errorMessage(error))

  const onImageFile = async (file: File) => {
    setImageError(undefined)
    if (!product) {
      setPendingFile(file)
      return
    }
    setUploading(true)
    try {
      storeProduct(await uploadProductImage(product.id, file))
      toast({ title: 'Photo uploaded', tone: 'success' })
    } catch (error) {
      setImageError(uploadError(error))
    } finally {
      setUploading(false)
    }
  }

  const onImageRemove = async () => {
    setImageError(undefined)
    if (!product) {
      setPendingFile(null)
      return
    }
    setUploading(true)
    try {
      // The schema answers 204; refetch the product rather than relying on a body.
      await unwrap(api.DELETE('/api/v1/catalog/products/{id}/image/', { params: { path: { id: product.id } } }))
      storeProduct(await unwrap(api.GET('/api/v1/catalog/products/{id}/', { params: { path: { id: product.id } } })))
      toast({ title: 'Photo removed', tone: 'success' })
    } catch (error) {
      setImageError(uploadError(error))
    } finally {
      setUploading(false)
    }
  }

  const onSubmit = handleSubmit(async (values) => {
    const body = toProductBody(values, mode)
    try {
      if (product) {
        const saved = await unwrap(api.PATCH('/api/v1/catalog/products/{id}/', { params: { path: { id: product.id } }, body }))
        storeProduct(saved)
        reset(productDefaults(saved))
        toast({ title: 'Product saved', tone: 'success' })
        return
      }
      let saved = await unwrap(api.POST('/api/v1/catalog/products/', { body }))
      if (pending) {
        try {
          saved = await uploadProductImage(saved.id, pending.file)
        } catch (error) {
          toast({ title: "Product added, but the photo didn't upload", description: uploadError(error), tone: 'error' })
        }
      }
      storeProduct(saved)
      toast({ title: 'Product added', tone: 'success' })
      navigate(`${base}/products/${saved.id}`, { replace: true })
    } catch (error) {
      applyApiErrorToForm(error, setError, { fieldMap: productFieldMap, fields: productFormFields })
    }
  })

  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const deleteProduct = async () => {
    if (!product) return
    setDeleting(true)
    try {
      await unwrap(api.DELETE('/api/v1/catalog/products/{id}/', { params: { path: { id: product.id } } }))
      queryClient.removeQueries({ queryKey: catalogKeys.detail(workspaceId, product.id) })
      void queryClient.invalidateQueries({ queryKey: catalogKeys.all(workspaceId) })
      toast({ title: `Deleted ${product.name}`, tone: 'success' })
      navigate(base, { replace: true })
    } catch (error) {
      toast({ title: "Couldn't delete the product", description: errorMessage(error), tone: 'error' })
      setDeleting(false)
      setDeleteOpen(false)
    }
  }

  const imageUrl = pending ? pending.url : (product?.image_url ?? null)
  const preview = productCardMessage({
    productId: product?.id ?? null,
    name,
    pricePaise: parseRupeesToPaise(price),
    salePricePaise: salePrice ? parseRupeesToPaise(salePrice) : null,
    description,
    imageUrl,
  })

  return (
    <div className="flex flex-col gap-6">
      <Link to={base} className="inline-flex w-fit items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden="true" />
        Catalog
      </Link>
      <PageHeader
        eyebrow={product ? <span className="normal-case tracking-normal">SKU {product.sku}</span> : 'Catalog'}
        title={product ? product.name : 'Add product'}
        description={product ? undefined : 'Prices are in rupees and include GST. Buyers see this card when they open the product in your WhatsApp store.'}
        actions={
          product &&
          canManage && (
            <Button variant="secondary" icon={<Trash2 className="size-4" aria-hidden="true" />} onClick={() => setDeleteOpen(true)}>
              Delete
            </Button>
          )
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <form onSubmit={onSubmit} noValidate className="flex min-w-0 flex-col gap-5">
          {!canManage && <Note>You can view products. Only admins and owners can change them.</Note>}
          <FormError message={errors.root?.server?.message} />

          <fieldset disabled={!canManage} className="flex min-w-0 flex-col gap-5">
            <section aria-labelledby="product-details" className="flex flex-col gap-4 rounded-xl border border-line bg-card p-5">
              <h2 id="product-details" className="font-display text-base font-semibold text-ink">
                Details
              </h2>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Name" required error={errors.name?.message}>
                  <Input placeholder="Kaju katli 500 g" {...register('name')} />
                </Field>
                {product ? (
                  <Field label="SKU" hint="The SKU can't change after the product is created.">
                    <Input value={product.sku} readOnly className="font-mono" />
                  </Field>
                ) : (
                  <Field label="SKU" required error={errors.sku?.message} hint="Your code for this product, also its ID in Meta's catalog.">
                    <Input placeholder="KAJU-KATLI-500" className="font-mono" autoCapitalize="characters" {...register('sku')} />
                  </Field>
                )}
              </div>
              <Field
                label="Description"
                error={errors.description?.message}
                hint={
                  <span className="flex justify-between gap-3">
                    <span>Shown on the product card.</span>
                    <CharCount value={description} max={DESCRIPTION_MAX} />
                  </span>
                }
              >
                <Textarea rows={3} {...register('description')} />
              </Field>
              <ImageField imageUrl={imageUrl} busy={uploading} error={imageError} disabled={!canManage} onFile={(file) => void onImageFile(file)} onRemove={() => void onImageRemove()} />
            </section>

            <section aria-labelledby="product-pricing" className="flex flex-col gap-4 rounded-xl border border-line bg-card p-5">
              <h2 id="product-pricing" className="font-display text-base font-semibold text-ink">
                Price and stock
              </h2>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Price (₹)" required error={errors.price?.message} hint="Including GST.">
                  <Input inputMode="decimal" prefix="₹" placeholder="649" {...register('price')} />
                </Field>
                <Field label="Sale price (₹)" error={errors.salePrice?.message} hint="Optional. Buyers see the price struck through.">
                  <Input inputMode="decimal" prefix="₹" placeholder="599" {...register('salePrice')} />
                </Field>
                <Field label="Availability" error={errors.availability?.message}>
                  <Select options={availabilityValues.map((value) => ({ value, label: availabilityLabels[value] }))} {...register('availability')} />
                </Field>
                <Field label="Max quantity per order" error={errors.maxQty?.message} hint="1 to 99.">
                  <Input inputMode="numeric" {...register('maxQty')} />
                </Field>
              </div>
              <Checkbox label="Track stock" description="Buyers see the product as out of stock when the count reaches 0." {...register('trackStock')} />
              {trackStock && (
                <Field label="Stock quantity" required error={errors.stockQty?.message} className="sm:max-w-[calc(50%-0.5rem)]">
                  <Input inputMode="numeric" {...register('stockQty')} />
                </Field>
              )}
            </section>

            <section aria-labelledby="product-organise" className="flex flex-col gap-4 rounded-xl border border-line bg-card p-5">
              <h2 id="product-organise" className="font-display text-base font-semibold text-ink">
                Store
              </h2>
              <Field label="Collection" error={errors.collectionId?.message}>
                <Select {...register('collectionId')}>
                  <option value="">No collection</option>
                  {(collections.data ?? []).map((collection) => (
                    <option key={collection.id} value={collection.id}>
                      {collection.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Controller
                control={control}
                name="isActive"
                render={({ field }) => (
                  <Switch
                    label="Active"
                    description="Inactive products are hidden from buyers."
                    checked={field.value}
                    onCheckedChange={field.onChange}
                    disabled={!canManage}
                  />
                )}
              />
            </section>
          </fieldset>

          {canManage && (
            <div className="flex flex-wrap justify-end gap-2">
              <Link to={base} className="inline-flex h-10 items-center rounded-md border border-line bg-card px-4 text-sm font-medium text-ink hover:border-ink/40">
                Cancel
              </Link>
              <Button type="submit" loading={isSubmitting} disabled={Boolean(product) && !isDirty}>
                {product ? 'Save product' : 'Add product'}
              </Button>
            </div>
          )}
        </form>

        <aside aria-label="WhatsApp preview" className="flex flex-col gap-4 lg:sticky lg:top-4 lg:self-start">
          <div className="flex flex-col gap-2">
            <h2 className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">Product card in WhatsApp</h2>
            <InteractiveMessagePreview message={preview} time="10:42" />
            {!imageUrl && <p className="text-[12.5px] text-muted">Add a photo to show it at the top of the card.</p>}
          </div>
          {product && catalogConnected && <MetaStatusCard product={product} />}
        </aside>
      </div>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        danger
        loading={deleting}
        title={`Delete ${product?.name ?? 'product'}?`}
        description="Buyers can't order it any more. Past orders keep their item names and prices. If a Meta catalog is connected, the product is removed from it too."
        confirmLabel="Delete product"
        onConfirm={() => void deleteProduct()}
      />
    </div>
  )
}

function MetaStatusCard({ product }: { product: Product }) {
  const sync = syncInfo[product.meta_sync_status]
  return (
    <section aria-labelledby="meta-status" className="flex flex-col gap-3 rounded-xl border border-line bg-card p-4">
      <h2 id="meta-status" className="font-display text-sm font-semibold text-ink">
        Meta catalog
      </h2>
      <dl className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2 text-[13px]">
        <dt className="text-muted">Sync</dt>
        <dd>
          <StatusBadge tone={sync.tone}>{sync.label}</StatusBadge>
        </dd>
        <dt className="text-muted">Review</dt>
        <dd>
          <ReviewBadge product={product} />
        </dd>
      </dl>
      {!product.image_url && <p className="text-[12.5px] text-muted">Add a photo to sync this product. Meta needs a public image.</p>}
      {product.meta_review_status === 'rejected' && product.meta_rejection_reasons.length > 0 && (
        <div className="rounded-lg border border-signal/20 bg-signal-soft/40 px-3 py-2">
          <p className="text-[13px] font-medium text-signal">Why Meta rejected it</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[13px] text-ink-2">
            {product.meta_rejection_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
