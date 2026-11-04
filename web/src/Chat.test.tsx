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

const flagged = {
  original: 'soy muy cansado',
  corrected: 'estoy muy cansado',
  category: 'ser_estar' as const,
  explanation: 'Con estados temporales usamos "estar".',
  start: 3,
  end: 18,
}

async function sendOne(socket: FakeWebSocket, text: string) {
  await userEvent.type(screen.getByLabelText('Your message'), text)
  await userEvent.click(screen.getByRole('button', { name: 'Send' }))
  act(() => socket.serverSend({ type: 'user_message_saved', id: 'u1' }))
}

it('underlines a flagged span and opens the correction sheet on tap', async () => {
  const socket = await openChat()
  await sendOne(socket, 'Yo soy muy cansado.')
  expect(screen.queryByRole('button', { name: /Mistake/ })).not.toBeInTheDocument()

  act(() => socket.serverSend({ type: 'corrections', message_id: 'u1', corrections: [flagged] }))
  await userEvent.click(screen.getByRole('button', { name: /Mistake: soy muy cansado/ }))

  const sheet = screen.getByRole('dialog', { name: 'Correction' })
  expect(sheet).toHaveTextContent('estoy muy cansado')
  expect(sheet).toHaveTextContent('Ser / estar')
  expect(sheet).toHaveTextContent('Con estados temporales usamos "estar".')

  await userEvent.click(screen.getByRole('button', { name: 'Got it' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

it('leaves a clean message unmarked', async () => {
  const socket = await openChat()
  await sendOne(socket, 'Estoy bien.')
  act(() => socket.serverSend({ type: 'corrections', message_id: 'u1', corrections: [] }))
  expect(screen.getByText('Estoy bien.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Mistake/ })).not.toBeInTheDocument()
})

it('shows flags from stored history after a reload', async () => {
  await openChat([
    assistantMsg,
    {
      id: 'u1',
      role: 'user',
      content: 'Yo soy muy cansado.',
      corrections: [flagged],
      created_at: '2026-11-03T10:00:02Z',
    },
  ])
  expect(screen.getByRole('button', { name: /Mistake: soy muy cansado/ })).toBeInTheDocument()
})

it('ends the conversation after confirmation and goes to the summary', async () => {
  const fetchMock = stubFetch({
    'GET /conversations/c1': detail([assistantMsg]),
    'POST /conversations/c1/end': { id: 'c1', ended_at: '2026-11-04T10:00:00Z' },
  })
  render(<Chat conversationId="c1" />)
  await screen.findByText('Ordering at a restaurant')
  act(() => FakeWebSocket.instances[0].serverOpen())

  await userEvent.click(screen.getByRole('button', { name: 'End' }))
  await userEvent.click(screen.getByRole('button', { name: 'End conversation' }))

  expect(fetchMock).toHaveBeenCalledWith('/api/conversations/c1/end', { method: 'POST' })
  expect(window.location.hash).toBe('#c1/summary')
  expect(screen.queryByLabelText('Your message')).not.toBeInTheDocument()
})

it('opens an ended conversation read-only, without a socket', async () => {
  stubFetch({
    'GET /conversations/c1': { ...detail([assistantMsg]), ended_at: '2026-11-04T10:00:00Z' },
  })
  render(<Chat conversationId="c1" />)
  await screen.findByText('Ordering at a restaurant')
  expect(FakeWebSocket.instances).toHaveLength(0)
  expect(screen.queryByLabelText('Your message')).not.toBeInTheDocument()
  expect(screen.getByText('This conversation has ended.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Summary' })).toHaveAttribute('href', '#c1/summary')
})
