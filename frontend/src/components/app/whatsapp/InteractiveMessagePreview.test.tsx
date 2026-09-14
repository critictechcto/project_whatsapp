import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { InteractiveMessage, ProductLookup } from './interactive'
import { InteractiveMessagePreview } from './InteractiveMessagePreview'

const products: ProductLookup = {
  'KAJU-500': { name: 'Kaju katli 500 g', pricePaise: 45000, imageUrl: 'https://cdn.example.com/kaju.jpg' },
  'LADDU-1KG': { name: 'Motichoor laddu 1 kg', pricePaise: 55050 },
}

describe('InteractiveMessagePreview', () => {
  it('renders reply buttons as stacked rows with a text header and footer', () => {
    const message: InteractiveMessage = {
      type: 'button',
      header: { type: 'text', text: 'Sharma Sweets' },
      body: { text: 'What would you like to do?' },
      footer: { text: 'Powered by UpChatz' },
      action: {
        buttons: [
          { type: 'reply', reply: { id: 'upc:shop:browse', title: 'Browse products' } },
          { type: 'reply', reply: { id: 'upc:shop:cart', title: 'View cart' } },
          { type: 'reply', reply: { id: 'upc:shop:orders', title: 'My orders' } },
        ],
      },
    }
    render(<InteractiveMessagePreview message={message} time="10:42" status="read" />)

    expect(within(screen.getByRole('figure')).getByText('Interactive message preview')).toBeInTheDocument()
    expect(screen.getByText('Sharma Sweets')).toBeInTheDocument()
    expect(screen.getByText('What would you like to do?')).toBeInTheDocument()
    expect(screen.getByText('Powered by UpChatz')).toBeInTheDocument()
    const buttons = within(screen.getByRole('list', { name: 'Reply buttons' })).getAllByRole('listitem')
    expect(buttons.map((item) => item.textContent)).toEqual(['Browse products', 'View cart', 'My orders'])
    expect(screen.getByLabelText('Read')).toBeInTheDocument()
  })

  it('renders an image header', () => {
    render(
      <InteractiveMessagePreview
        framed={false}
        message={{
          type: 'button',
          header: { type: 'image', image: { link: 'https://cdn.example.com/banner.jpg' } },
          body: { text: 'Diwali boxes are here' },
          action: { buttons: [{ type: 'reply', reply: { id: 'a', title: 'Shop now' } }] },
        }}
      />,
    )
    expect(screen.getByRole('img', { name: 'Header image' })).toHaveAttribute('src', 'https://cdn.example.com/banner.jpg')
    expect(screen.queryByRole('figure')).not.toBeInTheDocument()
  })

  it('opens a list from its button', async () => {
    const user = userEvent.setup()
    render(
      <InteractiveMessagePreview
        message={{
          type: 'list',
          body: { text: 'Pick a collection' },
          action: {
            button: 'Collections',
            sections: [
              {
                title: 'Sweets',
                rows: [
                  { id: 'upc:shop:col:1:0', title: 'Dry fruit sweets', description: 'Kaju katli, badam barfi' },
                  { id: 'upc:shop:col:2:0', title: 'Laddus' },
                ],
              },
            ],
          },
        }}
      />,
    )

    const toggle = screen.getByRole('button', { name: 'Collections' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Dry fruit sweets')).not.toBeVisible()

    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const section = screen.getByRole('list', { name: 'Sweets' })
    expect(within(section).getByText('Dry fruit sweets')).toBeVisible()
    expect(within(section).getByText('Kaju katli, badam barfi')).toBeVisible()
    expect(within(section).getByText('Laddus')).toBeVisible()
    expect(document.getElementById(toggle.getAttribute('aria-controls') ?? '')).toContainElement(section)

    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('renders a CTA URL button with its destination for screen readers', () => {
    render(
      <InteractiveMessagePreview
        message={{
          type: 'cta_url',
          body: { text: 'Pay for order SS-1001' },
          action: { name: 'cta_url', parameters: { display_text: 'Pay ₹1,450', url: 'https://rzp.io/i/abc123' } },
        }}
      />,
    )
    expect(screen.getByText('Pay ₹1,450').closest('p')).toHaveTextContent('Pay ₹1,450, opens rzp.io')
    expect(screen.getByTitle('https://rzp.io/i/abc123')).toBeInTheDocument()
  })

  it('shows a single product from the lookup, or its retailer id', () => {
    const { rerender } = render(
      <InteractiveMessagePreview
        products={products}
        message={{
          type: 'product',
          body: { text: 'Fresh today' },
          action: { catalog_id: 'cat-1', product_retailer_id: 'KAJU-500' },
        }}
      />,
    )
    expect(screen.getByText('Kaju katli 500 g')).toBeInTheDocument()
    expect(screen.getByText('₹450')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Kaju katli 500 g' })).toHaveAttribute('src', 'https://cdn.example.com/kaju.jpg')
    expect(screen.getByText('Fresh today')).toBeInTheDocument()

    rerender(
      <InteractiveMessagePreview message={{ type: 'product', action: { catalog_id: 'cat-1', product_retailer_id: 'UNKNOWN-1' } }} />,
    )
    expect(screen.getByText('UNKNOWN-1')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('lists products by section with names and prices', async () => {
    const user = userEvent.setup()
    render(
      <InteractiveMessagePreview
        products={products}
        message={{
          type: 'product_list',
          header: { type: 'text', text: 'Bestsellers' },
          body: { text: 'Our most loved sweets' },
          action: {
            catalog_id: 'cat-1',
            sections: [
              { title: 'Sweets', product_items: [{ product_retailer_id: 'KAJU-500' }, { product_retailer_id: 'LADDU-1KG' }] },
              { title: 'Namkeen', product_items: [{ product_retailer_id: 'BHUJIA-400' }] },
            ],
          },
        }}
      />,
    )
    expect(screen.getByText('Bestsellers')).toBeInTheDocument()
    expect(screen.getByText('3 items')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'View items' }))
    const sweets = screen.getByRole('list', { name: 'Sweets' })
    expect(within(sweets).getByText('Kaju katli 500 g')).toBeVisible()
    expect(within(sweets).getByText('₹450')).toBeVisible()
    expect(within(sweets).getByText('₹550.50')).toBeVisible()
    expect(within(screen.getByRole('list', { name: 'Namkeen' })).getByText('BHUJIA-400')).toBeVisible()
  })

  it('renders a catalog message with its thumbnail', () => {
    render(
      <InteractiveMessagePreview
        products={products}
        message={{
          type: 'catalog_message',
          body: { text: 'Browse our full menu' },
          footer: { text: 'Delivery across Jaipur' },
          action: { name: 'catalog_message', parameters: { thumbnail_product_retailer_id: 'KAJU-500' } },
        }}
      />,
    )
    expect(screen.getByText('Browse our full menu')).toBeInTheDocument()
    expect(screen.getByText('View catalog')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Kaju katli 500 g' })).toBeInTheDocument()
  })

  it('renders an address request', () => {
    render(
      <InteractiveMessagePreview
        direction="outbound"
        message={{
          type: 'address_message',
          body: { text: 'Where should we deliver order SS-1001?' },
          action: { name: 'address_message', parameters: { country: 'IN' } },
        }}
      />,
    )
    expect(screen.getByText('Where should we deliver order SS-1001?')).toBeInTheDocument()
    expect(screen.getByText('Provide address')).toBeInTheDocument()
  })
})
