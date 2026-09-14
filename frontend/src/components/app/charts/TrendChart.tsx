import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

export type TrendPoint = { label: string; value: number }

export type TrendChartProps = {
  data: readonly TrendPoint[]
  /** Accessible summary, e.g. "Messages delivered per day, last 7 days". */
  label: string
  height?: number
  valueFormatter?: (value: number) => string
}

/** Single-series area chart. Import through `LazyTrendChart` so recharts stays out of other chunks. */
export default function TrendChart({ data, label, height = 220, valueFormatter = (v) => v.toLocaleString('en-IN') }: TrendChartProps) {
  return (
    <div role="img" aria-label={label} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={[...data]} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid stroke="var(--color-line-2)" vertical={false} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: 'var(--color-muted)', fontSize: 12 }} />
          <YAxis tickLine={false} axisLine={false} tick={{ fill: 'var(--color-muted)', fontSize: 12 }} tickFormatter={valueFormatter} />
          <Tooltip
            formatter={(value) => valueFormatter(Number(value))}
            contentStyle={{ borderRadius: 8, borderColor: 'var(--color-line)', fontSize: 12 }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--color-accent)"
            strokeWidth={2}
            fill="var(--color-accent-soft)"
            isAnimationActive={!window.matchMedia('(prefers-reduced-motion: reduce)').matches}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
