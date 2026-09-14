import { useId, useState, type DragEvent, type ReactNode } from 'react'
import { CloudUpload } from 'lucide-react'
import { cn } from '../../lib/cn'

export type FileRejection = { file: File; reason: string }

type FileDropzoneProps = {
  /** Input `accept`, e.g. `.csv,text/csv` or `image/jpeg,image/png`. */
  accept?: string
  maxSizeBytes?: number
  multiple?: boolean
  disabled?: boolean
  label?: ReactNode
  hint?: ReactNode
  onFiles: (files: File[]) => void
  onReject?: (rejections: FileRejection[]) => void
  className?: string
}

function formatBytes(bytes: number) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(bytes % (1024 * 1024) ? 1 : 0)} MB`
  return `${Math.round(bytes / 1024)} KB`
}

function matchesAccept(file: File, accept: string | undefined) {
  if (!accept) return true
  const name = file.name.toLowerCase()
  return accept
    .split(',')
    .map((token) => token.trim().toLowerCase())
    .some((token) => {
      if (!token) return false
      if (token.startsWith('.')) return name.endsWith(token)
      if (token.endsWith('/*')) return file.type.startsWith(token.slice(0, -1))
      return file.type === token
    })
}

/** Click-to-browse or drag-and-drop. The real file input stays keyboard-focusable. */
export function FileDropzone({
  accept,
  maxSizeBytes,
  multiple = false,
  disabled = false,
  label = 'Drop a file here or browse',
  hint,
  onFiles,
  onReject,
  className,
}: FileDropzoneProps) {
  const id = useId()
  const [dragging, setDragging] = useState(false)
  const [errors, setErrors] = useState<string[]>([])

  const handle = (list: FileList | null) => {
    if (!list || disabled) return
    const files = Array.from(list).slice(0, multiple ? undefined : 1)
    const accepted: File[] = []
    const rejected: FileRejection[] = []
    for (const file of files) {
      if (!matchesAccept(file, accept)) rejected.push({ file, reason: `${file.name}: this file type isn't supported.` })
      else if (maxSizeBytes && file.size > maxSizeBytes) {
        rejected.push({ file, reason: `${file.name} is larger than ${formatBytes(maxSizeBytes)}.` })
      } else accepted.push(file)
    }
    setErrors(rejected.map((r) => r.reason))
    if (rejected.length) onReject?.(rejected)
    if (accepted.length) onFiles(accepted)
  }

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault()
    setDragging(false)
    handle(event.dataTransfer.files)
  }

  return (
    <div className={className}>
      <label
        htmlFor={id}
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          'flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed px-6 py-8 text-center transition-colors',
          'focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/25',
          dragging ? 'border-accent bg-accent-soft/50' : 'border-line bg-card hover:border-ink/30',
          disabled && 'cursor-not-allowed opacity-60',
        )}
      >
        <CloudUpload className="size-6 text-muted" aria-hidden="true" />
        <span className="text-sm font-medium text-ink">{label}</span>
        {(hint || maxSizeBytes) && (
          <span className="text-[13px] text-muted">{hint ?? `Up to ${formatBytes(maxSizeBytes ?? 0)}`}</span>
        )}
        <input
          id={id}
          type="file"
          accept={accept}
          multiple={multiple}
          disabled={disabled}
          className="sr-only"
          onChange={(event) => {
            handle(event.target.files)
            event.target.value = ''
          }}
        />
      </label>
      {errors.length > 0 && (
        <ul role="alert" className="mt-2 space-y-0.5 text-[13px] text-signal">
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
