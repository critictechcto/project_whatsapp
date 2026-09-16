import { useEffect, useState } from 'react'
import { Menu, X } from 'lucide-react'
import { Button } from '../../../components/ui/Button'
import { MagneticButton } from '../../../components/ui/MagneticButton'
import { Container } from '../../../components/ui/Container'
import { Logo } from '../../../components/ui/Logo'
import { isLandingPath, sectionHref, site } from '../../../config/site'
import { cn } from '../../../lib/cn'

const navIds: string[] = site.nav.map((item) => item.id)

/**
 * The id of the nav section crossing a band just above the middle of the viewport, or null. Observes
 * only when `enabled` (the landing page). State changes only when the active section changes, so
 * scrolling does not re-render the navbar.
 */
function useActiveSection(enabled: boolean) {
  const [active, setActive] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled || typeof IntersectionObserver === 'undefined') return
    const sections = navIds
      .map((id) => document.getElementById(id))
      .filter((element): element is HTMLElement => element !== null)
    if (sections.length === 0) return

    const visible = new Set<string>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) visible.add(entry.target.id)
          else visible.delete(entry.target.id)
        }
        setActive(navIds.find((id) => visible.has(id)) ?? null)
      },
      { rootMargin: '-40% 0px -55% 0px' },
    )
    sections.forEach((section) => observer.observe(section))
    return () => observer.disconnect()
  }, [enabled])

  return active
}

export function Navbar() {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const onLanding = isLandingPath()
  const active = useActiveSection(onLanding)

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
        <a href={onLanding ? '#top' : import.meta.env.BASE_URL} aria-label={`${site.name} home`}>
          <Logo />
        </a>

        <nav aria-label="Primary" className="hidden lg:block">
          <ul className="flex items-center gap-7">
            {site.nav.map((item) => {
              const current = active === item.id
              return (
                <li key={item.id}>
                  <a
                    href={sectionHref(item.id)}
                    aria-current={current ? 'true' : undefined}
                    className={cn(
                      'relative text-[14px] transition-colors hover:text-ink',
                      current
                        ? 'text-ink after:absolute after:inset-x-0 after:-bottom-1.5 after:h-px after:bg-accent'
                        : 'text-muted',
                    )}
                  >
                    {item.label}
                  </a>
                </li>
              )
            })}
          </ul>
        </nav>

        <div className="hidden items-center gap-2 lg:flex">
          <Button href={site.links.login} variant="ghost" size="sm">
            Log in
          </Button>
          <MagneticButton href={site.links.signup} size="sm" max={6}>
            Start free trial
          </MagneticButton>
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
                  <li key={item.id} className="border-b border-line-2">
                    <a
                      href={sectionHref(item.id)}
                      aria-current={active === item.id ? 'true' : undefined}
                      onClick={() => setOpen(false)}
                      className={cn('block py-3.5 text-[16px]', active === item.id && 'text-accent-2')}
                    >
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
