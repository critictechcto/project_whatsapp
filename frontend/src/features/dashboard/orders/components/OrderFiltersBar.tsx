import { Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button, Field, Input, Select } from '../../../../components/app'
import type { PaymentMethod, PaymentStatus } from '../api'
import { hasActiveFilters, paymentMethodOptions, paymentStatusOptions, type OrderFilters } from '../filters'

type OrderFiltersBarProps = {
  filters: OrderFilters
  setFilters: (patch: Partial<OrderFilters>) => void
}

const SEARCH_DEBOUNCE_MS = 300

export function OrderFiltersBar({ filters, setFilters }: OrderFiltersBarProps) {
  const [search, setSearch] = useState(filters.q)

  useEffect(() => {
    if (search === filters.q) return
    const timer = setTimeout(() => setFilters({ q: search }), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [search, filters.q, setFilters])

  const datesReversed = Boolean(filters.from && filters.to && filters.from > filters.to)

  return (
    <div className="flex flex-col gap-3 lg:flex-row lg:items-start">
      <Field label="Search" className="lg:w-72">
        <Input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Order number, name or phone"
          prefix={<Search className="size-4" aria-hidden="true" />}
        />
      </Field>
      <div className="grid flex-1 grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="Payment status">
          <Select
            value={filters.payment}
            onChange={(event) => setFilters({ payment: event.target.value as PaymentStatus | '' })}
            placeholder="Any"
            options={paymentStatusOptions}
          />
        </Field>
        <Field label="Payment method">
          <Select
            value={filters.method}
            onChange={(event) => setFilters({ method: event.target.value as PaymentMethod | '' })}
            placeholder="Any"
            options={paymentMethodOptions}
          />
        </Field>
        <Field label="Placed from" error={datesReversed ? 'Pick a date before the end date.' : undefined}>
          <Input type="date" value={filters.from} max={filters.to || undefined} onChange={(event) => setFilters({ from: event.target.value })} />
        </Field>
        <Field label="Placed until">
          <Input type="date" value={filters.to} min={filters.from || undefined} onChange={(event) => setFilters({ to: event.target.value })} />
        </Field>
      </div>
      {hasActiveFilters(filters) && (
        <Button
          variant="ghost"
          className="self-start lg:mt-[26px]"
          onClick={() => {
            setSearch('')
            setFilters({ payment: '', method: '', from: '', to: '', q: '' })
          }}
        >
          Clear filters
        </Button>
      )}
    </div>
  )
}
