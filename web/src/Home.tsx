import { useEffect, useState, type FormEvent } from 'react'
import { createConversation, listConversations, type Conversation } from './api'

const MAX_SCENARIO_LENGTH = 500

export default function Home() {
  const [scenario, setScenario] = useState('')
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listConversations()
      .then(setConversations)
      .catch(() => setError('Could not reach the API.'))
  }, [])

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    const text = scenario.trim()
    if (!text || creating) return
    setCreating(true)
    setError(null)
    try {
      const conversation = await createConversation(text)
      window.location.hash = conversation.id
    } catch {
      setError('Could not start the conversation.')
      setCreating(false)
    }
  }

  return (
    <main className="home">
      <h1>Charla</h1>
      <form onSubmit={onSubmit}>
        <label htmlFor="scenario">What do you want to practise?</label>
        <textarea
          id="scenario"
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
          placeholder="You are a waiter in a Madrid restaurant and I have just sat down."
          rows={3}
          maxLength={MAX_SCENARIO_LENGTH}
        />
        <button type="submit" disabled={!scenario.trim() || creating}>
          {creating ? 'Starting…' : 'Start conversation'}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}

      {conversations.length > 0 && (
        <section>
          <h2>Recent</h2>
          <ul className="conversation-list">
            {conversations.map((c) => (
              <li key={c.id}>
                <a href={`#${c.id}`}>{c.scenario}</a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  )
}
