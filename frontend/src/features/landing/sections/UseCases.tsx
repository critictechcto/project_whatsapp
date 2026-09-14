import { Badge } from '../../../components/ui/Badge'
import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { TiltCard } from '../../../components/ui/TiltCard'
import { ChatBubble } from '../mockups/ChatBubble'

const useCases = [
  {
    industry: 'E-commerce',
    title: 'Order & shipping updates',
    category: 'Utility',
    message: 'Hi Aarav, your order #SR-58213 has shipped with Delhivery. Expected delivery: Thu, 18 Sep.',
    buttons: ['Track order'],
  },
  {
    industry: 'D2C brands',
    title: 'Cash on Delivery confirmation',
    category: 'Utility',
    message: 'You placed a Cash on Delivery order for ₹1,249. Please confirm so we can ship it today.',
    buttons: ['Confirm order', 'Cancel order'],
  },
  {
    industry: 'Clinics',
    title: 'Appointment reminders',
    category: 'Utility',
    message: 'Reminder: your appointment with Dr. Mehta is tomorrow at 11:30 AM at our Andheri West clinic.',
    buttons: ['Confirm', 'Reschedule'],
  },
  {
    industry: 'Schools & coaching',
    title: 'Fee reminders with UPI link',
    category: 'Utility',
    message: 'Term 2 fee of ₹18,500 for Ishaan (Class 7-B) is due on 20 Sep. Pay securely using UPI.',
    buttons: ['Pay now'],
  },
  {
    industry: 'Fintech & apps',
    title: 'Login and payment OTPs',
    category: 'Authentication',
    message: '482913 is your verification code. For your security, do not share this code with anyone.',
    buttons: ['Copy code'],
  },
  {
    industry: 'Retail',
    title: 'Abandoned cart recovery',
    category: 'Marketing',
    message: 'You left 2 items in your cart. They’re still available — complete your order before stock runs out.',
    buttons: ['View cart'],
  },
]

export function UseCases() {
  return (
    <section id="use-cases" className="border-t border-line py-20 md:py-28">
      <Container>
        <SectionHeader
          index="07"
          eyebrow="Use cases"
          title="Messages your customers actually want to receive."
          description="WhatsApp works best for timely, useful messages. These are the ones Indian businesses send most — each one a template you can set up in minutes."
        />
        <ul className="mt-14 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {useCases.map((useCase, i) => (
            <Reveal as="li" key={useCase.title} delay={(i % 3) * 90} className="flex">
              <TiltCard className="flex w-full rounded-xl">
                <div className="group/card flex w-full flex-col overflow-hidden rounded-xl border border-line bg-card transition-[border-color,box-shadow] duration-300 hover:border-ink/25 hover:shadow-[0_20px_40px_-28px_rgba(16,39,31,0.4)]">
                  <div className="flex items-start justify-between gap-3 px-5 pt-5">
                    <div>
                      <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">{useCase.industry}</p>
                      <h3 className="mt-1.5 text-[17px] font-semibold tracking-[-0.01em]">{useCase.title}</h3>
                    </div>
                    <Badge tone={useCase.category === 'Marketing' ? 'amber' : 'green'}>{useCase.category}</Badge>
                  </div>
                  <div aria-hidden="true" className="mt-5 flex-1 bg-wallpaper px-4 py-5">
                    <ChatBubble
                      from="business"
                      time="10:00"
                      buttons={useCase.buttons}
                      className="transition-transform duration-500 ease-soft group-hover/card:-translate-y-1"
                    >
                      {useCase.message}
                    </ChatBubble>
                  </div>
                  <p className="sr-only">Example message: {useCase.message}</p>
                </div>
              </TiltCard>
            </Reveal>
          ))}
        </ul>
      </Container>
    </section>
  )
}
