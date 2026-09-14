import { Dialog } from '../../../../components/app/Dialog'

const rows: [string[], string][] = [
  [['j'], 'Next conversation'],
  [['k'], 'Previous conversation'],
  [['/'], 'Search conversations'],
  [['r'], 'Focus the reply box'],
  [['Enter'], 'Send (in the reply box)'],
  [['Shift', 'Enter'], 'New line (in the reply box)'],
  [['?'], 'Show these shortcuts'],
]

export function ShortcutsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="sm" title="Keyboard shortcuts" description="Single-key shortcuts work when you're not typing.">
      <dl className="flex flex-col divide-y divide-line-2 text-sm">
        {rows.map(([keys, label]) => (
          <div key={label} className="flex items-center justify-between gap-4 py-2">
            <dt className="text-ink-2">{label}</dt>
            <dd className="flex gap-1">
              {keys.map((key) => (
                <kbd key={key} className="rounded border border-line bg-paper px-1.5 py-0.5 font-mono text-[12px] text-ink">
                  {key}
                </kbd>
              ))}
            </dd>
          </div>
        ))}
      </dl>
    </Dialog>
  )
}
