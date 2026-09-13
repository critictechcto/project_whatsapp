import type { AnchorHTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'inverse' | 'outline-inverse'
type Size = 'sm' | 'md' | 'lg'

const variants: Record<Variant, string> = {
  primary: 'bg-ink text-paper hover:bg-ink-2',
  secondary: 'border border-line bg-card text-ink hover:border-ink/40',
  ghost: 'text-ink hover:bg-ink/5',
  inverse: 'bg-paper text-ink hover:bg-white',
  'outline-inverse': 'border border-paper/30 text-paper hover:border-paper/70',
}

const sizes: Record<Size, string> = {
  sm: 'h-9 px-3.5 text-sm',
  md: 'h-11 px-5 text-[15px]',
  lg: 'h-12 px-6 text-[15px]',
}

type ButtonProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  variant?: Variant
  size?: Size
  children: ReactNode
}

export function Button({ variant = 'primary', size = 'md', className, children, ...props }: ButtonProps) {
  return (
    <a
      className={cn(
        'group inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-[color,background-color,border-color,translate] duration-200 active:translate-y-px',
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {children}
    </a>
  )
}
