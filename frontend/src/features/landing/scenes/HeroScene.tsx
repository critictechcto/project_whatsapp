import { useRef, type CSSProperties, type ReactNode } from 'react'
import { CheckCheck, FileCheck } from 'lucide-react'
import { Badge } from '../../../components/ui/Badge'
import { usePointerTilt } from '../../../components/ui/usePointerTilt'
import { cn } from '../../../lib/cn'
import { useChatSequence } from '../lib/useChatSequence'
import { useOnScreen } from '../lib/useOnScreen'
import { CampaignMockup } from '../mockups/CampaignMockup'
import { InboxMockup } from '../mockups/InboxMockup'
import { PhoneMockup } from '../mockups/PhoneMockup'

type LayerProps = {
  /** Depth in px (sm and up). */
  z: number
  /** Unfold delay on load, in ms. */
  delay: number
  /** Idle float period in seconds; omit for a layer that doesn't float. */
  float?: number
  className?: string
  children: ReactNode
}

/** One depth plane of the scene. Positioning comes from `className`; depth and motion from index.css. */
function Layer({ z, delay, float, className, children }: LayerProps) {
  const style = {
    '--z': `${z}px`,
    '--delay': `${delay}ms`,
    '--float-duration': float ? `${float}s` : undefined,
  } as CSSProperties

  return (
    <div className={cn('hero-layer', className)} style={style}>
      {float ? <div className="hero-float">{children}</div> : children}
    </div>
  )
}

const cardShadow =
  'shadow-[inset_0_1px_0_rgb(255_255_255/0.9),0_1px_2px_rgb(16_39_31/0.06),0_18px_36px_-18px_rgb(16_39_31/0.35)]'

/**
 * Hero centrepiece: the team inbox and the customer's phone showing the same conversation, with
 * product cards floating at different depths. Phones get only the inbox with the template card on its
 * corner, so the hero stays short; sm and up get the full 3D scene,
 * with pointer tilt on devices that hover. Entirely decorative.
 */
export function HeroScene() {
  const step = useChatSequence()
  const stageRef = useRef<HTMLDivElement>(null)
  const onScreen = useOnScreen(stageRef)
  const tiltRef = usePointerTilt<HTMLDivElement>({ max: 8, track: 'section' })

  return (
    <div
      ref={stageRef}
      aria-hidden="true"
      data-paused={onScreen ? undefined : ''}
      className="hero-stage relative sm:mx-auto sm:h-[656px] sm:max-w-[680px] lg:max-w-none"
    >
      <div ref={tiltRef} className="hero-tilt">
        <div className="hero-scene">
          <div className="hero-shadow hidden sm:block" />

          <Layer z={0} delay={0} className="sm:absolute sm:left-16 sm:right-0 sm:top-6">
            <InboxMockup step={step} className="shadow-[0_1px_0_rgba(16,39,31,0.04),0_50px_80px_-40px_rgba(16,39,31,0.4)]" />
          </Layer>

          <Layer z={90} delay={180} float={7} className="hidden sm:absolute sm:left-0 sm:top-[112px] sm:block sm:w-[208px]">
            <PhoneMockup
              step={step}
              className="h-[428px] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14),inset_0_1px_0_rgb(255_255_255/0.22),0_40px_60px_-28px_rgb(16_39_31/0.55),0_14px_24px_-14px_rgb(16_39_31/0.35)]"
            />
          </Layer>

          <Layer
            z={60}
            delay={300}
            float={8.5}
            className="hidden sm:absolute sm:-right-3 sm:top-[420px] sm:block sm:w-[320px]"
          >
            <CampaignMockup />
          </Layer>

          <Layer
            z={130}
            delay={420}
            float={6.5}
            className="absolute -top-5 right-3 sm:left-6 sm:right-auto sm:top-[574px]"
          >
            <div className={cn('flex items-center gap-2.5 rounded-lg border border-line bg-card px-3 py-2', cardShadow)}>
              <span className="grid size-7 place-items-center rounded-md bg-accent-soft text-accent-2">
                <FileCheck className="size-3.5" />
              </span>
              <div>
                <p className="font-mono text-[11px] leading-tight">order_shipped</p>
                <p className="text-[10px] leading-tight text-muted">Utility template</p>
              </div>
              <Badge tone="green" className="ml-1">
                Approved
              </Badge>
            </div>
          </Layer>

          <Layer z={160} delay={540} float={7.5} className="hidden sm:absolute sm:left-[150px] sm:top-[486px] sm:block">
            <div
              className={cn(
                'flex items-center gap-1.5 rounded-full border border-line bg-card px-2.5 py-1.5 text-[11px]',
                cardShadow,
              )}
            >
              <CheckCheck className="size-3.5 text-[#2f7fc1]" />
              <span className="font-medium">Read</span>
              <span className="font-mono text-[10px] text-muted">10:42</span>
            </div>
          </Layer>
        </div>
      </div>
    </div>
  )
}
