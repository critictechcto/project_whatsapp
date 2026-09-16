import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SitePage from './SitePage'

vi.mock('../../config/site', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../config/site')>()
  return {
    ...actual,
    legalReady: true,
    site: {
      ...actual.site,
      legal: {
        entityName: 'Example Technologies Private Limited',
        registeredAddress: '1 Example Road, Pune 411001',
        grievanceOfficer: { name: 'A. Officer', email: 'grievance@example.com' },
        effectiveDate: '1 October 2026',
        jurisdictionCity: 'Pune',
      },
    },
  }
})

describe('legal pages when details are filled', () => {
  it('shows the privacy details without a draft note or noindex', () => {
    render(<SitePage page="privacy" />)

    expect(screen.queryByRole('note')).not.toBeInTheDocument()
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull()
    expect(screen.getByText('Example Technologies Private Limited')).toBeInTheDocument()
    expect(screen.getByText('1 October 2026')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'grievance@example.com' })).toHaveAttribute(
      'href',
      'mailto:grievance@example.com',
    )
  })

  it('names the jurisdiction city in the terms', () => {
    render(<SitePage page="terms" />)
    expect(screen.getByText(/exclusive jurisdiction of the courts at Pune, India/)).toBeInTheDocument()
  })
})
