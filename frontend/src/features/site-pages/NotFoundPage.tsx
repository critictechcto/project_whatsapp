import { Button } from '../../components/ui/Button'
import { sectionHref, site } from '../../config/site'
import { PageLayout } from './PageLayout'
import { BulletList, TextLink } from './prose'

/** Any path on the marketing site that is not the landing page, a site page or the dashboard. */
export function NotFoundPage() {
  const home = import.meta.env.BASE_URL

  return (
    <PageLayout
      title={`Page not found — ${site.name}`}
      description={`This page does not exist on ${site.domain}.`}
      eyebrow="404"
      heading="This page doesn’t exist"
      lead="The link may be old or mistyped. Here are some places to go instead."
      noindex
    >
      <div className="flex flex-wrap gap-3">
        <Button href={home}>Go to the home page</Button>
        <Button href={site.links.signup} variant="secondary">
          Start your free trial
        </Button>
      </div>

      <BulletList className="mt-10">
        <li>
          See <TextLink href={sectionHref('pricing')}>plans and pricing</TextLink> or{' '}
          <TextLink href={sectionHref('how-it-works')}>how it works</TextLink>.
        </li>
        <li>
          Already a customer? <TextLink href={site.links.login}>Log in to your dashboard</TextLink>.
        </li>
        <li>
          Looking for something specific? <TextLink href={site.links.contact}>Contact us</TextLink>.
        </li>
      </BulletList>
    </PageLayout>
  )
}
