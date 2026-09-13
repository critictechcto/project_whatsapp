import { useEffect, useState } from 'react'
import { Menu, X } from 'lucide-react'
import { Button } from '../../../components/ui/Button'
import { Container } from '../../../components/ui/Container'
import { Logo } from '../../../components/ui/Logo'
import { site } from '../../../config/site'
import { cn } from '../../../lib/cn'

export function Navbar() {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      className={cn(
        'sticky top-0 z-50 border-b transition-colors',
        scrolled || open ? 'border-line bg-paper/90 backdrop-blur-md' : 'border-transparent bg-paper',
      )}
    >
      <Container className="flex h-16 items-center justify-between gap-6">
        <a href="#top" aria-label={`${site.name} home`}>
          <Logo />
        </a>

        <nav aria-label="Primary" className="hidden lg:block">
          <ul className="flex items-center gap-7">
            {site.nav.map((item) => (
              <li key={item.href}>
                <a href={item.href} className="text-[14px] text-muted transition-colors hover:text-ink">
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="hidden items-center gap-2 lg:flex">
          <Button href={site.links.login} variant="ghost" size="sm">
            Log in
          </Button>
          <Button href={site.links.signup} size="sm">
            Start free trial
          </Button>
        </div>

        <button
          type="button"
          className="grid size-10 place-items-center rounded-md hover:bg-ink/5 lg:hidden"
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </Container>

      {open && (
        <div id="mobile-nav" className="menu-down border-t border-line lg:hidden">
          <Container className="pb-5 pt-2">
            <nav aria-label="Mobile">
              <ul>
                {site.nav.map((item) => (
                  <li key={item.href} className="border-b border-line-2">
                    <a href={item.href} onClick={() => setOpen(false)} className="block py-3.5 text-[16px]">
                      {item.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
            <div className="mt-5 grid grid-cols-2 gap-2">
              <Button href={site.links.login} variant="secondary">
                Log in
              </Button>
              <Button href={site.links.signup}>Start free trial</Button>
            </div>
          </Container>
        </div>
      )}
    </header>
  )
}
