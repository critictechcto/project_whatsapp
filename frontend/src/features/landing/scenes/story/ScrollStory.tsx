import { lazy, Suspense, useCallback, useEffect, useRef, useState, type ComponentType, type CSSProperties, type RefObject } from 'react'
import { Container } from '../../../../components/ui/Container'
import { SectionHeader } from '../../../../components/ui/SectionHeader'
import { cn } from '../../../../lib/cn'
import { prefersReducedMotion } from '../../../../lib/motion'
import { canUseWebGLStory } from '../../../../lib/webglSupport'
import { useScrollProgress } from '../../lib/useScrollProgress'
import { STORY_CHAPTER_COUNT, storyChapters } from './storyChapters'
import type { StoryCanvasProps } from './webgl/StoryCanvas'

/*
 * "From first message to delivered order": a pinned scroll story in five chapters. The chapter text is
 * real DOM text in this (entry) chunk. The visuals load separately when the section comes near:
 * the CSS 3D stage (`StoryFallback`) for everyone, then — on capable desktops only — the three.js
 * scene (`webgl/StoryCanvas`), which replaces the CSS stage once its first frame is drawn and hands
 * back to it if the WebGL context is lost. Reduced motion gets a static list of the chapters.
 */

const StoryFallback = lazy(() => import('./StoryFallback').then((module) => ({ default: module.StoryFallback })))
const StoryStill = lazy(() => import('./StoryFallback').then((module) => ({ default: module.StoryStill })))

/** True once the element is within about a viewport of the screen (straight away without IntersectionObserver). */
function useNear(ref: RefObject<HTMLElement | null>) {
  const [near, setNear] = useState(() => typeof IntersectionObserver === 'undefined')

  useEffect(() => {
    const element = ref.current
    if (!element || near) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setNear(true)
          observer.disconnect()
        }
      },
      { rootMargin: '100% 0px' },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref, near])

  return near
}

function ChapterNumber({ index }: { index: number }) {
  return <>{String(index + 1).padStart(2, '0')}</>
}

function PinnedStory() {
  const trackRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const { chapter, progressRef, subscribe } = useScrollProgress(trackRef, { count: STORY_CHAPTER_COUNT, stageRef })
  const near = useNear(trackRef)

  const [Canvas, setCanvas] = useState<ComponentType<StoryCanvasProps> | null>(null)
  const [webglReady, setWebglReady] = useState(false)
  const [webglFailed, setWebglFailed] = useState(false)

  useEffect(() => {
    // No IntersectionObserver means an old browser or jsdom: keep the CSS stage.
    if (!near || webglFailed || typeof IntersectionObserver === 'undefined' || !canUseWebGLStory()) return
    let cancelled = false
    import('./webgl/StoryCanvas')
      .then((module) => {
        if (!cancelled) setCanvas(() => module.StoryCanvas)
      })
      .catch(() => {
        if (!cancelled) setWebglFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [near, webglFailed])

  const onReady = useCallback(() => setWebglReady(true), [])
  const onContextLost = useCallback(() => {
    setWebglFailed(true)
    setWebglReady(false)
  }, [])

  const showCanvas = Canvas !== null && !webglFailed
  const showFallback = near && !(showCanvas && webglReady)

  return (
    <div
      ref={trackRef}
      data-chapter={chapter}
      className="relative h-[400vh] [@media(max-height:640px)]:h-[300vh]"
    >
      <div ref={stageRef} className="sticky top-16 h-[calc(100svh-4rem)] overflow-hidden">
        <Container className="flex h-full flex-col gap-4 py-6 lg:grid lg:grid-cols-12 lg:items-center lg:gap-10 lg:py-10">
          <div className="shrink-0 lg:col-span-5">
            {/* Small screens: a segmented rail above the current chapter */}
            <div className="flex gap-1.5 lg:hidden" aria-hidden="true">
              {storyChapters.map((item, i) => (
                <span
                  key={item.label}
                  className={cn('h-1 flex-1 rounded-full transition-colors duration-500', i <= chapter ? 'bg-accent' : 'bg-line')}
                />
              ))}
            </div>

            <ol className="relative mt-4 lg:mt-0">
              <span aria-hidden="true" className="absolute bottom-3 left-[11px] top-3 hidden w-px bg-line lg:block" />
              <span
                aria-hidden="true"
                className="absolute bottom-3 left-[11px] top-3 hidden w-px origin-top bg-accent lg:block"
                style={{ transform: 'scaleY(var(--story-progress, 0))' } as CSSProperties}
              />
              {storyChapters.map((item, i) => {
                const state = i < chapter ? 'done' : i === chapter ? 'current' : 'upcoming'
                return (
                  <li
                    key={item.label}
                    data-state={state}
                    aria-current={state === 'current' ? 'step' : undefined}
                    className={cn(
                      'relative grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-4 lg:py-2.5',
                      state !== 'current' && 'max-lg:sr-only',
                    )}
                  >
                    <span
                      aria-hidden="true"
                      className={cn(
                        'mt-0.5 grid size-[23px] place-items-center rounded-full border font-mono text-[10px] transition-colors duration-500',
                        state === 'current' && 'border-accent bg-accent text-white',
                        state === 'done' && 'border-accent bg-paper text-accent-2',
                        state === 'upcoming' && 'border-line bg-paper text-muted',
                      )}
                    >
                      <ChapterNumber index={i} />
                    </span>
                    <div>
                      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">{item.label}</p>
                      <h3
                        className={cn(
                          'mt-1 font-display text-[1.3rem] font-semibold leading-[1.15] tracking-[-0.02em] transition-colors duration-500 lg:text-[1.4rem]',
                          state === 'current' ? 'text-ink' : 'text-muted',
                        )}
                      >
                        {item.title}
                      </h3>
                      <div
                        className={cn(
                          'grid transition-[grid-template-rows] duration-500 ease-[var(--ease-soft)]',
                          state === 'current' ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
                        )}
                      >
                        <div className="overflow-hidden">
                          <p className="pt-2 text-[15px] leading-relaxed text-muted">{item.body}</p>
                          {item.note && <p className="pt-2 text-[12.5px] text-muted">{item.note}</p>}
                        </div>
                      </div>
                    </div>
                  </li>
                )
              })}
            </ol>
          </div>

          <div className="relative min-h-[260px] flex-1 lg:col-span-7 lg:h-full">
            {showFallback && (
              <Suspense fallback={null}>
                <StoryFallback />
              </Suspense>
            )}
            {showCanvas && (
              <Canvas
                progressRef={progressRef}
                subscribe={subscribe}
                onReady={onReady}
                onContextLost={onContextLost}
                className={webglReady ? 'opacity-100' : 'opacity-0'}
              />
            )}
          </div>
        </Container>
      </div>
    </div>
  )
}

/** Reduced motion: every chapter at once, no pinning and no animation. */
function StaticStory() {
  return (
    <Container>
      <ol className="mt-14 grid gap-px overflow-hidden rounded-xl border border-line bg-line">
        {storyChapters.map((item, i) => (
          <li key={item.label} className="grid gap-6 bg-card p-6 md:grid-cols-12 md:gap-10">
            <div className="md:col-span-7">
              <p className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
                <span className="text-accent-2">
                  <ChapterNumber index={i} />
                </span>
                {item.label}
              </p>
              <h3 className="mt-3 font-display text-[1.4rem] font-semibold leading-[1.15] tracking-[-0.02em]">
                {item.title}
              </h3>
              <p className="mt-2 text-[15px] leading-relaxed text-muted">{item.body}</p>
              {item.note && <p className="mt-2 text-[12.5px] text-muted">{item.note}</p>}
            </div>
            <div className="md:col-span-5">
              <Suspense fallback={null}>
                <StoryStill chapter={i} />
              </Suspense>
            </div>
          </li>
        ))}
      </ol>
    </Container>
  )
}

export function ScrollStory() {
  const [reduced] = useState(prefersReducedMotion)

  return (
    <section id="story" data-story-mode={reduced ? 'static' : 'pinned'} className="border-b border-line py-20 md:py-28">
      <Container>
        <SectionHeader
          index="03"
          eyebrow="One order, start to finish"
          title="From first message to delivered order."
          description="Follow a sample order at Sharma Sweets: the campaign that starts it, the chat where the buyer shops and pays, and the alert that gets it shipped."
        />
      </Container>
      {reduced ? <StaticStory /> : <PinnedStory />}
    </section>
  )
}
