import { useEffect, type ReactNode } from 'react'
import { Container } from '../../components/ui/Container'
import { Footer } from '../landing/sections/Footer'
import { Navbar } from '../landing/sections/Navbar'

type PageLayoutProps = {
  /** Document title, without the brand suffix. */
  title: string
  description: string
  eyebrow: string
  heading: string
  lead?: ReactNode
  /** Rendered between the heading and the body, e.g. the legal details panel. */
  aside?: ReactNode
  /** Adds `<meta name="robots" content="noindex">` while the page is mounted. */
  noindex?: boolean
  children: ReactNode
}

function useDocumentMeta(title: string, description: string, noindex: boolean) {
  useEffect(() => {
    const previousTitle = document.title
    document.title = title

    let descriptionTag = document.querySelector<HTMLMetaElement>('meta[name="description"]')
    const previousDescription = descriptionTag?.content
    const createdDescription = !descriptionTag
    if (!descriptionTag) {
      descriptionTag = document.createElement('meta')
      descriptionTag.name = 'description'
      document.head.appendChild(descriptionTag)
    }
    descriptionTag.content = description

    let robots: HTMLMetaElement | null = null
    if (noindex) {
      robots = document.createElement('meta')
      robots.name = 'robots'
      robots.content = 'noindex'
      document.head.appendChild(robots)
    }

    return () => {
      document.title = previousTitle
      if (createdDescription) descriptionTag.remove()
      else descriptionTag.content = previousDescription ?? ''
      robots?.remove()
    }
  }, [title, description, noindex])
}

/** The page loads after a full navigation: start at the top, or at the linked section once it exists. */
function useInitialScroll() {
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.slice(1))
    const target = id ? document.getElementById(id) : null
    if (target) target.scrollIntoView()
    else if (window.scrollY > 0) window.scrollTo(0, 0)
  }, [])
}

export function PageLayout({
  title,
  description,
  eyebrow,
  heading,
  lead,
  aside,
  noindex = false,
  children,
}: PageLayoutProps) {
  useDocumentMeta(title, description, noindex)
  useInitialScroll()

  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-ink focus:px-4 focus:py-2 focus:text-paper"
      >
        Skip to content
      </a>
      <Navbar />
      <main id="main">
        <Container className="py-16 md:py-24">
          <div className="max-w-[46rem]">
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted">{eyebrow}</p>
            <h1 className="mt-5 font-display text-[2.3rem] font-semibold leading-[1.05] tracking-[-0.03em] text-balance md:text-[3.1rem]">
              {heading}
            </h1>
            {lead && <p className="mt-5 text-[17px] leading-relaxed text-muted text-pretty">{lead}</p>}
            {aside && <div className="mt-8">{aside}</div>}
            <div className="mt-12">{children}</div>
          </div>
        </Container>
      </main>
      <Footer />
    </>
  )
}
