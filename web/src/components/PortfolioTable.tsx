import { useMemo, useState } from 'react'
import { label, type Status, type Test } from '../api'

const ORDER: Record<Status, number> = { red: 0, amber: 1, green: 2 }

export function summarise(tests: Test[]): Record<Status, number> {
  return tests.reduce((acc, t) => ({ ...acc, [t.status]: acc[t.status] + 1 }), { red: 0, amber: 0, green: 0 })
}

export function PortfolioTable({ tests }: { tests: Test[] }) {
  const [status, setStatus] = useState<Status | 'all'>('all')
  const [doc, setDoc] = useState('all')
  const borrowers = useMemo(() => [...new Set(tests.map((t) => t.doc))].sort(), [tests])
  const counts = summarise(tests)

  const rows = tests
    .filter((t) => (status === 'all' || t.status === status) && (doc === 'all' || t.doc === doc))
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || a.doc.localeCompare(b.doc))

  return (
    <section className="card">
      <div className="card-head">
        <h2>Portfolio</h2>
        <div className="chips" role="group" aria-label="Filter by status">
          {(['all', 'red', 'amber', 'green'] as const).map((s) => (
            <button key={s} className={`chip ${s} ${status === s ? 'on' : ''}`} onClick={() => setStatus(s)}>
              {s === 'all' ? `All ${tests.length}` : `${s} ${counts[s]}`}
            </button>
          ))}
        </div>
        <select aria-label="Borrower" value={doc} onChange={(e) => setDoc(e.target.value)}>
          <option value="all">All borrowers</option>
          {borrowers.map((b) => (
            <option key={b} value={b}>{label(b)}</option>
          ))}
        </select>
      </div>
      <table>
        <thead>
          <tr>
            <th>Borrower</th><th>Test</th><th>Period</th><th className="num">Actual</th>
            <th className="num">Limit</th><th className="num">Headroom</th><th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr key={`${t.doc}-${t.metric}-${t.kind}`}>
              <td>{label(t.doc)}</td>
              <td>{label(t.metric)} <span className="muted">({t.kind})</span></td>
              <td>{t.period}</td>
              <td className="num">{t.actual.toFixed(2)}</td>
              <td className="num">{t.operator} {t.limit_value}</td>
              <td className="num">{t.headroom_pct == null ? '-' : `${t.headroom_pct.toFixed(0)}%`}</td>
              <td><span className={`badge ${t.status}`}>{t.status}</span></td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={7} className="muted">No tests match these filters.</td></tr>
          )}
        </tbody>
      </table>
    </section>
  )
}
