// Typed client for the CovenantWatch FastAPI service (covenantwatch/api.py).

export type Status = 'green' | 'amber' | 'red'
export type Severity = 'high' | 'medium' | 'low'
export type Verdict = 'confirmed' | 'false_positive' | 'resolved'

export interface Test {
  doc: string
  metric: string
  kind: 'covenant' | 'policy'
  period: string
  actual: number
  operator: string
  limit_value: number
  status: Status
  headroom_pct: number | null
}

export interface Alert {
  key: string
  doc: string
  date: string
  severity: Severity
  kind: string
  title: string
  detail: string
  evidence: string
  status: string
}

const BASE = import.meta.env.VITE_API_URL ?? '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  portfolio: () => request<Test[]>('/portfolio'),
  alerts: (status = 'open') => request<Alert[]>(`/alerts?status=${encodeURIComponent(status)}`),
  feedback: (key: string, verdict: Verdict, comment = '') =>
    request<{ key: string; status: string }>(`/alerts/${encodeURIComponent(key)}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ verdict, comment }),
    }),
}

export const label = (s: string) => s.replace(/_/g, ' ')
