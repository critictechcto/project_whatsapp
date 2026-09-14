/** Product CSV import rules from `docs/contracts/wave-3-commerce.md`. */
export const MAX_IMPORT_BYTES = 2 * 1024 * 1024
export const MAX_IMPORT_ROWS = 5000

export type CsvColumnHelp = { name: string; required: boolean; format: string }

export const csvColumns: readonly CsvColumnHelp[] = [
  { name: 'sku', required: true, format: 'Letters, numbers, - and _. Existing SKUs are updated.' },
  { name: 'name', required: false, format: 'Up to 200 characters. Needed for new products.' },
  { name: 'description', required: false, format: 'Up to 1,000 characters.' },
  { name: 'price', required: false, format: 'Rupees including GST, like 249 or 249.50. Needed for new products.' },
  { name: 'sale_price', required: false, format: 'Rupees, lower than price. Leave empty for no sale.' },
  { name: 'collection', required: false, format: 'Collection name. Created when it doesn’t exist.' },
  { name: 'stock_qty', required: false, format: 'Whole number. Leave empty to not track stock.' },
  { name: 'max_qty_per_order', required: false, format: '1 to 99. Defaults to 10.' },
  { name: 'availability', required: false, format: 'in_stock or out_of_stock.' },
  { name: 'is_active', required: false, format: 'true or false.' },
]

export const sampleCsv = [
  'sku,name,description,price,sale_price,collection,stock_qty,max_qty_per_order,availability,is_active',
  'KAJU-KATLI-500,Kaju katli 500 g,Silver-leaf kaju katli made with pure ghee,650,599,Dry fruit sweets,40,10,in_stock,true',
  'BESAN-LADDU-500,Besan laddu 500 g,Roasted gram flour laddus,320,,Laddus,,10,in_stock,true',
  'DIWALI-HAMPER-L,Diwali gift hamper (large),"Kaju katli, soan papdi and dry fruits",2499,,Namkeen & gift boxes,8,5,in_stock,true',
].join('\n')

export const sampleCsvHref = `data:text/csv;charset=utf-8,${encodeURIComponent(sampleCsv)}`

/** Splits one CSV text into rows of cells. Handles quoted cells with commas, quotes and newlines. */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  const input = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text
  for (let i = 0; i < input.length; i++) {
    const char = input[i]
    if (quoted) {
      if (char === '"' && input[i + 1] === '"') {
        cell += '"'
        i++
      } else if (char === '"') quoted = false
      else cell += char
    } else if (char === '"') quoted = true
    else if (char === ',') {
      row.push(cell)
      cell = ''
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && input[i + 1] === '\n') i++
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
    } else cell += char
  }
  if (cell || row.length) {
    row.push(cell)
    rows.push(row)
  }
  return rows.filter((cells) => cells.some((value) => value.trim()))
}
