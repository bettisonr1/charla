import { expect, it } from 'vitest'
import { segment } from './segment'

const c = (start: number, end: number) => ({
  original: '',
  corrected: '',
  category: 'grammar' as const,
  explanation: '',
  start,
  end,
})

it('slices by code points so emoji before a span do not shift it', () => {
  const parts = segment('😀 la problema', [c(2, 13)])
  expect(parts.map((p) => p.text)).toEqual(['😀 ', 'la problema'])
  expect(parts[1].correction).toBeDefined()
})

it('ignores out-of-range and overlapping spans', () => {
  const parts = segment('Hola amigo', [c(0, 4), c(2, 6), c(5, 99)])
  expect(parts.map((p) => p.text)).toEqual(['Hola', ' amigo'])
})
