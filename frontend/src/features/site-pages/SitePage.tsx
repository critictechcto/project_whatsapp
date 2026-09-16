import { ContactPage } from './ContactPage'
import type { SitePageId } from './paths'
import { PrivacyPage } from './PrivacyPage'
import { TermsPage } from './TermsPage'

/** Entry of the lazy site-pages chunk (see App.tsx). */
export default function SitePage({ page }: { page: SitePageId }) {
  switch (page) {
    case 'privacy':
      return <PrivacyPage />
    case 'terms':
      return <TermsPage />
    case 'contact':
      return <ContactPage />
  }
}
