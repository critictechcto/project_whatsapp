import { useId, useState, type ReactNode } from 'react'
import { Plus } from 'lucide-react'
import { cn } from '../../lib/cn'

export type AccordionItem = { question: string; answer: ReactNode }

export function Accordion({ items }: { items: AccordionItem[] }) {
  const [open, setOpen] = useState<number | null>(0)
  const baseId = useId()

  return (
    <div className="divide-y divide-line border-y border-line">
      {items.map((item, i) => {
        const isOpen = open === i
        const buttonId = `${baseId}-button-${i}`
        const panelId = `${baseId}-panel-${i}`

        return (
          <div key={item.question}>
            <h3>
              <button
                id={buttonId}
                type="button"
                aria-expanded={isOpen}
                aria-controls={panelId}
                onClick={() => setOpen(isOpen ? null : i)}
                className="flex w-full items-center justify-between gap-6 py-5 text-left text-[16.5px] font-medium transition-colors hover:text-accent-2"
              >
                <span>{item.question}</span>
                <Plus
                  className={cn('size-5 shrink-0 text-muted transition-transform duration-300', isOpen && 'rotate-45')}
                  aria-hidden="true"
                />
              </button>
            </h3>
            <div
              id={panelId}
              role="region"
              aria-labelledby={buttonId}
              inert={!isOpen}
              className={cn(
                'grid transition-[grid-template-rows] duration-300 ease-out',
                isOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
              )}
            >
              <div className="overflow-hidden">
                <div className="max-w-2xl pb-6 pr-8 text-[15px] leading-relaxed text-muted">{item.answer}</div>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
