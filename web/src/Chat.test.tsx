import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Chat from './Chat'
import { CLOSE_NOT_FOUND } from './api'
import { FakeWebSocket, stubFetch, stubWebSocket } from './test/fakes'

const detail = (messages: object[]) => ({
  id: 'c1',
  scenario: 'Ordering at a restaurant',
  created_at: '2026-11-03T10:00:00Z',
  messages,
})

const assistantMsg = {
  id: 'm1',
  role: 'assistant',
  content: 'Buenas noches, ¿mesa para cuántos?',
  created_at: '2026-11-03T10:00:01Z',
}

beforeEach(() => {
  stubWebSocket()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

async function openChat(messages: object[] = [assistantMsg]) {
  stubFetch({ 'GET /conversations/c1': detail(messages) })
  render(<Chat conversationId="c1" />)
  await screen.findByText('Ordering at a restaurant')
  const socket = FakeWebSocket.instances[0]
  act(() => socket.serverOpen())
  return socket
}

it('shows the stored history and connects to the conversation socket', async () => {
  const socket = await openChat()
  expect(screen.getByText('Buenas noches, ¿mesa para cuántos?')).toBeInTheDocument()
  expect(socket.url).toMatch(/\/api\/conversations\/c1\/ws$/)
})

it('sends a message and streams the reply token by token', async () => {
  const socket = await openChat()
  await userEvent.type(screen.getByLabelText('Your message'), 'Para dos, por favor')
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))

  expect(JSON.parse(socket.sent[0])).toEqual({ type: 'message', content: 'Para dos, por favor' })
  expect(screen.getByText('Para dos, por favor')).toBeInTheDocument()
  expect(screen.getByLabelText('The agent is typing')).toBeInTheDocument()

  act(() => socket.serverSend({ type: 'token', text: 'Perfecto, ' }))
  expect(screen.getByText('Perfecto,')).toBeInTheDocument()
  expect(screen.queryByLabelText('The agent is typing')).not.toBeInTheDocument()

  act(() => socket.serverSend({ type: 'token', text: 'síganme.' }))
  act(() => socket.serverSend({ type: 'message_done', id: 'm3', content: 'Perfecto, síganme.' }))
  expect(screen.getAllByText('Perfecto, síganme.')).toHaveLength(1)
})

it('blocks sending while the agent is replying', async () => {
  const socket = await openChat()
  await userEvent.type(screen.getByLabelText('Your message'), 'Hola')
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
  await userEvent.type(screen.getByLabelText('Your message'), 'Otra vez')
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

  act(() => socket.serverSend({ type: 'message_done', id: 'm3', content: 'Claro.' }))
  expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()
})

it('shows an error from the server', async () => {
  const socket = await openChat()
  act(() => socket.serverSend({ type: 'error', detail: 'ANTHROPIC_API_KEY is not set.' }))
  expect(screen.getByRole('alert')).toHaveTextContent('ANTHROPIC_API_KEY is not set.')
})

it('reconnects and reloads history after the connection drops', async () => {
  const socket = await openChat()
  vi.useFakeTimers()
  act(() => socket.serverClose(1006))
  expect(screen.getByText('Reconnecting…')).toBeInTheDocument()

  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000)
  })
  expect(FakeWebSocket.instances).toHaveLength(2)
})

it('does not reconnect when the conversation does not exist', async () => {
  const socket = await openChat()
  vi.useFakeTimers()
  act(() => socket.serverClose(CLOSE_NOT_FOUND))
  expect(screen.getByRole('alert')).toHaveTextContent('Conversation not found.')

  await act(async () => {
    await vi.advanceTimersByTimeAsync(20_000)
  })
  expect(FakeWebSocket.instances).toHaveLength(1)
})
