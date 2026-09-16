import { useId, useState, type ReactNode } from 'react'
import { Plus } from 'lucide-react'
import './Accordion.css'

export type AccordionItem = { question: string; answer: ReactNode }

/**
 * Disclosure list with one open item at a time. Height animates with `grid-template-rows: 0fr → 1fr`,
 * so answers of any length open smoothly without measuring; closed panels are `inert`.
 */
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
                  data-open={isOpen}
                  className="accordion-icon size-5 shrink-0 text-muted"
                  aria-hidden="true"
                />
              </button>
            </h3>
            <div
              id={panelId}
              role="region"
              aria-labelledby={buttonId}
              inert={!isOpen}
              data-open={isOpen}
              className="accordion-panel"
            >
              <div>
                <div className="accordion-body max-w-2xl pb-6 pr-8 text-[15px] leading-relaxed text-muted">
                  {item.answer}
                </div>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
