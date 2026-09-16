import { ScrollProgressBar } from '../../components/ui/ScrollProgressBar'
import { BuiltFor } from './sections/BuiltFor'
import { Developers } from './sections/Developers'
import { Faq } from './sections/Faq'
import { Features } from './sections/Features'
import { FinalCta } from './sections/FinalCta'
import { Footer } from './sections/Footer'
import { GettingConnected } from './sections/GettingConnected'
import { Hero } from './sections/Hero'
import { HowItWorks } from './sections/HowItWorks'
import { MessagingRules } from './sections/MessagingRules'
import { Navbar } from './sections/Navbar'
import { OfficialVsUnofficial } from './sections/OfficialVsUnofficial'
import { Pricing } from './sections/Pricing'
import { SellOnWhatsApp } from './sections/SellOnWhatsApp'
import { Security } from './sections/Security'
import { UseCases } from './sections/UseCases'

export function LandingPage() {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-ink focus:px-4 focus:py-2 focus:text-paper"
      >
        Skip to content
      </a>
      <ScrollProgressBar />
      <Navbar />
      <main id="main">
        <Hero />
        <BuiltFor />
        <OfficialVsUnofficial />
        <HowItWorks />
        <Features />
        <SellOnWhatsApp />
        <GettingConnected />
        <MessagingRules />
        <UseCases />
        <Pricing />
        <Developers />
        <Security />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </>
  )
}
