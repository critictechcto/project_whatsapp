import { useEffect, useRef, type RefObject } from 'react'
import { cn } from '../../../../../lib/cn'
import type { ScrollProgressListener } from '../../../lib/useScrollProgress'
import { useOnScreen } from '../../../lib/useOnScreen'
import { createStoryScene, type StoryScene } from './scene'

export type StoryCanvasProps = {
  progressRef: RefObject<number>
  subscribe: (listener: ScrollProgressListener) => () => void
  /** Called once the first frame (with brand fonts) is on the canvas. */
  onReady: () => void
  /** Called when WebGL is unavailable or the context is lost; the caller shows the CSS stage. */
  onContextLost: () => void
  className?: string
}

/**
 * The lazily loaded WebGL stage. Owns the renderer's lifecycle: resize, pointer parallax (fine
 * pointers only), pausing while offscreen or in a hidden tab, and disposal on unmount.
 */
export function StoryCanvas({ progressRef, subscribe, onReady, onContextLost, className }: StoryCanvasProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sceneRef = useRef<StoryScene | null>(null)
  const onScreen = useOnScreen(wrapRef, '0px')
  const callbacks = useRef({ onReady, onContextLost })
  const active = useRef(onScreen)

  useEffect(() => {
    callbacks.current = { onReady, onContextLost }
  }, [onReady, onContextLost])

  useEffect(() => {
    active.current = onScreen
    sceneRef.current?.setActive(onScreen)
  }, [onScreen])

  useEffect(() => {
    const wrap = wrapRef.current
    const canvas = canvasRef.current
    if (!wrap || !canvas) return

    let scene: StoryScene
    try {
      scene = createStoryScene(canvas, { onContextLost: () => callbacks.current.onContextLost() })
    } catch {
      callbacks.current.onContextLost()
      return
    }
    sceneRef.current = scene
    let disposed = false

    scene.resize(wrap.clientWidth, wrap.clientHeight)
    scene.setProgress(progressRef.current ?? 0)
    scene.setActive(active.current)
    const unsubscribe = subscribe((progress) => scene.setProgress(progress))
    scene.ready.then(() => {
      if (!disposed) callbacks.current.onReady()
    })

    const resizeObserver = new ResizeObserver(() => scene.resize(wrap.clientWidth, wrap.clientHeight))
    resizeObserver.observe(wrap)

    const area = wrap.closest('section') ?? wrap
    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches
    const onMove = (event: PointerEvent) => {
      if (event.pointerType !== 'mouse' && event.pointerType !== 'pen') return
      const rect = wrap.getBoundingClientRect()
      const x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      const y = ((event.clientY - rect.top) / rect.height) * 2 - 1
      scene.setPointer(Math.max(-1, Math.min(1, x)), Math.max(-1, Math.min(1, y)))
    }
    const onLeave = () => scene.setPointer(0, 0)
    if (finePointer) {
      area.addEventListener('pointermove', onMove, { passive: true })
      area.addEventListener('pointerleave', onLeave)
    }

    return () => {
      disposed = true
      unsubscribe()
      resizeObserver.disconnect()
      area.removeEventListener('pointermove', onMove)
      area.removeEventListener('pointerleave', onLeave)
      scene.dispose()
      sceneRef.current = null
    }
  }, [progressRef, subscribe])

  return (
    <div
      ref={wrapRef}
      aria-hidden="true"
      className={cn('absolute inset-0 transition-opacity duration-700 ease-[var(--ease-soft)]', className)}
    >
      <canvas ref={canvasRef} className="block size-full" />
    </div>
  )
}
