import { useCallback, useEffect, useState, type ComponentType, type RefObject } from 'react'
import { canUseWebGLStory } from '../../../../lib/webglSupport'
import type { ScrollProgressListener } from '../../lib/useScrollProgress'
import { StoryFallback } from './StoryFallback'
import type { StoryCanvasProps } from './webgl/StoryCanvas'

type StoryStageProps = {
  progressRef: RefObject<number>
  subscribe: (listener: ScrollProgressListener) => () => void
}

/**
 * The visual half of the pinned story, loaded when the section comes within about a viewport. Shows
 * the CSS 3D stage straight away and, on capable desktops (`canUseWebGLStory`), loads the three.js
 * scene in the background. The canvas replaces the CSS stage once its first frame is drawn, and hands
 * back to it if WebGL fails or the context is lost.
 */
export function StoryStage({ progressRef, subscribe }: StoryStageProps) {
  const [Canvas, setCanvas] = useState<ComponentType<StoryCanvasProps> | null>(null)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    // No IntersectionObserver means an old browser or jsdom: keep the CSS stage.
    if (failed || typeof IntersectionObserver === 'undefined' || !canUseWebGLStory()) return
    let cancelled = false
    import('./webgl/StoryCanvas')
      .then((module) => {
        if (!cancelled) setCanvas(() => module.StoryCanvas)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [failed])

  const onReady = useCallback(() => setReady(true), [])
  const onContextLost = useCallback(() => {
    setFailed(true)
    setReady(false)
  }, [])

  const showCanvas = Canvas !== null && !failed

  return (
    <>
      {!(showCanvas && ready) && <StoryFallback />}
      {showCanvas && (
        <Canvas
          progressRef={progressRef}
          subscribe={subscribe}
          onReady={onReady}
          onContextLost={onContextLost}
          className={ready ? 'opacity-100' : 'opacity-0'}
        />
      )}
    </>
  )
}
