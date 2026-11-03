import { vi } from 'vitest'
import type { ServerEvent } from '../api'

/** Minimal stand-in for the browser WebSocket that tests drive by hand. */
export class FakeWebSocket {
  static readonly OPEN = 1
  static instances: FakeWebSocket[] = []

  readyState = 0
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  url: string

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = 3
  }

  // Test helpers: what the server would do.
  serverOpen() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  serverSend(event: ServerEvent) {
    this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>)
  }

  serverClose(code: number) {
    this.readyState = 3
    this.onclose?.({ code } as CloseEvent)
  }
}

export function stubWebSocket() {
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
}

/** Stub fetch with a map of "METHOD /path" to JSON bodies. */
export function stubFetch(routes: Record<string, unknown>) {
  const fetchMock = vi.fn((path: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${path.replace(/^\/api/, '')}`
    if (!(key in routes)) return Promise.resolve({ ok: false, status: 404, statusText: key })
    return Promise.resolve({ ok: true, json: () => Promise.resolve(routes[key]) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
