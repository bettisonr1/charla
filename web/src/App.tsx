import { useEffect, useState } from 'react'

export default function App() {
  const [apiStatus, setApiStatus] = useState<string>('checking…')

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((d: { status: string }) => setApiStatus(d.status))
      .catch(() => setApiStatus('unreachable'))
  }, [])

  return (
    <main>
      <h1>Charla</h1>
      <p>API: {apiStatus}</p>
    </main>
  )
}
