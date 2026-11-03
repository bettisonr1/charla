import { useEffect, useState } from 'react'
import Chat from './Chat'
import Home from './Home'

/** The URL hash is the route: empty for the home screen, a conversation id for a chat. */
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

  return conversationId ? <Chat key={conversationId} conversationId={conversationId} /> : <Home />
}
