import { useState } from 'react'
import { label, type Alert, type Verdict } from '../api'

interface Props {
  alerts: Alert[]
  onVerdict: (key: string, verdict: Verdict) => Promise<void>
}

const VERDICTS: { verdict: Verdict; text: string }[] = [
  { verdict: 'confirmed', text: 'Confirm' },
  { verdict: 'false_positive', text: 'False positive' },
  { verdict: 'resolved', text: 'Resolved' },
]

export function AlertsPanel({ alerts, onVerdict }: Props) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function decide(key: string, verdict: Verdict) {
    setBusy(key)
    setError(null)
    try {
      await onVerdict(key, verdict)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save the verdict')
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <h2>Open alerts <span className="muted">{alerts.length}</span></h2>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      {alerts.length === 0 && <p className="muted">No open alerts.</p>}
      <ul className="alerts">
        {alerts.map((a) => (
          <li key={a.key} className={`alert ${a.severity}`}>
            <div>
              <span className={`badge ${a.severity}`}>{a.severity}</span>
              <strong>{label(a.doc)}</strong> · {a.title}
              <div className="muted small">{a.date} · {label(a.kind)}</div>
            </div>
            <div className="actions">
              {VERDICTS.map((v) => (
                <button key={v.verdict} disabled={busy === a.key} onClick={() => decide(a.key, v.verdict)}>
                  {v.text}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
