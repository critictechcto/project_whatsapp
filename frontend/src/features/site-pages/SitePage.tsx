import { ContactPage } from './ContactPage'
import { NotFoundPage } from './NotFoundPage'
import type { SitePageId } from './paths'
import { PrivacyPage } from './PrivacyPage'
import { TermsPage } from './TermsPage'

/** Entry of the lazy site-pages chunk (see App.tsx). */
export default function SitePage({ page }: { page: SitePageId | 'not-found' }) {
  switch (page) {
    case 'privacy':
      return <PrivacyPage />
    case 'terms':
      return <TermsPage />
    case 'contact':
      return <ContactPage />
    case 'not-found':
      return <NotFoundPage />
  }
}
