import { useEffect, useRef, type ComponentProps } from 'react'
import { cn } from '../../lib/cn'
import { Button } from './Button'
import { canPointerTilt } from './usePointerTilt'
import './MagneticButton.css'

type MagneticButtonProps = ComponentProps<typeof Button> & {
  /** How far the button follows the pointer, as a share of the pointer's distance from its centre. */
  strength?: number
  /** Largest offset in px on each axis. */
  max?: number
  /**
   * Classes for the wrapping `<span>` (default `inline-flex`); pass layout such as `flex mt-7` here.
   * `className` still goes to the link.
   */
  wrapperClassName?: string
}

/**
 * A `Button` (an `<a>`) that leans slightly towards a hovering mouse and springs back when it leaves.
 *
 * Pointer moves are throttled to one per animation frame and written to CSS variables on a wrapping
 * `<span>`, so hovering never re-renders. Touch devices and reduced-motion users get a plain Button.
 */
export function MagneticButton({ strength = 0.3, max = 10, wrapperClassName, ...buttonProps }: MagneticButtonProps) {
  const ref = useRef<HTMLSpanElement | null>(null)

  useEffect(() => {
    const wrapper = ref.current
    if (!wrapper || !canPointerTilt()) return

    let frame = 0
    let pointer: { x: number; y: number } | null = null

    const apply = () => {
      frame = 0
      if (!pointer) return
      const rect = wrapper.getBoundingClientRect()
      const clamp = (value: number) => Math.max(-max, Math.min(max, value))
      const x = clamp((pointer.x - (rect.left + rect.width / 2)) * strength)
      const y = clamp((pointer.y - (rect.top + rect.height / 2)) * strength)
      wrapper.style.setProperty('--magnetic-x', `${x.toFixed(1)}px`)
      wrapper.style.setProperty('--magnetic-y', `${y.toFixed(1)}px`)
    }
    const onMove = (event: PointerEvent) => {
      if (event.pointerType !== 'mouse' && event.pointerType !== 'pen') return
      wrapper.dataset.magnetic = 'active'
      pointer = { x: event.clientX, y: event.clientY }
      if (!frame) frame = requestAnimationFrame(apply)
    }
    const onLeave = () => {
      cancelAnimationFrame(frame)
      frame = 0
      pointer = null
      delete wrapper.dataset.magnetic
      wrapper.style.setProperty('--magnetic-x', '0px')
      wrapper.style.setProperty('--magnetic-y', '0px')
    }

    wrapper.addEventListener('pointermove', onMove)
    wrapper.addEventListener('pointerleave', onLeave)
    return () => {
      cancelAnimationFrame(frame)
      wrapper.removeEventListener('pointermove', onMove)
      wrapper.removeEventListener('pointerleave', onLeave)
    }
  }, [strength, max])

  return (
    <span ref={ref} className={cn('magnetic', wrapperClassName ?? 'inline-flex')}>
      <Button {...buttonProps} />
    </span>
  )
}
