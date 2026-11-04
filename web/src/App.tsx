import { useEffect, useState } from 'react'
import Chat from './Chat'
import Home from './Home'
import Summary from './Summary'

/** The URL hash is the route: empty for home, `<id>` for a chat, `<id>/summary` for its summary. */
function readHash(): string {
  return window.location.hash.replace(/^#/, '')
}

export default function App() {
  const [conversationId, setConversationId] = useState(readHash)

  useEffect(() => {
    const onChange = () => setConversationId(readHash())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  if (!conversationId) return <Home />
  const [id, view] = conversationId.split('/')
  if (view === 'summary') return <Summary key={id} conversationId={id} />
  return <Chat key={id} conversationId={id} />
}
