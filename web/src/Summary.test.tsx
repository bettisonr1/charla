import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import Summary from './Summary'
import { stubFetch } from './test/fakes'

afterEach(() => vi.unstubAllGlobals())

const base = { conversation_id: 'c1', ended_at: '2026-11-04T10:00:00Z', messages_sent: 3 }

it('lists mistakes by category with the corrected sentence', async () => {
  stubFetch({
    'GET /conversations/c1/summary': {
      ...base,
      total_corrections: 3,
      groups: [
        {
          category: 'ser_estar',
          count: 2,
          examples: [
            {
              sentence: 'Yo soy cansado',
              original: 'soy cansado',
              corrected: 'estoy cansado',
              corrected_sentence: 'Yo estoy cansado',
              explanation: 'Usamos "estar" para estados.',
            },
          ],
        },
        { category: 'gender_agreement', count: 1, examples: [] },
      ],
    },
  })
  render(<Summary conversationId="c1" />)
  expect(await screen.findByText('3 mistakes in 3 messages.')).toBeInTheDocument()
  const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
  expect(headings).toEqual(['Ser / estar ×2', 'Gender agreement ×1'])
  expect(screen.getByText('Yo soy cansado')).toBeInTheDocument()
  expect(screen.getByText('Yo estoy cansado')).toBeInTheDocument()
})

it('celebrates a clean conversation', async () => {
  stubFetch({
    'GET /conversations/c1/summary': { ...base, total_corrections: 0, groups: [] },
  })
  render(<Summary conversationId="c1" />)
  expect(await screen.findByText(/No mistakes flagged in 3 messages/)).toBeInTheDocument()
})

it('shows an error when the summary cannot load', async () => {
  stubFetch({})
  render(<Summary conversationId="c1" />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the summary.')
})
