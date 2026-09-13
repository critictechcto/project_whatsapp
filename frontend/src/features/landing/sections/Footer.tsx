import { Container } from '../../../components/ui/Container'
import { Logo } from '../../../components/ui/Logo'
import { site } from '../../../config/site'

const columns = [
  {
    title: 'Product',
    links: [
      { label: 'Features', href: '#product' },
      { label: 'How it works', href: '#how-it-works' },
      { label: 'Pricing', href: '#pricing' },
      { label: 'Use cases', href: '#use-cases' },
    ],
  },
  {
    title: 'Resources',
    links: [
      { label: 'Developers', href: '#developers' },
      { label: 'WhatsApp rules', href: '#rules' },
      { label: 'Setup requirements', href: '#requirements' },
      { label: 'FAQ', href: '#faq' },
    ],
  },
  {
    title: 'Company',
    links: [
      { label: 'Contact sales', href: site.links.contactSales },
      { label: 'Support', href: `mailto:${site.email.support}` },
      { label: 'Privacy policy', href: '#' },
      { label: 'Terms of service', href: '#' },
    ],
  },
]

export function Footer() {
  const year = new Date().getFullYear()

  return (
    <footer className="border-t border-line bg-paper-2/60">
      <Container className="py-14">
        <div className="grid gap-10 md:grid-cols-12">
          <div className="md:col-span-5">
            <Logo />
            <p className="mt-4 max-w-sm text-[14.5px] leading-relaxed text-muted">
              WhatsApp campaigns, reminders and a shared inbox for Indian businesses — built on the official WhatsApp
              Business Platform.
            </p>
          </div>
          <nav aria-label="Footer" className="grid grid-cols-2 gap-8 sm:grid-cols-3 md:col-span-7">
            {columns.map((column) => (
              <div key={column.title}>
                <h2 className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">{column.title}</h2>
                <ul className="mt-4 space-y-2.5 text-[14.5px]">
                  {column.links.map((link) => (
                    <li key={link.label}>
                      <a href={link.href} className="hover:text-accent-2">
                        {link.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-line pt-6 text-[13px] text-muted md:flex-row md:justify-between">
          <p>
            © {year} {site.name}. All rights reserved.
          </p>
          <p className="max-w-xl md:text-right">
            WhatsApp is a trademark of Meta Platforms, Inc. {site.name} is an independent product and is not affiliated
            with or endorsed by Meta.
          </p>
        </div>
      </Container>
    </footer>
  )
}
