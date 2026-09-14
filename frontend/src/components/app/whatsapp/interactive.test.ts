import { describe, expect, it } from 'vitest'
import { cartItemCount, cartTotalPaise, isInteractiveMessage, toOrderCart } from './interactive'

describe('isInteractiveMessage', () => {
  it('accepts known interactive shapes', () => {
    expect(
      isInteractiveMessage({ type: 'button', body: { text: 'Hi' }, action: { buttons: [{ type: 'reply', reply: { id: 'a', title: 'A' } }] } }),
    ).toBe(true)
    expect(isInteractiveMessage({ type: 'list', body: { text: 'Hi' }, action: { button: 'Menu', sections: [] } })).toBe(true)
    expect(isInteractiveMessage({ type: 'product', action: { catalog_id: 'c', product_retailer_id: 'SKU' } })).toBe(true)
    expect(isInteractiveMessage({ type: 'address_message', body: { text: 'Address?' }, action: { name: 'address_message' } })).toBe(true)
  })

  it('rejects unknown or malformed values', () => {
    expect(isInteractiveMessage(null)).toBe(false)
    expect(isInteractiveMessage({ type: 'flow', body: { text: 'Hi' }, action: {} })).toBe(false)
    expect(isInteractiveMessage({ type: 'button', body: { text: 'Hi' } })).toBe(false)
    expect(isInteractiveMessage({ type: 'list', body: { text: 'Hi' }, action: { sections: [] } })).toBe(false)
  })
})

describe('order carts', () => {
  it('reads Meta product_items and API items, coercing numeric strings', () => {
    const fromMeta = toOrderCart({
      catalog_id: 'cat-1',
      text: 'Gift wrap',
      product_items: [{ product_retailer_id: 'A', quantity: 2, item_price: 12.5, currency: 'INR' }],
    })
    expect(fromMeta).toEqual({
      catalog_id: 'cat-1',
      text: 'Gift wrap',
      product_items: [{ product_retailer_id: 'A', quantity: 2, item_price: 12.5, currency: 'INR' }],
    })

    const fromApi = toOrderCart({
      catalog_id: 'cat-1',
      items: [
        { product_retailer_id: 'A', quantity: '3', item_price: '100.25', currency: 'INR' },
        { product_retailer_id: 'B', quantity: 'x', item_price: 1 },
      ],
    })
    expect(fromApi?.product_items).toEqual([{ product_retailer_id: 'A', quantity: 3, item_price: 100.25, currency: 'INR' }])
    expect(toOrderCart({ catalog_id: 'cat-1' })).toBeNull()
  })

  it('totals in paise and counts quantities', () => {
    const cart = {
      catalog_id: 'cat-1',
      product_items: [
        { product_retailer_id: 'A', quantity: 2, item_price: 450, currency: 'INR' },
        { product_retailer_id: 'B', quantity: 3, item_price: 0.1, currency: 'INR' },
      ],
    }
    expect(cartTotalPaise(cart)).toBe(90030)
    expect(cartItemCount(cart)).toBe(5)
  })
})
