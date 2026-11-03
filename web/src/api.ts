export type Role = 'user' | 'assistant'

export interface Message {
  id: string
  role: Role
  content: string
  created_at: string
}

export interface Conversation {
  id: string
  scenario: string
  created_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

/** Events the server sends over the chat WebSocket. */
export type ServerEvent =
  | { type: 'token'; text: string }
  | { type: 'message_done'; id: string; content: string }
  | { type: 'error'; detail: string }

/** Close code the server uses when the conversation does not exist. */
export const CLOSE_NOT_FOUND = 4404

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return (await response.json()) as T
}

export function createConversation(scenario: string): Promise<Conversation> {
  return request('/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario }),
  })
}

export function listConversations(): Promise<Conversation[]> {
  return request('/conversations')
}

export function getConversation(id: string): Promise<ConversationDetail> {
  return request(`/conversations/${id}`)
}

export function chatSocketUrl(id: string): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/api/conversations/${id}/ws`
}
