import { Fragment } from 'react'
import { Badge } from '../../../components/ui/Badge'
import { cn } from '../../../lib/cn'
import { useInView } from '../../../lib/useInView'
import { TemplateStatusMockup } from './TemplateStatusMockup'

type Preview = {
  name: string
  category: string
  status: 'approved' | 'review'
  /** Message text; numbers are template variables, rendered as {{n}} chips. */
  body: Array<string | number>
  button: string
}

const previews: Preview[] = [
  {
    name: 'login_otp',
    category: 'Authentication',
    status: 'approved',
    body: [1, ' is your verification code. For your security, do not share this code.'],
    button: 'Copy code',
  },
  {
    name: 'order_shipped',
    category: 'Utility',
    status: 'approved',
    body: ['Hi ', 1, ', your order ', 2, ' has shipped. Expected delivery: ', 3, '.'],
    button: 'Track order',
  },
  {
    name: 'festive_early_access',
    category: 'Marketing',
    status: 'review',
    body: ['Hi ', 1, ', our festive sale opens early for you on ', 2, '. Tap below to shop first.'],
    button: 'Shop now',
  },
]

function PreviewCard({ preview }: { preview: Preview }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-card shadow-[inset_0_1px_0_rgb(255_255_255/0.9),0_24px_40px_-24px_rgb(16_39_31/0.45)]">
      <div className="flex items-center justify-between gap-2 border-b border-line-2 px-3 py-2">
        <p className="truncate font-mono text-[10.5px]">{preview.name}</p>
        {preview.status === 'approved' ? <Badge tone="green">Approved</Badge> : <Badge tone="amber">In review</Badge>}
      </div>
      <div className="bg-wallpaper px-3 py-3">
        <div className="rounded-lg rounded-tl-sm bg-white text-[11px] leading-snug shadow-[0_1px_0_rgba(16,39,31,0.1)]">
          <p className="px-2.5 pt-2">
            {preview.body.map((part, i) =>
              typeof part === 'number' ? (
                <span key={i} className="rounded bg-accent-soft px-1 font-mono text-[9.5px] text-accent-2">
                  {`{{${part}}}`}
                </span>
              ) : (
                <Fragment key={i}>{part}</Fragment>
              ),
            )}
          </p>
          <p className="mt-2 border-t border-ink/5 py-1.5 text-center text-[11px] font-medium text-[#1f6aa8]">
            {preview.button}
          </p>
        </div>
        <p className="mt-2 font-mono text-[9.5px] uppercase tracking-[0.12em] text-muted">{preview.category}</p>
      </div>
    </div>
  )
}

/** Template list with live previews fanned out in front of it. Decorative. */
export function TemplateStack() {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.3 })

  return (
    <div ref={ref} className={cn('template-stack', inView && 'is-fanned')}>
      <TemplateStatusMockup />
      <div aria-hidden="true" className="template-deck relative -mt-2 h-[250px]">
        {previews.map((preview, i) => (
          <div key={preview.name} className="template-card" data-card={i}>
            <PreviewCard preview={preview} />
          </div>
        ))}
      </div>
    </div>
  )
}
