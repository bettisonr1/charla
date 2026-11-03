import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useChat } from './useChat'

export default function Chat({ conversationId }: { conversationId: string }) {
  const { scenario, messages, streaming, status, error, waitingForReply, send } =
    useChat(conversationId)
  const [draft, setDraft] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' })
  }, [messages, streaming, waitingForReply])

  const busy = streaming !== '' || waitingForReply
  const canSend = status === 'open' && !busy && draft.trim() !== ''

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (canSend && send(draft)) setDraft('')
  }

  return (
    <div className="chat">
      <header className="chat-header">
        <a href="#" aria-label="Back to conversations">
          ←
        </a>
        <p className="chat-scenario">{scenario}</p>
      </header>

      <div className="chat-log" role="log" aria-live="polite">
        {messages.map((m) => (
          <p key={m.id} className={`bubble ${m.role}`}>
            {m.content}
          </p>
        ))}
        {streaming !== '' && <p className="bubble assistant">{streaming}</p>}
        {waitingForReply && (
          <p className="bubble assistant typing" aria-label="The agent is typing">
            …
          </p>
        )}
        <div ref={endRef} />
      </div>

      {error && (
        <p className="chat-error" role="alert">
          {error}
        </p>
      )}
      {status === 'connecting' && !error && <p className="chat-status">Connecting…</p>}
      {status === 'closed' && !error && <p className="chat-status">Reconnecting…</p>}

      <form className="chat-input" onSubmit={onSubmit}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Escribe en español…"
          aria-label="Your message"
          autoComplete="off"
          lang="es"
          maxLength={2000}
        />
        <button type="submit" disabled={!canSend}>
          Send
        </button>
      </form>
    </div>
  )
}
