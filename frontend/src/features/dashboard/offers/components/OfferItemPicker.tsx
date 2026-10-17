import { Search } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { errorMessage } from '../../../../api/errors'
import { Button, Input, Spinner } from '../../../../components/app'
import { formatPaise } from '../../../../lib/money'
import { useOfferCatalogItems } from '../api'
import type { OfferItem } from '../types'

type Props = {
  workspaceId: string
  value: string[]
  onChange: (ids: string[]) => void
  /** Items already saved on the offer, shown even if they are no longer in the catalog list. */
  saved?: readonly OfferItem[]
  invalid?: boolean
  describedBy?: string
}

type Row = { id: string; name: string; kind: string; price_paise: number; is_active: boolean }

/** Checkbox list of catalog products and services, with a search box. */
export function OfferItemPicker({ workspaceId, value, onChange, saved = [], invalid, describedBy }: Props) {
  const items = useOfferCatalogItems(workspaceId)
  const [search, setSearch] = useState('')
  const listId = useId()

  const rows = useMemo<Row[]>(() => {
    const fromCatalog: Row[] = (items.data ?? []).map((item) => ({
      id: item.id,
      name: item.name,
      kind: item.kind ?? 'product',
      price_paise: item.sale_price_paise ?? item.price_paise,
      is_active: item.is_active ?? true,
    }))
    const known = new Set(fromCatalog.map((row) => row.id))
    return [...fromCatalog, ...saved.filter((item) => !known.has(item.id))]
  }, [items.data, saved])

  const chosen = new Set(value)
  const query = search.trim().toLowerCase()
  const visible = query ? rows.filter((row) => row.name.toLowerCase().includes(query)) : rows

  function toggle(id: string, on: boolean) {
    onChange(on ? [...value, id] : value.filter((other) => other !== id))
  }

  if (items.isPending) {
    return (
      <div className="flex items-center gap-2 py-3 text-sm text-muted">
        <Spinner size="sm" /> Loading your catalog…
      </div>
    )
  }
  if (items.isError && rows.length === 0) {
    return (
      <div className="flex flex-wrap items-center gap-3 text-sm text-muted">
        <span>Couldn't load your catalog. {errorMessage(items.error)}</span>
        <Button variant="secondary" size="sm" onClick={() => void items.refetch()}>
          Try again
        </Button>
      </div>
    )
  }
  if (rows.length === 0) {
    return <p className="text-sm text-muted">Your catalog is empty. Add products or services on the Catalog page first.</p>
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="w-full sm:max-w-xs">
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            prefix={<Search className="size-4" aria-hidden="true" />}
            placeholder="Search items"
            aria-label="Search products and services"
            aria-controls={listId}
            autoComplete="off"
          />
        </div>
        <p className="text-[13px] text-muted" aria-live="polite">
          {value.length === 0 ? 'None chosen' : `${value.length} chosen`}
        </p>
      </div>
      <ul
        id={listId}
        aria-label="Products and services"
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        className={`max-h-72 overflow-y-auto rounded-xl border bg-card ${invalid ? 'border-signal' : 'border-line'}`}
      >
        {visible.length === 0 && <li className="px-4 py-3 text-sm text-muted">No items match “{search.trim()}”.</li>}
        {visible.map((row) => (
          <li key={row.id} className="border-b border-line last:border-b-0">
            <label className="flex min-h-11 cursor-pointer items-center gap-3 px-4 py-2 hover:bg-paper">
              <input
                type="checkbox"
                checked={chosen.has(row.id)}
                onChange={(event) => toggle(row.id, event.target.checked)}
                className="size-4 shrink-0 cursor-pointer rounded border-line accent-accent"
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-ink">{row.name}</span>
                <span className="block text-[12px] text-muted">
                  {row.kind === 'service' ? 'Service' : 'Product'} · {formatPaise(row.price_paise)}
                  {row.is_active ? '' : ' · Hidden from the store'}
                </span>
              </span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  )
}
