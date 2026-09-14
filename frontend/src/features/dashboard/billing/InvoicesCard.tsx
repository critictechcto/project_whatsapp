import { Download, ReceiptText } from 'lucide-react'
import type { Schemas } from '../../../api/types'
import { Button, EmptyState, StatusBadge, Table, type Column } from '../../../components/app'
import { formatDate } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { actionErrorMessage } from '../settings/ui/hooks'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import { formatPaise } from './money'
import { useInvoices } from './queries'

type Invoice = Schemas['Invoice']

function TaxLines({ invoice }: { invoice: Invoice }) {
  if (invoice.igst_paise > 0) {
    return <span className="block">IGST {formatPaise(invoice.igst_paise)}</span>
  }
  return (
    <>
      <span className="block">CGST {formatPaise(invoice.cgst_paise)}</span>
      <span className="block">SGST {formatPaise(invoice.sgst_paise)}</span>
    </>
  )
}

export function InvoicesCard() {
  const { timeZone } = useWorkspace()
  const invoices = useInvoices()

  const columns: Column<Invoice>[] = [
    {
      id: 'number',
      header: 'Invoice',
      cell: (invoice) => (
        <div>
          <p className="font-mono text-[13px] font-medium text-ink">{invoice.number}</p>
          <p className="text-[12.5px] text-muted">{formatDate(invoice.issued_at, timeZone)}</p>
        </div>
      ),
    },
    {
      id: 'period',
      header: 'Period',
      hideOnMobile: true,
      cell: (invoice) => (
        <span className="text-muted">
          {formatDate(invoice.period_start, timeZone)} – {formatDate(invoice.period_end, timeZone)}
        </span>
      ),
    },
    { id: 'subtotal', header: 'Taxable value', align: 'right', hideOnMobile: true, cell: (invoice) => formatPaise(invoice.subtotal_paise) },
    {
      id: 'tax',
      header: 'GST',
      align: 'right',
      hideOnMobile: true,
      cell: (invoice) => (
        <span className="text-[13px] text-muted">
          <TaxLines invoice={invoice} />
        </span>
      ),
    },
    {
      id: 'total',
      header: 'Total',
      align: 'right',
      cell: (invoice) => <span className="font-medium text-ink">{formatPaise(invoice.total_paise)}</span>,
    },
    { id: 'status', header: 'Status', cell: (invoice) => <StatusBadge status={invoice.status} /> },
    {
      id: 'download',
      header: <span className="sr-only">Download</span>,
      align: 'right',
      cell: (invoice) =>
        invoice.download_url ? (
          <a
            href={invoice.download_url}
            target="_blank"
            rel="noreferrer"
            aria-label={`Download invoice ${invoice.number}`}
            className="inline-grid size-8 place-items-center rounded-md text-muted hover:bg-ink/5 hover:text-ink"
          >
            <Download className="size-4" aria-hidden="true" />
          </a>
        ) : (
          <span className="text-[12.5px] text-muted">PDF not ready</span>
        ),
    },
  ]

  return (
    <SectionCard id="billing-invoices" title="Invoices" description="Tax invoices with GST for each payment.">
      {invoices.isError ? (
        <Notice
          tone="danger"
          role="alert"
          title="Couldn't load invoices"
          action={
            <Button variant="secondary" size="sm" onClick={() => void invoices.refetch()}>
              Try again
            </Button>
          }
        >
          {actionErrorMessage(invoices.error)}
        </Notice>
      ) : (
        <Table
          caption="Invoices"
          columns={columns}
          rows={invoices.items}
          getRowId={(invoice) => invoice.id}
          loading={invoices.isPending}
          hasNextPage={invoices.hasNextPage}
          isFetchingNextPage={invoices.isFetchingNextPage}
          onLoadMore={() => void invoices.fetchNextPage()}
          empty={
            <EmptyState
              icon={<ReceiptText className="size-5" aria-hidden="true" />}
              title="No invoices yet"
              description="An invoice appears here after each successful payment."
            />
          }
        />
      )}
    </SectionCard>
  )
}
