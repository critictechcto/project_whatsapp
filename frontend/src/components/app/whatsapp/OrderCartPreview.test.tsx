import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { OrderCart } from './interactive'
import { OrderCartPreview } from './OrderCartPreview'

const cart: OrderCart = {
  catalog_id: 'cat-1',
  text: 'Please pack as a gift',
  product_items: [
    { product_retailer_id: 'KAJU-500', quantity: 2, item_price: 450, currency: 'INR' },
    { product_retailer_id: 'BHUJIA-400', quantity: 1, item_price: 550.5, currency: 'INR' },
  ],
}

describe('OrderCartPreview', () => {
  it('shows the item count, lines and total from item_price × quantity', () => {
    render(<OrderCartPreview order={cart} products={{ 'KAJU-500': { name: 'Kaju katli 500 g', pricePaise: 45000 } }} time="11:05" />)

    expect(within(screen.getByRole('figure')).getByText('Order cart preview')).toBeInTheDocument()
    expect(screen.getByText('3 items')).toBeInTheDocument()
    expect(screen.getByText('₹1,450.50 (estimated total)')).toBeInTheDocument()

    const lines = within(screen.getByRole('list', { name: 'Cart items' })).getAllByRole('listitem')
    expect(lines).toHaveLength(2)
    expect(lines[0]).toHaveTextContent('Kaju katli 500 g')
    expect(lines[0]).toHaveTextContent('2 × ₹450')
    expect(lines[0]).toHaveTextContent('₹900')
    expect(lines[1]).toHaveTextContent('BHUJIA-400')
    expect(lines[1]).toHaveTextContent('1 × ₹550.50')

    expect(screen.getByText('Total').parentElement).toHaveTextContent('Total₹1,450.50')
    expect(screen.getByText('Please pack as a gift')).toBeInTheDocument()
    expect(screen.getByText('11:05')).toBeInTheDocument()
  })

  it('uses the singular for one item and rounds rupee prices to paise', () => {
    render(
      <OrderCartPreview
        framed={false}
        order={{ catalog_id: 'cat-1', product_items: [{ product_retailer_id: 'A', quantity: 1, item_price: 99.999, currency: 'INR' }] }}
      />,
    )
    expect(screen.getByText('1 item')).toBeInTheDocument()
    expect(screen.getByText('₹100 (estimated total)')).toBeInTheDocument()
  })
})
