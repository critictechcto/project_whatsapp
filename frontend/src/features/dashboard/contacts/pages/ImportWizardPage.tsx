import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CircleAlert, FileSpreadsheet, X } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { z } from 'zod'
import { applyApiErrorToForm } from '../../../../api/errors'
import { Button, Checkbox, Field, FieldError, FileDropzone, Input, PageHeader } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { formatNumber } from '../../../../lib/format'
import { useWorkspace } from '../../../../lib/workspace'
import { contactKeys, createImport, useTags } from '../api'
import { FormError, TagPicker } from '../components/shared'
import { buildPreview, MAX_IMPORT_BYTES, PHONE_ALIASES, type ColumnTarget, type CsvPreview } from '../lib/csv'

const targetLabels: Record<ColumnTarget, string> = {
  phone: 'Phone number',
  name: 'Name',
  email: 'Email',
  attribute: 'Attribute',
  ignored: 'Not imported',
}

const schema = z
  .object({
    tagIds: z.array(z.string()),
    markOptedIn: z.boolean(),
    optInSource: z.string().trim().max(255, 'Use at most 255 characters.'),
    consentAttested: z.boolean(),
  })
  .superRefine((values, ctx) => {
    if (!values.consentAttested) {
      ctx.addIssue({
        code: 'custom',
        path: ['consentAttested'],
        message: 'Confirm that these contacts agreed to receive WhatsApp messages from your business.',
      })
    }
    if (values.markOptedIn && !values.optInSource) {
      ctx.addIssue({ code: 'custom', path: ['optInSource'], message: 'Say where these contacts opted in.' })
    }
  })

type Values = z.infer<typeof schema>

type SelectedFile = { file: File; preview: CsvPreview }

function formatBytes(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

export function ImportWizardPage() {
  const { workspaceId, workspace } = useWorkspace()
  const base = `/app/w/${workspaceId}`
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { tags, isLoading: tagsLoading } = useTags()
  const [selected, setSelected] = useState<SelectedFile | null>(null)
  const [fileError, setFileError] = useState<string>()

  const {
    control,
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { tagIds: [], markOptedIn: false, optInSource: '', consentAttested: false },
  })
  const markOptedIn = useWatch({ control, name: 'markOptedIn' })

  const readFile = async (file: File) => {
    setFileError(undefined)
    try {
      const preview = buildPreview(await file.text())
      if (!preview) {
        setSelected(null)
        setFileError('The file is empty.')
        return
      }
      setSelected({ file, preview })
    } catch {
      setSelected(null)
      setFileError("This file couldn't be read. Save it as a UTF-8 CSV and try again.")
    }
  }

  const onSubmit = handleSubmit(async (values) => {
    if (!selected) {
      setFileError('Choose a CSV file to import.')
      return
    }
    if (!selected.preview.hasPhoneColumn) return
    try {
      const job = await createImport({
        file: selected.file,
        markOptedIn: values.markOptedIn,
        consentAttested: values.consentAttested,
        optInSource: values.markOptedIn ? values.optInSource : '',
        tagIds: values.tagIds,
      })
      void queryClient.invalidateQueries({ queryKey: contactKeys.custom(workspaceId, 'imports') })
      navigate(`${base}/contacts/imports/${job.id}`, { state: { estimatedRows: selected.preview.rowCount } })
    } catch (error) {
      applyApiErrorToForm(error, setError, {
        fieldMap: { consent_attested: 'consentAttested', opt_in_source: 'optInSource', tag_ids: 'tagIds' },
        fields: ['consentAttested', 'optInSource', 'tagIds'],
      })
    }
  })

  const preview = selected?.preview

  return (
    <div className="flex flex-col gap-6">
      <Link to={`${base}/contacts/imports`} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden="true" />
        Imports
      </Link>
      <PageHeader
        title="Import contacts"
        description="Upload a CSV of customers who agreed to hear from you on WhatsApp. Existing contacts with the same phone number are updated."
      />

      <form onSubmit={onSubmit} noValidate className="flex max-w-3xl flex-col gap-6">
        <Step number={1} title="Choose a CSV file">
          {selected ? (
            <div className="flex items-center gap-3 rounded-lg border border-line bg-card px-4 py-3">
              <FileSpreadsheet className="size-5 shrink-0 text-muted" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink">{selected.file.name}</p>
                <p className="text-[13px] text-muted">
                  {formatBytes(selected.file.size)} · {formatNumber(selected.preview.rowCount)}{' '}
                  {selected.preview.rowCount === 1 ? 'row' : 'rows'}
                </p>
              </div>
              <Button variant="ghost" size="icon-sm" aria-label="Remove file" onClick={() => setSelected(null)}>
                <X className="size-4" aria-hidden="true" />
              </Button>
            </div>
          ) : (
            <FileDropzone
              accept=".csv,text/csv"
              maxSizeBytes={MAX_IMPORT_BYTES}
              label="Drop a CSV here or browse"
              hint="UTF-8 CSV up to 10 MB, with a header row"
              onFiles={([file]) => void readFile(file)}
              onReject={() => setSelected(null)}
            />
          )}
          <FieldError>{fileError}</FieldError>
          <p className="text-[13px] text-muted">
            Name the phone column one of {PHONE_ALIASES.map((alias) => `"${alias}"`).join(', ')}. Columns named "name" and "email" fill
            those fields; other columns become attributes. Numbers without a country code are read as Indian (+91).
          </p>
        </Step>

        {preview && (
          <Step number={2} title="Check the columns">
            {!preview.hasPhoneColumn && (
              <div role="alert" className="flex items-start gap-2 rounded-lg border border-signal/25 bg-signal-soft/60 px-3 py-2.5 text-sm text-signal">
                <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <span>No phone column found. Rename the column with phone numbers to "phone" and upload the file again.</span>
              </div>
            )}
            <div className="overflow-x-auto rounded-xl border border-line bg-card">
              <table className="w-full border-collapse text-sm">
                <caption className="sr-only">Column mapping</caption>
                <thead>
                  <tr className="border-b border-line-2 bg-paper/60 text-left font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
                    <th scope="col" className="px-4 py-2.5 font-normal">Column</th>
                    <th scope="col" className="px-4 py-2.5 font-normal">Imports as</th>
                    <th scope="col" className="px-4 py-2.5 font-normal">First row</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.mapping.map((column) => (
                    <tr key={column.index} className="border-b border-line-2 last:border-b-0">
                      <td className="px-4 py-2.5 font-mono text-[13px]">{column.header || <span className="text-muted">(blank)</span>}</td>
                      <td className={cn('px-4 py-2.5', column.target === 'ignored' ? 'text-muted' : 'text-ink')}>
                        {targetLabels[column.target]}
                        {column.target === 'attribute' && <span className="font-mono text-[12.5px] text-muted"> {column.key}</span>}
                      </td>
                      <td className="max-w-56 truncate px-4 py-2.5 text-ink-2">{preview.rows[0]?.[column.index] ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {preview.rows.length > 0 && (
              <details className="rounded-lg border border-line-2 bg-card px-4 py-2 text-sm">
                <summary className="cursor-pointer py-1 text-ink">Preview the first {preview.rows.length} rows</summary>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full border-collapse text-[13px]">
                    <caption className="sr-only">First rows of the file</caption>
                    <thead>
                      <tr className="text-left text-muted">
                        {preview.header.map((cell, index) => (
                          <th key={index} scope="col" className="whitespace-nowrap px-2 py-1 font-medium">
                            {cell}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row, rowIndex) => (
                        <tr key={rowIndex} className="border-t border-line-2">
                          {preview.header.map((_, index) => (
                            <td key={index} className="whitespace-nowrap px-2 py-1 text-ink-2">
                              {row[index] ?? ''}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
            <p className="text-[13px] text-muted">
              This preview is read in your browser. The server reads the whole file and reports any rows it can't import.
            </p>
          </Step>
        )}

        <Step number={preview ? 3 : 2} title="Tags and consent">
          <FormError message={errors.root?.server?.message} />
          <Field label="Add tags to every imported contact" error={errors.tagIds?.message}>
            <Controller
              control={control}
              name="tagIds"
              render={({ field }) => <TagPicker tags={tags} loading={tagsLoading} value={field.value} onChange={field.onChange} placeholder="Optional" />}
            />
          </Field>

          <Checkbox
            label="Record a marketing opt-in for these contacts"
            description="Use this only if they agreed to receive offers and updates. Contacts who have opted out stay opted out and are counted as skipped."
            {...register('markOptedIn')}
          />
          {markOptedIn && (
            <Field
              label="Where did they opt in?"
              required
              error={errors.optInSource?.message}
              hint="Kept as evidence in each contact's consent history, e.g. 'Checkout form on sharmasweets.in'."
              className="sm:pl-6"
            >
              <Input maxLength={255} {...register('optInSource')} />
            </Field>
          )}

          <div className="rounded-lg border border-line bg-paper/60 p-4">
            <Checkbox
              aria-invalid={errors.consentAttested ? true : undefined}
              label={
                markOptedIn
                  ? `I confirm every contact in this file agreed to receive WhatsApp messages, including marketing messages, from ${workspace.name}.`
                  : `I confirm every contact in this file agreed to receive WhatsApp messages from ${workspace.name}.`
              }
              description="WhatsApp requires businesses to get opt-in before messaging people. Messaging people who didn't agree can lead to blocks and reports, which can lower your number's quality rating and limits set by Meta."
              {...register('consentAttested')}
            />
            <div className="mt-2 pl-6">
              <FieldError>{errors.consentAttested?.message}</FieldError>
            </div>
          </div>
        </Step>

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" loading={isSubmitting} disabled={Boolean(preview && !preview.hasPhoneColumn)}>
            Start import
          </Button>
          <Link to={`${base}/contacts`} className="text-sm text-muted underline-offset-2 hover:text-ink hover:underline">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  )
}

function Step({ number, title, children }: { number: number; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={`import-step-${number}`} className="flex flex-col gap-3">
      <h2 id={`import-step-${number}`} className="flex items-center gap-2.5 font-display text-base font-semibold tracking-[-0.01em] text-ink">
        <span className="grid size-6 place-items-center rounded-full border border-line bg-card font-mono text-[12px] font-normal text-muted">
          {number}
        </span>
        {title}
      </h2>
      {children}
    </section>
  )
}
