import { lazy, Suspense, useEffect, useRef, useState, type CSSProperties, type RefObject } from 'react'
import { Container } from '../../../../components/ui/Container'
import { SectionHeader } from '../../../../components/ui/SectionHeader'
import { cn } from '../../../../lib/cn'
import { prefersReducedMotion } from '../../../../lib/motion'
import { useScrollProgress } from '../../lib/useScrollProgress'
import { STORY_CHAPTER_COUNT, storyChapters } from './storyChapters'

/*
 * "From first message to delivered order": a pinned scroll story in five chapters. Only the chapter
 * text and the scroll tracking live in this (landing entry) module. The visuals load when the section
 * comes near: `StoryStage` shows the CSS 3D stage and, on capable desktops, swaps in the three.js
 * scene. Reduced motion gets a static list with flat illustrations instead.
 */

const StoryStage = lazy(() => import('./StoryStage').then((module) => ({ default: module.StoryStage })))
const StoryStill = lazy(() => import('./StoryFallback').then((module) => ({ default: module.StoryStill })))

/** True once the element is within about a viewport of the screen (straight away without IntersectionObserver). */
function useNear(ref: RefObject<HTMLElement | null>) {
  const [near, setNear] = useState(() => typeof IntersectionObserver === 'undefined')

  useEffect(() => {
    const element = ref.current
    if (!element || near) return
    const observer = new IntersectionObserver(([entry]) => entry.isIntersecting && setNear(true), {
      rootMargin: '100% 0px',
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref, near])

  return near
}

const label = 'font-mono text-[11px] uppercase tracking-[0.14em] text-muted'
const title = 'font-display text-[1.3rem] font-semibold leading-[1.15] tracking-[-0.02em] lg:text-[1.4rem]'

function ChapterBody({ index }: { index: number }) {
  const { body, note } = storyChapters[index]
  return (
    <>
      <p className="pt-2 text-[15px] leading-relaxed text-muted">{body}</p>
      {note && <p className="pt-2 text-[12.5px] text-muted">{note}</p>}
    </>
  )
}

function PinnedStory() {
  const trackRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const { chapter, progressRef, subscribe } = useScrollProgress(trackRef, { count: STORY_CHAPTER_COUNT, stageRef })
  const near = useNear(trackRef)

  return (
    <div ref={trackRef} data-chapter={chapter} className="relative h-[400vh] [@media(max-height:640px)]:h-[300vh]">
      <div ref={stageRef} className="sticky top-16 h-[calc(100svh-4rem)] overflow-hidden">
        <Container className="flex h-full flex-col gap-4 py-6 lg:grid lg:grid-cols-12 lg:items-center lg:gap-10 lg:py-10">
          <div className="shrink-0 lg:col-span-5">
            {/* Small screens: a segmented rail above the current chapter */}
            <div className="mb-4 flex gap-1.5 lg:hidden" aria-hidden="true">
              {storyChapters.map((item, i) => (
                <span
                  key={item.label}
                  className={cn('h-1 flex-1 rounded-full transition-colors duration-500', i <= chapter ? 'bg-accent' : 'bg-line')}
                />
              ))}
            </div>

            <ol className="relative">
              <span aria-hidden="true" className="absolute inset-y-3 left-[11px] hidden w-px bg-line lg:block" />
              <span
                aria-hidden="true"
                className="absolute inset-y-3 left-[11px] hidden w-px origin-top bg-accent lg:block"
                style={{ transform: 'scaleY(var(--story-progress, 0))' } as CSSProperties}
              />
              {storyChapters.map((item, i) => {
                const state = i < chapter ? 'done' : i === chapter ? 'current' : 'upcoming'
                const current = state === 'current'
                return (
                  <li
                    key={item.label}
                    data-state={state}
                    aria-current={current ? 'step' : undefined}
                    className={cn('relative grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-4 lg:py-2.5', !current && 'max-lg:sr-only')}
                  >
                    <span
                      aria-hidden="true"
                      className={cn(
                        'mt-0.5 grid size-[23px] place-items-center rounded-full border font-mono text-[10px] transition-colors duration-500',
                        current ? 'border-accent bg-accent text-white' : 'bg-paper',
                        state === 'done' && 'border-accent text-accent-2',
                        state === 'upcoming' && 'border-line text-muted',
                      )}
                    >
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <div>
                      <p className={label}>{item.label}</p>
                      <h3 className={cn(title, 'mt-1 transition-colors duration-500', current ? 'text-ink' : 'text-muted')}>
                        {item.title}
                      </h3>
                      {/* Only the current chapter's body is open; the others stay in the DOM, collapsed. */}
                      <div
                        className={cn(
                          'grid transition-[grid-template-rows] duration-500',
                          current ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
                        )}
                      >
                        <div className="overflow-hidden">
                          <ChapterBody index={i} />
                        </div>
                      </div>
                    </div>
                  </li>
                )
              })}
            </ol>
          </div>

          <div className="relative min-h-[260px] flex-1 lg:col-span-7 lg:h-full">
            {near && (
              <Suspense fallback={null}>
                <StoryStage progressRef={progressRef} subscribe={subscribe} />
              </Suspense>
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
              <p className={label}>
                <span className="mr-3 text-accent-2">{String(i + 1).padStart(2, '0')}</span>
                {item.label}
              </p>
              <h3 className={cn(title, 'mt-3')}>{item.title}</h3>
              <ChapterBody index={i} />
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
