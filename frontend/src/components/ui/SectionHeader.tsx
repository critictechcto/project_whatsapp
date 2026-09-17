import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { Reveal } from './Reveal'
import { SplitReveal } from './SplitReveal'

type SectionHeaderProps = {
  index: string
  eyebrow: string
  title: ReactNode
  description?: ReactNode
  inverse?: boolean
  className?: string
}

export function SectionHeader({ index, eyebrow, title, description, inverse, className }: SectionHeaderProps) {
  return (
    <Reveal className={cn('max-w-3xl', className)}>
      <p
        className={cn(
          'flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.16em] max-md:text-[12px] max-md:tracking-[0.14em]',
          inverse ? 'text-paper/65' : 'text-muted',
        )}
      >
        <span className={inverse ? 'text-paper' : 'text-accent-2'}>{index}</span>
        <span className={cn('h-px w-8', inverse ? 'bg-paper/25' : 'bg-line')} aria-hidden="true" />
        {eyebrow}
      </p>
      <SplitReveal className="mt-5 font-display text-[2.1rem] font-semibold leading-[1.06] tracking-[-0.03em] text-balance md:text-[2.9rem]">
        {title}
      </SplitReveal>
      {description && (
        <p className={cn('mt-5 max-w-2xl text-[17px] leading-relaxed', inverse ? 'text-paper/70' : 'text-muted')}>
          {description}
        </p>
      )}
    </Reveal>
  )
}
