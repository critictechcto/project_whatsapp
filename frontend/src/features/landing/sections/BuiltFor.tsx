import { Container } from '../../../components/ui/Container'

const industries = [
  'D2C & e-commerce',
  'Clinics & diagnostics',
  'Coaching & schools',
  'Real estate',
  'Restaurants & cloud kitchens',
  'Travel & hospitality',
  'Local retail',
]

export function BuiltFor() {
  return (
    <section aria-label="Industries we serve" className="border-y border-line bg-paper-2/60">
      <Container className="flex flex-col gap-4 py-7 md:flex-row md:items-center md:gap-10">
        <p className="shrink-0 font-mono text-[11px] uppercase tracking-[0.16em] text-muted max-md:text-[12px] max-md:tracking-[0.14em]">Built for</p>
        <ul className="flex flex-wrap gap-x-4 gap-y-2 text-[14.5px] sm:gap-x-5 sm:text-[15px]">
          {industries.map((industry) => (
            <li
              key={industry}
              className="flex items-center gap-2 before:size-1 before:rounded-full before:bg-accent/60 before:content-[''] after:text-line sm:gap-5 sm:before:hidden sm:after:content-['/'] sm:last:after:content-none"
            >
              {industry}
            </li>
          ))}
        </ul>
      </Container>
    </section>
  )
}
