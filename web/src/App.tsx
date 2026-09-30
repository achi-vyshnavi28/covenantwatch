import { useCallback, useEffect, useState } from 'react'
import { api, type Alert, type Test, type Verdict } from './api'
import { AlertsPanel } from './components/AlertsPanel'
import { PortfolioTable } from './components/PortfolioTable'
import './App.css'

export default function App() {
  const [tests, setTests] = useState<Test[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [p, a] = await Promise.all([api.portfolio(), api.alerts('open')])
      setTests(p)
      setAlerts(a)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not reach the CovenantWatch API')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function onVerdict(key: string, verdict: Verdict) {
    await api.feedback(key, verdict)
    // a confirmed alert stays open; dismissed and resolved ones leave the list
    if (verdict !== 'confirmed') setAlerts((prev) => prev.filter((a) => a.key !== key))
  }

  return (
    <main>
      <header>
        <h1>CovenantWatch</h1>
        <p className="muted">Covenant monitoring for private-credit lenders · analyst console</p>
        <button onClick={() => void load()} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
      </header>
      {error && <p role="alert" className="error">{error}. Start the API with: uvicorn covenantwatch.api:app --port 8901</p>}
      {!error && !loading && (
        <div className="grid">
          <PortfolioTable tests={tests} />
          <AlertsPanel alerts={alerts} onVerdict={onVerdict} />
        </div>
      )}
    </main>
  )
}
