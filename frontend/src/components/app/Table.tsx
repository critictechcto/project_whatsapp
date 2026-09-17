import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { Button } from './Button'
import { Skeleton } from './Spinner'

export type Column<T> = {
  id: string
  header: ReactNode
  cell: (row: T) => ReactNode
  className?: string
  /** Hide below the `sm` breakpoint. */
  hideOnMobile?: boolean
  align?: 'left' | 'right'
}

type TableProps<T> = {
  /** Screen-reader caption describing the table. */
  caption: string
  columns: readonly Column<T>[]
  rows: readonly T[]
  getRowId: (row: T) => string
  loading?: boolean
  /** Shown instead of the table when there are no rows and it isn't loading. */
  empty?: ReactNode
  hasNextPage?: boolean
  isFetchingNextPage?: boolean
  onLoadMore?: () => void
  className?: string
}

/**
 * Data table with cursor "Load more". Pair with `useCursorQuery`:
 * `<Table rows={q.items} hasNextPage={q.hasNextPage} isFetchingNextPage={q.isFetchingNextPage} onLoadMore={() => q.fetchNextPage()} />`
 * Put links or buttons inside cells for row actions (rows themselves aren't clickable).
 */
export function Table<T>({
  caption,
  columns,
  rows,
  getRowId,
  loading = false,
  empty,
  hasNextPage = false,
  isFetchingNextPage = false,
  onLoadMore,
  className,
}: TableProps<T>) {
  if (!loading && rows.length === 0 && empty) return <>{empty}</>

  const cellClass = (column: Column<T>) =>
    cn('px-4 py-3 align-middle', column.align === 'right' && 'text-right', column.hideOnMobile && 'hidden sm:table-cell', column.className)

  return (
    <div className={cn('overflow-hidden rounded-xl border border-line bg-card', className)}>
      <div className="relative overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="border-b border-line-2 bg-paper/60">
              {columns.map((column) => (
                <th
                  key={column.id}
                  scope="col"
                  className={cn(cellClass(column), 'py-2.5 text-left font-mono text-[11px] font-normal uppercase tracking-[0.12em] text-muted')}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody aria-busy={loading || undefined}>
            {loading && rows.length === 0
              ? Array.from({ length: 5 }, (_, i) => (
                  <tr key={`skeleton-${i}`} className="border-b border-line-2 last:border-b-0">
                    {columns.map((column) => (
                      <td key={column.id} className={cellClass(column)}>
                        <Skeleton className="h-4 w-3/4" />
                      </td>
                    ))}
                  </tr>
                ))
              : rows.map((row) => (
                  <tr key={getRowId(row)} className="border-b border-line-2 last:border-b-0 hover:bg-paper/50">
                    {columns.map((column) => (
                      <td key={column.id} className={cellClass(column)}>
                        {column.cell(row)}
                      </td>
                    ))}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
      {(hasNextPage || isFetchingNextPage) && onLoadMore && (
        <div className="flex justify-center border-t border-line-2 p-3">
          <Button variant="secondary" size="sm" loading={isFetchingNextPage} onClick={onLoadMore}>
            Load more
          </Button>
        </div>
      )}
    </div>
  )
}
