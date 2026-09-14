import type { AnchorHTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'inverse' | 'outline-inverse'
type Size = 'sm' | 'md' | 'lg'

// Solid variants sit on a 2px edge (a hard bottom shadow) and sink onto it while pressed.
// The press itself is instant — only colours transition — so nothing but a transform changes.
const variants: Record<Variant, string> = {
  primary:
    'bg-ink text-paper hover:bg-ink-2 shadow-[inset_0_1px_0_rgb(255_255_255/0.12),0_2px_0_#06150f,0_10px_18px_-12px_rgb(16_39_31/0.7)] active:translate-y-0.5 active:shadow-[inset_0_1px_0_rgb(255_255_255/0.08),0_0_0_#06150f]',
  secondary:
    'border border-line bg-card text-ink hover:border-ink/40 shadow-[inset_0_1px_0_rgb(255_255_255/0.9),0_2px_0_var(--color-line)] active:translate-y-0.5 active:shadow-[inset_0_1px_0_rgb(255_255_255/0.9),0_0_0_var(--color-line)]',
  ghost: 'text-ink hover:bg-ink/5 active:translate-y-px',
  inverse:
    'bg-paper text-ink hover:bg-white shadow-[inset_0_1px_0_rgb(255_255_255/0.9),0_2px_0_#b9b09c] active:translate-y-0.5 active:shadow-[inset_0_1px_0_rgb(255_255_255/0.9),0_0_0_#b9b09c]',
  'outline-inverse': 'border border-paper/30 text-paper hover:border-paper/70 active:translate-y-px',
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
        'group inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-[color,background-color,border-color] duration-200',
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
