import { Check, Lock } from 'lucide-react'
import { cn } from '../../../lib/cn'
import { Window } from './Window'

const steps = [
  { label: 'Log in with Facebook', detail: 'Signed in directly with Meta', state: 'done' },
  { label: 'Choose a business portfolio', detail: 'Sharma Retail Pvt Ltd', state: 'done' },
  { label: 'Create WhatsApp Business Account', detail: 'Sharma Retail — WhatsApp', state: 'done' },
  { label: 'Add and verify phone number', detail: 'Code sent by SMS to +91 98XXX 41207', state: 'active' },
  { label: 'Set display name', detail: 'Shown to customers after Meta review', state: 'todo' },
] as const

export function EmbeddedSignupMockup() {
  return (
    <Window
      title="Meta Embedded Signup · secure popup"
      right={
        <span className="flex items-center gap-1 font-mono text-[10px] text-muted">
          <Lock className="size-3" />
          HTTPS
        </span>
      }
    >
      <ol className="px-5 py-4">
        {steps.map((step, i) => (
          <li key={step.label} className="relative flex gap-4 pb-4 last:pb-0">
            {i < steps.length - 1 && (
              <span
                className={cn(
                  'absolute left-[11px] top-7 h-[calc(100%-1.75rem)] w-px',
                  step.state === 'done' ? 'bg-accent/50' : 'bg-line',
                )}
              />
            )}
            <span
              className={cn(
                'grid size-6 shrink-0 place-items-center rounded-full border text-[11px] font-medium',
                step.state === 'done' && 'border-accent bg-accent text-white',
                step.state === 'active' && 'border-ink bg-card text-ink',
                step.state === 'todo' && 'border-line bg-card text-muted',
              )}
            >
              {step.state === 'done' ? <Check className="size-3.5" /> : i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className={cn('text-[13px] font-medium', step.state === 'todo' && 'text-muted')}>{step.label}</p>
              <p className="mt-0.5 truncate text-[11.5px] text-muted">{step.detail}</p>
              {step.state === 'active' && (
                <div className="mt-2.5 flex gap-1.5">
                  {['4', '8', '2', '', '', ''].map((digit, d) => (
                    <span
                      key={d}
                      className={cn(
                        'grid h-9 w-8 place-items-center rounded-md border bg-white font-mono text-[14px]',
                        d === 3 ? 'border-ink' : 'border-line',
                      )}
                    >
                      {digit || (d === 3 && <span className="caret h-4 w-px bg-ink" />)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </Window>
  )
}
