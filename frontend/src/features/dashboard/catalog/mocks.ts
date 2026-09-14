import type { Schemas } from '../../../api/types'
import { mockRealtime } from '../../../mocks/realtime'
import { ids, seedPhoneNumber, seedWaba } from '../../../mocks/seed'
import { authorize, errorResponse, http, mockDelay, notFound, nowIso, paginate, uuid, validationError } from '../../../mocks/utils'
import { parseRupeesToPaise } from '../../../lib/money'
import type { AreaMockHandlers } from '../registry/types'
import { MAX_IMPORT_BYTES, MAX_IMPORT_ROWS, parseCsv } from './lib/csv'
import { IMAGE_TYPES, MAX_IMAGE_BYTES } from './lib/image'
import { DESCRIPTION_MAX, MAX_QTY_LIMIT, MIN_PRICE_PAISE, NAME_MAX, SKU_RE } from './lib/productForm'
import { catalogMock, mockProductImage, type MockCollection, type MockMetaCatalog, type MockProduct } from './mockState'

const COLLECTION_NAME_MAX = 24
const COLLECTION_DESCRIPTION_MAX = 72
const SYNC_DELAY_MS = 1500

type ProductBody = Partial<Schemas['ProductWriteRequest']>
type CollectionBody = Partial<Schemas['CollectionWriteRequest']>

const byPosition = <T extends { position: number; name: string }>(items: T[]) =>
  [...items].sort((a, b) => a.position - b.position || a.name.localeCompare(b.name))

const productsOf = (workspaceId: string) => catalogMock().products.filter((p) => p.workspace_id === workspaceId)
const collectionsOf = (workspaceId: string) => catalogMock().collections.filter((c) => c.workspace_id === workspaceId)
const catalogsOf = (workspaceId: string) => catalogMock().metaCatalogs.filter((m) => m.workspace_id === workspaceId)

function toProduct({ workspace_id: _ws, collection_id, ...product }: MockProduct): Schemas['Product'] {
  const collection = collection_id ? catalogMock().collections.find((c) => c.id === collection_id) : undefined
  return {
    ...product,
    meta_rejection_reasons: [...product.meta_rejection_reasons],
    collection: collection ? { id: collection.id, name: collection.name } : null,
    effective_price_paise: product.sale_price_paise ?? product.price_paise,
  }
}

function toCollection({ workspace_id, ...collection }: MockCollection): Schemas['Collection'] {
  const product_count = productsOf(workspace_id).filter((p) => p.collection_id === collection.id).length
  return { ...collection, product_count }
}

function toMetaCatalog({ workspace_id, ...catalog }: MockMetaCatalog): Schemas['MetaCatalog'] {
  const products = productsOf(workspace_id)
  const count = (predicate: (p: MockProduct) => boolean) => products.filter(predicate).length
  return {
    ...catalog,
    waba: { ...catalog.waba },
    phone_numbers: catalog.phone_numbers.map((settings) => ({ ...settings })),
    product_counts: {
      synced: count((p) => p.meta_sync_status === 'synced'),
      pending: count((p) => p.meta_sync_status === 'pending'),
      failed: count((p) => p.meta_sync_status === 'failed'),
      approved: count((p) => p.meta_review_status === 'approved'),
      rejected: count((p) => p.meta_review_status === 'rejected'),
    },
  }
}

const permissionsMissing = () =>
  errorResponse(
    409,
    'catalog_permissions_missing',
    'Your WhatsApp connection is missing the catalog_management and business_management permissions. Reconnect WhatsApp and allow catalog access.',
    { reconnect_url: null },
  )

/** Marks a changed product for the next sync when a catalog is connected (products need a public image). */
function queueSync(product: MockProduct) {
  if (!catalogsOf(product.workspace_id).length) return
  product.meta_sync_status = product.image_url ? 'pending' : 'not_synced'
  if (product.image_url && product.meta_review_status !== 'none') product.meta_review_status = 'outdated'
}

function validateProduct(workspaceId: string, body: ProductBody, existing?: MockProduct) {
  const errors: Record<string, string[]> = {}
  if (!existing) {
    const sku = String(body.sku ?? '')
    if (!sku) errors.sku = ['This field is required.']
    else if (!SKU_RE.test(sku)) errors.sku = ['Use letters, numbers, hyphens and underscores only.']
    else if (productsOf(workspaceId).some((p) => p.sku === sku)) errors.sku = ['A product with this SKU already exists.']
  }
  if (!existing || body.name !== undefined) {
    const name = String(body.name ?? '').trim()
    if (!name) errors.name = ['This field is required.']
    else if (name.length > NAME_MAX) errors.name = [`Ensure this field has no more than ${NAME_MAX} characters.`]
  }
  if (body.description && body.description.length > DESCRIPTION_MAX) errors.description = [`Ensure this field has no more than ${DESCRIPTION_MAX} characters.`]
  const price = body.price_paise ?? existing?.price_paise
  if (!existing || body.price_paise !== undefined) {
    if (!Number.isInteger(body.price_paise)) errors.price_paise = ['A valid integer is required.']
    else if ((body.price_paise ?? 0) < MIN_PRICE_PAISE) errors.price_paise = ['Ensure this value is greater than or equal to 100.']
  }
  const sale = body.sale_price_paise !== undefined ? body.sale_price_paise : existing?.sale_price_paise
  if (sale != null && price != null && sale >= price) errors.sale_price_paise = ['The sale price must be lower than the price.']
  if (body.collection_id && !collectionsOf(workspaceId).some((c) => c.id === body.collection_id)) {
    errors.collection_id = [`Invalid pk "${body.collection_id}" - object does not exist.`]
  }
  if (body.stock_qty != null && (!Number.isInteger(body.stock_qty) || body.stock_qty < 0)) errors.stock_qty = ['Ensure this value is greater than or equal to 0.']
  if (body.max_qty_per_order !== undefined && (!Number.isInteger(body.max_qty_per_order) || body.max_qty_per_order < 1 || body.max_qty_per_order > MAX_QTY_LIMIT)) {
    errors.max_qty_per_order = [`Ensure this value is between 1 and ${MAX_QTY_LIMIT}.`]
  }
  return Object.keys(errors).length ? validationError(errors) : null
}

function applyProduct(product: MockProduct, body: ProductBody) {
  if (body.name !== undefined) product.name = body.name.trim()
  if (body.description !== undefined) product.description = body.description
  if (body.price_paise !== undefined) product.price_paise = body.price_paise
  if (body.sale_price_paise !== undefined) product.sale_price_paise = body.sale_price_paise
  if (body.collection_id !== undefined) product.collection_id = body.collection_id
  if (body.availability !== undefined) product.availability = body.availability
  if (body.stock_qty !== undefined) product.stock_qty = body.stock_qty
  if (body.max_qty_per_order !== undefined) product.max_qty_per_order = body.max_qty_per_order
  if (body.position !== undefined) product.position = body.position
  if (body.is_active !== undefined) product.is_active = body.is_active
  product.updated_at = nowIso()
}

function validateCollection(body: CollectionBody, existing?: MockCollection) {
  const errors: Record<string, string[]> = {}
  if (!existing || body.name !== undefined) {
    const name = String(body.name ?? '').trim()
    if (!name) errors.name = ['This field is required.']
    else if (name.length > COLLECTION_NAME_MAX) errors.name = [`Ensure this field has no more than ${COLLECTION_NAME_MAX} characters.`]
  }
  if (body.description && body.description.length > COLLECTION_DESCRIPTION_MAX) {
    errors.description = [`Ensure this field has no more than ${COLLECTION_DESCRIPTION_MAX} characters.`]
  }
  return Object.keys(errors).length ? validationError(errors) : null
}

/** Checks a full ordering and rewrites positions 0..n. Returns an error response or null. */
function reorder<T extends { id: string; position: number }>(items: T[], ids: unknown) {
  if (!Array.isArray(ids) || ids.length !== items.length || new Set(ids).size !== ids.length || !items.every((item) => ids.includes(item.id))) {
    return validationError({ ids: ['Send every id exactly once.'] })
  }
  ids.forEach((id, position) => {
    const item = items.find((candidate) => candidate.id === id)
    if (item) item.position = position
  })
  return null
}

async function readFile(request: Request): Promise<File | null> {
  try {
    const form = await request.formData()
    const file = form.get('file')
    return file && typeof file !== 'string' ? (file as File) : null
  } catch {
    return null
  }
}

const TRUE_VALUES = new Set(['true', '1', 'yes'])
const FALSE_VALUES = new Set(['false', '0', 'no'])

/** Applies an uploaded CSV like the backend import: create or update by SKU, collections by name. */
function importCsv(workspaceId: string, text: string): Schemas['ProductImportResult'] | { error: string } {
  const rows = parseCsv(text)
  if (!rows.length) return { error: 'The file is empty.' }
  const header = rows[0].map((cell) => cell.trim().toLowerCase())
  if (!header.includes('sku')) return { error: 'The file needs a sku column.' }
  if (rows.length - 1 > MAX_IMPORT_ROWS) return { error: `Import at most ${MAX_IMPORT_ROWS.toLocaleString('en-IN')} rows at a time.` }

  const result = { created_count: 0, updated_count: 0, skipped_count: 0, errors: [] as Schemas['ProductImportRowError'][] }
  const state = catalogMock()
  rows.slice(1).forEach((cells, index) => {
    const row = index + 2
    const value = (column: string) => {
      const i = header.indexOf(column)
      return i >= 0 && i < cells.length ? cells[i].trim() : ''
    }
    const sku = value('sku')
    const skip = (reason: string) => {
      result.skipped_count += 1
      result.errors.push({ row, sku, reason })
    }
    if (!sku || !SKU_RE.test(sku)) return skip(sku ? 'The SKU can only use letters, numbers, - and _.' : 'The sku is empty.')
    const existing = productsOf(workspaceId).find((p) => p.sku === sku)

    const body: ProductBody = {}
    if (value('name')) body.name = value('name')
    if (value('description')) body.description = value('description')
    if (value('price')) {
      const paise = parseRupeesToPaise(value('price'))
      if (paise === null) return skip(`"${value('price')}" is not a price in rupees.`)
      body.price_paise = paise
    }
    if (header.includes('sale_price')) {
      if (value('sale_price')) {
        const paise = parseRupeesToPaise(value('sale_price'))
        if (paise === null) return skip(`"${value('sale_price')}" is not a price in rupees.`)
        body.sale_price_paise = paise
      } else body.sale_price_paise = null
    }
    if (value('stock_qty')) {
      if (!/^\d+$/.test(value('stock_qty'))) return skip('stock_qty must be a whole number.')
      body.stock_qty = Number(value('stock_qty'))
    } else if (header.includes('stock_qty')) body.stock_qty = null
    if (value('max_qty_per_order')) body.max_qty_per_order = Number(value('max_qty_per_order'))
    if (value('availability')) {
      if (value('availability') !== 'in_stock' && value('availability') !== 'out_of_stock') return skip('availability must be in_stock or out_of_stock.')
      body.availability = value('availability') as Schemas['ProductAvailabilityEnum']
    }
    if (value('is_active')) {
      const flag = value('is_active').toLowerCase()
      if (!TRUE_VALUES.has(flag) && !FALSE_VALUES.has(flag)) return skip('is_active must be true or false.')
      body.is_active = TRUE_VALUES.has(flag)
    }
    if (!existing && (!body.name || body.price_paise === undefined)) return skip('New products need a name and a price.')

    const invalid = validateProduct(workspaceId, existing ? body : { ...body, sku }, existing)
    if (invalid) return skip('The row has invalid values. Check the price, sale price and quantities.')

    const collectionName = value('collection')
    if (collectionName) {
      let collection = collectionsOf(workspaceId).find((c) => c.name.toLowerCase() === collectionName.toLowerCase())
      if (!collection) {
        if (collectionName.length > COLLECTION_NAME_MAX) return skip(`Collection names can be at most ${COLLECTION_NAME_MAX} characters.`)
        const now = nowIso()
        collection = { id: uuid(), workspace_id: workspaceId, name: collectionName, description: '', position: collectionsOf(workspaceId).length, is_active: true, created_at: now, updated_at: now }
        state.collections.push(collection)
      }
      body.collection_id = collection.id
    }

    if (existing) {
      applyProduct(existing, body)
      queueSync(existing)
      result.updated_count += 1
    } else {
      const product = newProduct(workspaceId, { ...body, sku })
      state.products.push(product)
      result.created_count += 1
    }
  })
  return result
}

function newProduct(workspaceId: string, body: ProductBody): MockProduct {
  const now = nowIso()
  const products = productsOf(workspaceId)
  const product: MockProduct = {
    id: uuid(),
    workspace_id: workspaceId,
    sku: String(body.sku),
    name: '',
    description: '',
    price_paise: 0,
    sale_price_paise: null,
    currency: 'INR',
    image_url: null,
    collection_id: null,
    availability: 'in_stock',
    stock_qty: null,
    max_qty_per_order: 10,
    position: products.length ? Math.max(...products.map((p) => p.position)) + 1 : 0,
    is_active: true,
    meta_sync_status: 'not_synced',
    meta_review_status: 'none',
    meta_rejection_reasons: [],
    created_at: now,
    updated_at: now,
  }
  applyProduct(product, body)
  return product
}

export const handlers: AreaMockHandlers = [
  // Products
  http.get('/api/v1/catalog/products/', async ({ request, query, response }) => {
    await mockDelay(200)
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const search = (query.get('search') ?? '').trim().toLowerCase()
    const collection = query.get('collection')
    const active = query.get('is_active')
    const availability = query.get('availability')
    const review = query.get('meta_review_status')
    const items = productsOf(ctx.workspace.id).filter(
      (p) =>
        (!search || p.name.toLowerCase().includes(search) || p.sku.toLowerCase().includes(search)) &&
        (!collection || (collection === 'none' ? p.collection_id === null : p.collection_id === collection)) &&
        (active === null || String(p.is_active) === active) &&
        (!availability || p.availability === availability) &&
        (!review || p.meta_review_status === review),
    )
    return response(200).json(paginate(request, byPosition(items).map(toProduct), 25))
  }),

  http.post('/api/v1/catalog/products/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as ProductBody
    const invalid = validateProduct(ctx.workspace.id, body)
    if (invalid) return response.untyped(invalid)
    const product = newProduct(ctx.workspace.id, body)
    catalogMock().products.push(product)
    return response(201).json(toProduct(product))
  }),

  http.post('/api/v1/catalog/products/import/', async ({ request, response }) => {
    await mockDelay(600)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const file = await readFile(request)
    if (!file) return response.untyped(validationError({ file: ['No file was submitted.'] }))
    if (file.size > MAX_IMPORT_BYTES) return response.untyped(validationError({ file: ['The file is larger than 2 MB.'] }))
    const result = importCsv(ctx.workspace.id, await file.text())
    if ('error' in result) return response.untyped(validationError({ file: [result.error] }))
    return response(200).json(result)
  }),

  http.post('/api/v1/catalog/products/reorder/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as Partial<Schemas['ReorderRequest']>
    const invalid = reorder(productsOf(ctx.workspace.id), body.ids)
    return invalid ? response.untyped(invalid) : response(204).empty()
  }),

  http.get('/api/v1/catalog/products/{id}/', async ({ request, params, response }) => {
    await mockDelay(150)
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const product = productsOf(ctx.workspace.id).find((p) => p.id === params.id)
    return product ? response(200).json(toProduct(product)) : response.untyped(notFound())
  }),

  http.patch('/api/v1/catalog/products/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const product = productsOf(ctx.workspace.id).find((p) => p.id === params.id)
    if (!product) return response.untyped(notFound())
    const { sku: _readOnly, ...body } = (await request.json()) as ProductBody
    const invalid = validateProduct(ctx.workspace.id, body, product)
    if (invalid) return response.untyped(invalid)
    applyProduct(product, body)
    queueSync(product)
    return response(200).json(toProduct(product))
  }),

  http.delete('/api/v1/catalog/products/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const state = catalogMock()
    const index = state.products.findIndex((p) => p.workspace_id === ctx.workspace.id && p.id === params.id)
    if (index < 0) return response.untyped(notFound())
    state.products.splice(index, 1)
    return response(204).empty()
  }),

  http.post('/api/v1/catalog/products/{id}/image/', async ({ request, params, response }) => {
    await mockDelay(500)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const product = productsOf(ctx.workspace.id).find((p) => p.id === params.id)
    if (!product) return response.untyped(notFound())
    const file = await readFile(request)
    if (!file) return response.untyped(validationError({ file: ['No file was submitted.'] }))
    if (!(IMAGE_TYPES as readonly string[]).includes(file.type)) return response.untyped(validationError({ file: ['Upload a JPEG or PNG image.'] }))
    if (file.size > MAX_IMAGE_BYTES) return response.untyped(validationError({ file: ['The image is larger than 8 MB.'] }))
    product.image_url = mockProductImage(product.name, (product.name.length * 37) % 360)
    product.updated_at = nowIso()
    queueSync(product)
    return response(200).json(toProduct(product))
  }),

  http.delete('/api/v1/catalog/products/{id}/image/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const product = productsOf(ctx.workspace.id).find((p) => p.id === params.id)
    if (!product) return response.untyped(notFound())
    product.image_url = null
    product.updated_at = nowIso()
    queueSync(product)
    return response(204).empty()
  }),

  // Collections
  http.get('/api/v1/catalog/collections/', async ({ request, response }) => {
    await mockDelay(150)
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    return response(200).json(paginate(request, byPosition(collectionsOf(ctx.workspace.id)).map(toCollection), 50))
  }),

  http.post('/api/v1/catalog/collections/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as CollectionBody
    const invalid = validateCollection(body)
    if (invalid) return response.untyped(invalid)
    const now = nowIso()
    const existing = collectionsOf(ctx.workspace.id)
    const collection: MockCollection = {
      id: uuid(),
      workspace_id: ctx.workspace.id,
      name: String(body.name).trim(),
      description: body.description ?? '',
      position: body.position ?? (existing.length ? Math.max(...existing.map((c) => c.position)) + 1 : 0),
      is_active: body.is_active ?? true,
      created_at: now,
      updated_at: now,
    }
    catalogMock().collections.push(collection)
    return response(201).json(toCollection(collection))
  }),

  http.post('/api/v1/catalog/collections/reorder/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as Partial<Schemas['ReorderRequest']>
    const invalid = reorder(collectionsOf(ctx.workspace.id), body.ids)
    return invalid ? response.untyped(invalid) : response(204).empty()
  }),

  http.get('/api/v1/catalog/collections/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const collection = collectionsOf(ctx.workspace.id).find((c) => c.id === params.id)
    return collection ? response(200).json(toCollection(collection)) : response.untyped(notFound())
  }),

  http.patch('/api/v1/catalog/collections/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const collection = collectionsOf(ctx.workspace.id).find((c) => c.id === params.id)
    if (!collection) return response.untyped(notFound())
    const body = (await request.json()) as CollectionBody
    const invalid = validateCollection(body, collection)
    if (invalid) return response.untyped(invalid)
    if (body.name !== undefined) collection.name = body.name.trim()
    if (body.description !== undefined) collection.description = body.description
    if (body.position !== undefined) collection.position = body.position
    if (body.is_active !== undefined) collection.is_active = body.is_active
    collection.updated_at = nowIso()
    return response(200).json(toCollection(collection))
  }),

  http.delete('/api/v1/catalog/collections/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const state = catalogMock()
    const index = state.collections.findIndex((c) => c.workspace_id === ctx.workspace.id && c.id === params.id)
    if (index < 0) return response.untyped(notFound())
    const [removed] = state.collections.splice(index, 1)
    for (const product of productsOf(ctx.workspace.id)) {
      if (product.collection_id === removed.id) product.collection_id = null
    }
    return response(204).empty()
  }),

  // Meta catalogs
  http.get('/api/v1/catalog/meta-catalogs/', async ({ request, response }) => {
    await mockDelay(150)
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    return response(200).json(paginate(request, catalogsOf(ctx.workspace.id).map(toMetaCatalog)))
  }),

  http.get('/api/v1/catalog/meta-catalogs/available/', async ({ request, query, response }) => {
    await mockDelay(300)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    if (catalogMock().permissionsMissing) return response.untyped(permissionsMissing())
    const wabaId = query.get('waba_id') ?? ''
    return response(200).json([...(catalogMock().availableCatalogs[wabaId] ?? [])])
  }),

  http.post('/api/v1/catalog/meta-catalogs/', async ({ request, response }) => {
    await mockDelay(600)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const state = catalogMock()
    if (state.permissionsMissing) return response.untyped(permissionsMissing())
    const body = (await request.json()) as Partial<Schemas['MetaCatalogConnectRequest']>
    if (Boolean(body.catalog_id) === Boolean(body.create_name?.trim())) {
      return response.untyped(validationError({ non_field_errors: ['Send exactly one of catalog_id or create_name.'] }))
    }
    const waba = ctx.workspace.id === ids.sharmaSweets && body.waba_id === seedWaba.id ? seedWaba : null
    const available = waba ? state.availableCatalogs[waba.id] : undefined
    if (!waba || !available) return response.untyped(validationError({ waba_id: ['Choose a connected WhatsApp Business Account.'] }))
    if (catalogsOf(ctx.workspace.id).length) return response.untyped(errorResponse(409, 'conflict', 'A Meta catalog is already connected. Disconnect it first.'))

    let catalog = body.catalog_id ? available.find((c) => c.id === body.catalog_id) : undefined
    if (body.catalog_id && !catalog) return response.untyped(validationError({ catalog_id: ['This catalog isn’t in your Meta business.'] }))
    if (!catalog) {
      catalog = { id: String(Math.floor(100_000_000_000_000 + Math.random() * 800_000_000_000_000)), name: String(body.create_name).trim() }
      available.push(catalog)
    }
    const now = nowIso()
    const numbers = [{ phone_number_id: seedPhoneNumber.id, display_phone_number: seedPhoneNumber.display_phone_number, is_cart_enabled: false, is_catalog_visible: false }]
    const connected: MockMetaCatalog = {
      id: uuid(),
      workspace_id: ctx.workspace.id,
      waba: { id: waba.id, waba_id: waba.waba_id, name: waba.name },
      catalog_id: catalog.id,
      catalog_name: catalog.name,
      status: 'connected',
      last_synced_at: null,
      last_sync_error: '',
      phone_numbers: numbers,
      created_at: now,
      updated_at: now,
    }
    state.metaCatalogs.push(connected)
    for (const product of productsOf(ctx.workspace.id)) {
      product.meta_sync_status = product.image_url ? 'pending' : 'not_synced'
      product.meta_review_status = 'none'
      product.meta_rejection_reasons = []
    }
    return response(201).json(toMetaCatalog(connected))
  }),

  http.get('/api/v1/catalog/meta-catalogs/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const catalog = catalogsOf(ctx.workspace.id).find((m) => m.id === params.id)
    return catalog ? response(200).json(toMetaCatalog(catalog)) : response.untyped(notFound())
  }),

  http.delete('/api/v1/catalog/meta-catalogs/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const state = catalogMock()
    const index = state.metaCatalogs.findIndex((m) => m.workspace_id === ctx.workspace.id && m.id === params.id)
    if (index < 0) return response.untyped(notFound())
    state.metaCatalogs.splice(index, 1)
    for (const product of productsOf(ctx.workspace.id)) {
      product.meta_sync_status = 'not_synced'
      product.meta_review_status = 'none'
      product.meta_rejection_reasons = []
    }
    return response(204).empty()
  }),

  http.post('/api/v1/catalog/meta-catalogs/{id}/sync/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const catalog = catalogsOf(ctx.workspace.id).find((m) => m.id === params.id)
    if (!catalog) return response.untyped(notFound())
    const products = productsOf(ctx.workspace.id)
    for (const product of products) if (product.image_url) product.meta_sync_status = 'pending'
    const workspaceId = ctx.workspace.id
    setTimeout(() => {
      const now = nowIso()
      for (const product of products) {
        if (product.meta_sync_status !== 'pending') continue
        product.meta_sync_status = 'synced'
        if (product.meta_review_status === 'none' || product.meta_review_status === 'outdated') product.meta_review_status = 'pending'
      }
      catalog.last_synced_at = now
      catalog.last_sync_error = ''
      catalog.updated_at = now
      mockRealtime.emit('catalog.sync', { meta_catalog_id: catalog.id, status: 'synced' }, workspaceId)
    }, SYNC_DELAY_MS)
    return response(202).json(toMetaCatalog(catalog))
  }),

  http.patch('/api/v1/catalog/meta-catalogs/{id}/commerce-settings/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const catalog = catalogsOf(ctx.workspace.id).find((m) => m.id === params.id)
    if (!catalog) return response.untyped(notFound())
    if (catalogMock().permissionsMissing) return response.untyped(permissionsMissing())
    const body = (await request.json()) as Schemas['PatchedCommerceSettingsRequest']
    const settings = catalog.phone_numbers.find((n) => n.phone_number_id === body.phone_number_id)
    if (!settings) return response.untyped(validationError({ phone_number_id: ['This number isn’t linked to the catalog’s WhatsApp Business Account.'] }))
    if (body.is_cart_enabled !== undefined) settings.is_cart_enabled = body.is_cart_enabled
    if (body.is_catalog_visible !== undefined) settings.is_catalog_visible = body.is_catalog_visible
    catalog.updated_at = nowIso()
    return response(200).json(toMetaCatalog(catalog))
  }),
]
