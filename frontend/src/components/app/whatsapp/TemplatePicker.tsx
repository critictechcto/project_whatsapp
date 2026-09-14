import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../../../api/client'
import { useCursorQuery } from '../../../api/pagination'
import type { MessageTemplate, TemplateCategory, TemplateStatus } from '../../../api/types'
import { useWorkspace } from '../../../lib/workspace'
import { Combobox } from '../Combobox'
import { StatusBadge } from '../StatusBadge'
import { templatePreview } from './template'
import { templateKeys } from './templateKeys'
import { WhatsAppMessagePreview } from './WhatsAppMessagePreview'

const categoryLabels: Record<TemplateCategory, string> = {
  MARKETING: 'Marketing',
  UTILITY: 'Utility',
  AUTHENTICATION: 'Authentication',
}

type TemplatePickerProps = {
  value: string | null
  onChange: (template: MessageTemplate | null) => void
  /** Default `APPROVED`: only approved templates can be sent. */
  status?: TemplateStatus
  category?: TemplateCategory
  showPreview?: boolean
  disabled?: boolean
  id?: string
  'aria-describedby'?: string
  'aria-invalid'?: boolean
  'aria-label'?: string
}

/** Searchable list of the workspace's templates with a preview of the selection. */
export function TemplatePicker({ value, onChange, status = 'APPROVED', category, showPreview = true, disabled, ...aria }: TemplatePickerProps) {
  const { workspaceId } = useWorkspace()
  const [search, setSearch] = useState('')

  const list = useCursorQuery<MessageTemplate>({
    queryKey: templateKeys.list(workspaceId, { status, category, search, page_size: 100 }),
    queryFn: ({ cursor, signal }) =>
      unwrap(
        api.GET('/api/v1/templates/', {
          params: { query: { status, category, search: search || undefined, cursor, page_size: 100 } },
          signal,
        }),
      ),
  })

  // The selected template may not be in the current search results.
  const selected = useQuery({
    queryKey: templateKeys.detail(workspaceId, value ?? ''),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/templates/{id}/', { params: { path: { id: value ?? '' } }, signal })),
    enabled: Boolean(value) && !list.items.some((template) => template.id === value),
  })

  const selectedTemplate = list.items.find((template) => template.id === value) ?? (value ? selected.data : undefined)

  const options = useMemo(
    () =>
      list.items.map((template) => ({
        value: template.id,
        label: template.name,
        description: `${categoryLabels[template.category]} · ${template.language}`,
      })),
    [list.items],
  )

  return (
    <div className="flex flex-col gap-3">
      <Combobox
        {...aria}
        options={options}
        value={value}
        onChange={(id) => onChange(list.items.find((template) => template.id === id) ?? null)}
        onSearchChange={setSearch}
        filter={false}
        loading={list.isFetching}
        disabled={disabled}
        placeholder="Search templates"
        emptyText={status === 'APPROVED' ? 'No approved templates found' : 'No templates found'}
        selectedLabels={selectedTemplate ? { [selectedTemplate.id]: selectedTemplate.name } : undefined}
      />
      {showPreview && selectedTemplate && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2 text-[13px] text-muted">
            <span className="font-mono text-ink">{selectedTemplate.name}</span>
            <span>{categoryLabels[selectedTemplate.category]}</span>
            <span>{selectedTemplate.language}</span>
            <StatusBadge status={selectedTemplate.status} />
          </div>
          <WhatsAppMessagePreview message={templatePreview(selectedTemplate)} />
        </div>
      )}
    </div>
  )
}
