import { Download, FileSpreadsheet, X } from 'lucide-react'
import { useState } from 'react'
import { ApiError, errorMessage } from '../../../../api/errors'
import { Button, Dialog, FileDropzone } from '../../../../components/app'
import { formatNumber } from '../../../../lib/format'
import { importProducts, useInvalidateCatalog } from '../api'
import { csvColumns, MAX_IMPORT_BYTES, MAX_IMPORT_ROWS, sampleCsvHref } from '../lib/csv'
import type { ProductImportResult } from '../lib/types'
import { FormError, Note } from './shared'

type ImportDialogProps = { open: boolean; onOpenChange: (open: boolean) => void }

export function ImportDialog({ open, onOpenChange }: ImportDialogProps) {
  const [busy, setBusy] = useState(false)
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      dismissible={!busy}
      title="Import products from CSV"
      description="Create new products and update existing ones by SKU. Prices are in rupees and include GST."
    >
      {open && <ImportFlow onClose={() => onOpenChange(false)} onBusyChange={setBusy} />}
    </Dialog>
  )
}

function ImportFlow({ onClose, onBusyChange }: { onClose: () => void; onBusyChange: (busy: boolean) => void }) {
  const invalidate = useInvalidateCatalog()
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string>()
  const [result, setResult] = useState<ProductImportResult | null>(null)

  const start = async () => {
    if (!file) {
      setError('Choose a CSV file to import.')
      return
    }
    setUploading(true)
    onBusyChange(true)
    setError(undefined)
    try {
      const data = await importProducts(file)
      setResult(data)
      void invalidate()
    } catch (err) {
      setError(err instanceof ApiError ? (err.fieldErrors.file ?? errorMessage(err)) : errorMessage(err))
    } finally {
      setUploading(false)
      onBusyChange(false)
    }
  }

  const reset = () => {
    setResult(null)
    setFile(null)
    setError(undefined)
  }

  if (result) return <ImportResultView result={result} onDone={onClose} onAgain={reset} />

  return (
    <div className="flex flex-col gap-4">
      <FormError message={error} />
      <div className="overflow-x-auto rounded-lg border border-line-2">
        <table className="w-full border-collapse text-[13px]">
          <caption className="sr-only">CSV columns</caption>
          <thead>
            <tr className="border-b border-line-2 bg-paper/60 text-left">
              <th scope="col" className="px-3 py-2 font-mono text-[11px] font-normal uppercase tracking-[0.12em] text-muted">
                Column
              </th>
              <th scope="col" className="px-3 py-2 font-mono text-[11px] font-normal uppercase tracking-[0.12em] text-muted">
                Format
              </th>
            </tr>
          </thead>
          <tbody>
            {csvColumns.map((column) => (
              <tr key={column.name} className="border-b border-line-2 last:border-b-0">
                <td className="whitespace-nowrap px-3 py-1.5 align-top font-mono text-ink">
                  {column.name}
                  {column.required && <span className="ml-1.5 font-sans text-[11px] text-signal">required</span>}
                </td>
                <td className="px-3 py-1.5 text-ink-2">{column.format}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Note>
        Up to {formatNumber(MAX_IMPORT_ROWS)} rows and 2 MB. Photos aren&apos;t imported: add them to each product afterwards.{' '}
        <a href={sampleCsvHref} download="upchatz-products-sample.csv" className="inline-flex items-center gap-1 font-medium text-accent-2 underline-offset-2 hover:underline">
          <Download className="size-3.5" aria-hidden="true" />
          Download sample CSV
        </a>
      </Note>

      {file ? (
        <div className="flex items-center gap-3 rounded-lg border border-line bg-card px-3 py-2.5">
          <FileSpreadsheet className="size-5 shrink-0 text-muted" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-ink">{file.name}</p>
            <p className="text-[12.5px] text-muted">{Math.max(1, Math.round(file.size / 1024))} KB</p>
          </div>
          <Button variant="ghost" size="icon-sm" aria-label={`Remove ${file.name}`} onClick={() => setFile(null)} disabled={uploading}>
            <X className="size-4" aria-hidden="true" />
          </Button>
        </div>
      ) : (
        <FileDropzone
          accept=".csv,text/csv"
          maxSizeBytes={MAX_IMPORT_BYTES}
          label="Drop a CSV here or browse"
          hint="CSV up to 2 MB"
          onFiles={(files) => {
            setError(undefined)
            setFile(files[0] ?? null)
          }}
        />
      )}

      <div className="-mx-5 -mb-4 mt-1 flex flex-wrap justify-end gap-2 border-t border-line-2 px-5 py-3.5">
        <Button variant="secondary" onClick={onClose} disabled={uploading}>
          Cancel
        </Button>
        <Button onClick={() => void start()} loading={uploading}>
          Import products
        </Button>
      </div>
    </div>
  )
}

function ImportResultView({ result, onDone, onAgain }: { result: ProductImportResult; onDone: () => void; onAgain: () => void }) {
  const stats = [
    { label: 'Created', value: result.created_count },
    { label: 'Updated', value: result.updated_count },
    { label: 'Skipped', value: result.skipped_count },
  ]
  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Import result" className="flex flex-col gap-3">
        <p role="status" className="text-sm text-ink">
          Import finished.
        </p>
        <dl className="grid grid-cols-3 gap-2">
          {stats.map((stat) => (
            <div key={stat.label} className="rounded-lg border border-line-2 bg-paper/50 px-3 py-2.5">
              <dt className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">{stat.label}</dt>
              <dd className="font-display text-xl font-semibold text-ink">{formatNumber(stat.value)}</dd>
            </div>
          ))}
        </dl>
      </section>
      {result.errors.length > 0 && (
        <div className="max-h-72 overflow-auto rounded-lg border border-line-2">
          <table className="w-full border-collapse text-[13px]">
            <caption className="sr-only">Rows not imported</caption>
            <thead className="sticky top-0 bg-card">
              <tr className="border-b border-line-2 text-left">
                {['Row', 'SKU', 'Reason'].map((heading) => (
                  <th key={heading} scope="col" className="px-3 py-2 font-mono text-[11px] font-normal uppercase tracking-[0.12em] text-muted">
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.errors.map((row) => (
                <tr key={`${row.row}-${row.sku}`} className="border-b border-line-2 last:border-b-0">
                  <td className="px-3 py-1.5 align-top font-mono text-ink-2">{row.row}</td>
                  <td className="px-3 py-1.5 align-top font-mono text-ink">{row.sku || '—'}</td>
                  <td className="px-3 py-1.5 text-ink-2">{row.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="-mx-5 -mb-4 mt-1 flex flex-wrap justify-end gap-2 border-t border-line-2 px-5 py-3.5">
        <Button variant="secondary" onClick={onAgain}>
          Import another file
        </Button>
        <Button onClick={onDone}>Done</Button>
      </div>
    </div>
  )
}
