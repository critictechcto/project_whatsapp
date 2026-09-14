import { ImageOff, Trash2 } from 'lucide-react'
import { useId, useState } from 'react'
import { Button, FileDropzone, Spinner } from '../../../../components/app'
import { IMAGE_ACCEPT, validateProductImage } from '../lib/image'

type ImageFieldProps = {
  /** The image currently shown (saved URL or a local preview of a pending file). */
  imageUrl: string | null
  disabled?: boolean
  busy?: boolean
  /** Server error to show under the field. */
  error?: string
  /** Called with a file that passed the client-side checks. */
  onFile: (file: File) => void
  onRemove: () => void
}

/** Product photo with client-side checks (JPEG/PNG, ≤ 8 MB, ≥ 500×500 px) and server error display. */
export function ImageField({ imageUrl, disabled, busy, error, onFile, onRemove }: ImageFieldProps) {
  const [checking, setChecking] = useState(false)
  const [clientError, setClientError] = useState<string>()
  const errorId = useId()
  const message = clientError ?? error

  const handle = async (file: File) => {
    setChecking(true)
    setClientError(undefined)
    const problem = await validateProductImage(file)
    setChecking(false)
    if (problem) setClientError(problem)
    else onFile(file)
  }

  return (
    <fieldset className="flex flex-col gap-2" aria-describedby={message ? errorId : undefined} disabled={disabled}>
      <legend className="text-[13px] font-medium text-ink">Photo</legend>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <div className="relative grid size-28 shrink-0 place-items-center overflow-hidden rounded-lg border border-line-2 bg-paper-2">
          {imageUrl ? (
            <img src={imageUrl} alt="Product photo" className="size-full object-cover" />
          ) : (
            <ImageOff className="size-6 text-muted" aria-label="No photo" />
          )}
          {(busy || checking) && (
            <div className="absolute inset-0 grid place-items-center bg-card/70">
              <Spinner label={checking ? 'Checking image' : 'Uploading image'} />
            </div>
          )}
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          {!disabled && (
            <FileDropzone
              accept={IMAGE_ACCEPT}
              disabled={busy || checking}
              label={imageUrl ? 'Replace photo: drop or browse' : 'Drop a photo here or browse'}
              hint="JPEG or PNG, at least 500×500 px, up to 8 MB"
              onFiles={(files) => files[0] && void handle(files[0])}
            />
          )}
          {imageUrl && !disabled && (
            <div>
              <Button variant="ghost" size="sm" icon={<Trash2 className="size-3.5" aria-hidden="true" />} onClick={onRemove} disabled={busy}>
                Remove photo
              </Button>
            </div>
          )}
          {message && (
            <p id={errorId} role="alert" className="text-[13px] text-signal">
              {message}
            </p>
          )}
          <p className="text-[12.5px] text-muted">Meta needs a public photo before a product can appear in WhatsApp&apos;s catalog.</p>
        </div>
      </div>
    </fieldset>
  )
}
