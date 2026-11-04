import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { Correction } from './api'
import CorrectionSheet from './CorrectionSheet'
import FlaggedText from './FlaggedText'
import { useChat } from './useChat'

export default function Chat({ conversationId }: { conversationId: string }) {
  const { scenario, messages, streaming, status, error, waitingForReply, ended, send, end } =
    useChat(conversationId)
  const [draft, setDraft] = useState('')
  const [selected, setSelected] = useState<Correction | null>(null)
  const [confirmingEnd, setConfirmingEnd] = useState(false)
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

  async function onEnd() {
    if (await end()) window.location.hash = `${conversationId}/summary`
    else setConfirmingEnd(false)
  }

  return (
    <div className="chat">
      <header className="chat-header">
        <a href="#" aria-label="Back to conversations">
          ←
        </a>
        <p className="chat-scenario">{scenario}</p>
        {ended ? (
          <a href={`#${conversationId}/summary`}>Summary</a>
        ) : (
          <button type="button" className="link-button" onClick={() => setConfirmingEnd(true)}>
            End
          </button>
        )}
      </header>

      {confirmingEnd && !ended && (
        <div className="chat-confirm" role="alertdialog" aria-label="End conversation">
          <span>End this conversation? You can't continue it.</span>
          <button type="button" onClick={onEnd}>
            End conversation
          </button>
          <button type="button" className="link-button" onClick={() => setConfirmingEnd(false)}>
            Keep chatting
          </button>
        </div>
      )}

      <div className="chat-log" role="log" aria-live="polite">
        {messages.map((m) => (
          <p key={m.id} className={`bubble ${m.role}`}>
            {m.role === 'user' && m.corrections?.length ? (
              <FlaggedText content={m.content} corrections={m.corrections} onSelect={setSelected} />
            ) : (
              m.content
            )}
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
      {!ended && status === 'connecting' && !error && <p className="chat-status">Connecting…</p>}
      {!ended && status === 'closed' && !error && <p className="chat-status">Reconnecting…</p>}

      {ended ? (
        <p className="chat-status">This conversation has ended.</p>
      ) : (
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
      )}

      {selected && <CorrectionSheet correction={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
