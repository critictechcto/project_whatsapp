import { Container } from '../../../components/ui/Container'
import { Logo } from '../../../components/ui/Logo'
import { legalReady, sectionHref, site } from '../../../config/site'

type FooterLink = { label: string; href: string }

function footerColumns(): { title: string; links: FooterLink[] }[] {
  const company: FooterLink[] = [
    { label: 'Contact sales', href: `${site.links.contact}#sales` },
    { label: 'Support', href: `${site.links.contact}#support` },
  ]
  // The legal pages link only once their details are filled in (see `site.legal`).
  if (legalReady) {
    company.push(
      { label: 'Privacy policy', href: site.links.privacy },
      { label: 'Terms of service', href: site.links.terms },
    )
  }

  return [
    {
      title: 'Product',
      links: [
        { label: 'Features', href: sectionHref('product') },
        { label: 'How it works', href: sectionHref('how-it-works') },
        { label: 'Pricing', href: sectionHref('pricing') },
        { label: 'Use cases', href: sectionHref('use-cases') },
      ],
    },
    {
      title: 'Resources',
      links: [
        { label: 'Developers', href: sectionHref('developers') },
        { label: 'WhatsApp rules', href: sectionHref('rules') },
        { label: 'Setup requirements', href: sectionHref('requirements') },
        { label: 'FAQ', href: sectionHref('faq') },
      ],
    },
    { title: 'Company', links: company },
  ]
}

export function Footer() {
  const year = new Date().getFullYear()

  return (
    <footer className="border-t border-line bg-paper-2/60">
      <Container className="py-14 max-md:py-12">
        <div className="grid gap-10 md:grid-cols-12">
          <div className="md:col-span-5">
            <Logo />
            <p className="mt-4 max-w-sm text-[14.5px] leading-relaxed text-muted">
              WhatsApp campaigns, reminders and a shared inbox for Indian businesses — built on the official WhatsApp
              Business Platform.
            </p>
          </div>
          <nav aria-label="Footer" className="grid grid-cols-2 gap-8 sm:grid-cols-3 md:col-span-7">
            {footerColumns().map((column) => (
              <div key={column.title}>
                <h2 className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted max-md:text-[12px]">
                  {column.title}
                </h2>
                {/* On phones each link is a full 44 px row, so there is no extra spacing between them. */}
                <ul className="mt-4 space-y-2.5 text-[14.5px] max-md:mt-2 max-md:space-y-0">
                  {column.links.map((link) => (
                    <li key={link.label}>
                      <a href={link.href} className="hover:text-accent-2 max-md:flex max-md:min-h-11 max-md:items-center">
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
