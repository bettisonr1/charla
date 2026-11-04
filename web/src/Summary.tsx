import { useEffect, useState } from 'react'
import { CATEGORY_LABELS, getSummary, type ConversationSummary } from './api'

export default function Summary({ conversationId }: { conversationId: string }) {
  const [summary, setSummary] = useState<ConversationSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSummary(conversationId)
      .then(setSummary)
      .catch(() => setError('Could not load the summary.'))
  }, [conversationId])

  return (
    <main className="summary">
      <header className="summary-header">
        <a href="#" aria-label="Back to conversations">
          ←
        </a>
        <h1>Summary</h1>
      </header>

      {error && <p role="alert">{error}</p>}
      {!summary && !error && <p className="chat-status">Checking your last messages…</p>}

      {summary && (
        <>
          <p className="summary-totals">
            {summary.total_corrections === 0
              ? `No mistakes flagged in ${summary.messages_sent} messages. ¡Muy bien!`
              : `${summary.total_corrections} ${summary.total_corrections === 1 ? 'mistake' : 'mistakes'} in ${summary.messages_sent} messages.`}
          </p>
          {summary.groups.map((group) => (
            <section key={group.category} className="summary-group">
              <h2>
                {CATEGORY_LABELS[group.category]} <span className="count">×{group.count}</span>
              </h2>
              <ul>
                {group.examples.map((ex, i) => (
                  <li key={i}>
                    <p className="summary-you">
                      <del>{ex.sentence}</del>
                    </p>
                    <p className="summary-fix">{ex.corrected_sentence}</p>
                    <p className="summary-why" lang="es">
                      {ex.explanation}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </>
      )}

      <p>
        <a href={`#${conversationId}`}>View the conversation</a>
      </p>
    </main>
  )
}
