export type Role = 'user' | 'assistant'

export type ErrorCategory =
  | 'grammar'
  | 'verb_tense'
  | 'gender_agreement'
  | 'vocabulary'
  | 'preposition'
  | 'ser_estar'
  | 'subjunctive'
  | 'word_order'
  | 'register'
  | 'spelling'

/** A correction placed in the learner's message. Offsets are code points, end exclusive. */
export interface Correction {
  original: string
  corrected: string
  category: ErrorCategory
  explanation: string
  start: number
  end: number
}

export interface Message {
  id: string
  role: Role
  content: string
  /** undefined/null: not checked (yet) or the check failed. []: checked and clean. */
  corrections?: Correction[] | null
  created_at: string
}

export interface Conversation {
  id: string
  scenario: string
  created_at: string
  ended_at?: string | null
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

/** Events the server sends over the chat WebSocket. */
export type ServerEvent =
  | { type: 'user_message_saved'; id: string }
  | { type: 'corrections'; message_id: string; corrections: Correction[] }
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

export function endConversation(id: string): Promise<Conversation> {
  return request(`/conversations/${id}/end`, { method: 'POST' })
}

export interface SummaryExample {
  sentence: string
  original: string
  corrected: string
  corrected_sentence: string
  explanation: string
}

export interface SummaryGroup {
  category: ErrorCategory
  count: number
  examples: SummaryExample[]
}

export interface ConversationSummary {
  conversation_id: string
  ended_at: string | null
  messages_sent: number
  total_corrections: number
  groups: SummaryGroup[]
}

export function getSummary(id: string): Promise<ConversationSummary> {
  return request(`/conversations/${id}/summary`)
}

/** Human-readable names for error categories. */
export const CATEGORY_LABELS: Record<ErrorCategory, string> = {
  grammar: 'Grammar',
  verb_tense: 'Verb tense',
  gender_agreement: 'Gender agreement',
  vocabulary: 'Vocabulary',
  preposition: 'Prepositions',
  ser_estar: 'Ser / estar',
  subjunctive: 'Subjunctive',
  word_order: 'Word order',
  register: 'Register',
  spelling: 'Spelling',
}

export function chatSocketUrl(id: string): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/api/conversations/${id}/ws`
}
