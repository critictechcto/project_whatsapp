import { Download, LoaderCircle, ReceiptText } from 'lucide-react'
import { useState } from 'react'
import { api } from '../../../api/client'
import { ApiError } from '../../../api/errors'
import type { Schemas } from '../../../api/types'
import { Button, EmptyState, StatusBadge, Table, useToast, type Column } from '../../../components/app'
import { formatDate } from '../../../lib/datetime'
import { filenameFromDisposition, saveBlob } from '../../../lib/download'
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

/**
 * Downloads the invoice PDF through the authenticated client (it needs the Bearer token and workspace
 * header, so a plain link would not work) and saves it with the server's file name.
 */
async function downloadInvoicePdf(invoice: Invoice): Promise<string> {
  const { data, error, response } = await api.GET('/api/v1/billing/invoices/{id}/pdf/', {
    params: { path: { id: invoice.id } },
    parseAs: 'blob',
  })
  if (!response.ok || !data) throw new ApiError(response.status, error ?? null)
  const filename = filenameFromDisposition(response.headers.get('Content-Disposition')) ?? `${invoice.number.replaceAll('/', '-')}.pdf`
  saveBlob(data, filename)
  return filename
}

function DownloadInvoiceButton({ invoice }: { invoice: Invoice }) {
  const [busy, setBusy] = useState(false)
  const { toast } = useToast()

  async function onDownload() {
    setBusy(true)
    try {
      await downloadInvoicePdf(invoice)
    } catch (error) {
      toast({ title: "Couldn't download the invoice", description: actionErrorMessage(error), tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      type="button"
      onClick={() => void onDownload()}
      disabled={busy}
      aria-label={`Download invoice ${invoice.number} as PDF`}
      aria-busy={busy}
      className="inline-grid size-11 place-items-center rounded-md text-muted hover:bg-ink/5 hover:text-ink disabled:opacity-60 sm:size-8"
    >
      {busy ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <Download className="size-4" aria-hidden="true" />}
    </button>
  )
}

export function InvoicesCard() {
  const { timeZone } = useWorkspace()
  const invoices = useInvoices()
  // Invoices issued while GST isn't charged have no tax; drop the tax columns unless one has some.
  const anyTax = invoices.items.some((invoice) => invoice.total_paise !== invoice.subtotal_paise)

  const allColumns: Column<Invoice>[] = [
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
      cell: (invoice) => <DownloadInvoiceButton invoice={invoice} />,
    },
  ]
  const columns = anyTax ? allColumns : allColumns.filter((column) => column.id !== 'subtotal' && column.id !== 'tax')

  return (
    <SectionCard id="billing-invoices" title="Invoices" description="An invoice for each payment, with GST shown where it was charged.">
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
