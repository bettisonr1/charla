import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => {
  vi.unstubAllGlobals()
})

it('shows the API status once the health check resolves', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ json: () => Promise.resolve({ status: 'ok' }) }),
  )
  render(<App />)
  expect(await screen.findByText('API: ok')).toBeInTheDocument()
})
