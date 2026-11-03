import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'
import { stubFetch, stubWebSocket } from './test/fakes'

beforeEach(() => {
  window.location.hash = ''
  stubWebSocket()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

it('lists past conversations on the home screen', async () => {
  stubFetch({
    'GET /conversations': [
      { id: 'c1', scenario: 'Ordering at a restaurant', created_at: '2026-11-03T10:00:00Z' },
    ],
  })
  render(<App />)
  const link = await screen.findByRole('link', { name: 'Ordering at a restaurant' })
  expect(link).toHaveAttribute('href', '#c1')
})

it('creates a conversation from a scenario and opens it', async () => {
  const fetchMock = stubFetch({
    'GET /conversations': [],
    'POST /conversations': {
      id: 'c2',
      scenario: 'At the doctor',
      created_at: '2026-11-03T10:00:00Z',
    },
    'GET /conversations/c2': {
      id: 'c2',
      scenario: 'At the doctor',
      created_at: '2026-11-03T10:00:00Z',
      messages: [],
    },
  })
  render(<App />)
  await userEvent.type(screen.getByLabelText('What do you want to practise?'), 'At the doctor')
  await userEvent.click(screen.getByRole('button', { name: 'Start conversation' }))

  expect(await screen.findByLabelText('Your message')).toBeInTheDocument()
  expect(window.location.hash).toBe('#c2')
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
  expect(JSON.parse(post![1]!.body as string)).toEqual({ scenario: 'At the doctor' })
})
