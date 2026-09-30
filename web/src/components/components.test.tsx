import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Alert, Test } from '../api'
import { AlertsPanel } from './AlertsPanel'
import { PortfolioTable, summarise } from './PortfolioTable'

const test = (doc: string, metric: string, status: Test['status']): Test => ({
  doc, metric, status, kind: 'covenant', period: 'FY2027-Q4', actual: 1.5, operator: '<=', limit_value: 2, headroom_pct: 25,
})

const tests = [test('madhur_steel', 'debt_to_equity', 'red'), test('atomberg', 'interest_cover', 'green'),
  test('anchor_offshore', 'security_cover', 'amber')]

describe('PortfolioTable', () => {
  it('counts tests by status', () => {
    expect(summarise(tests)).toEqual({ red: 1, amber: 1, green: 1 })
  })

  it('shows the worst status first', () => {
    render(<PortfolioTable tests={tests} />)
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByText('red')).toBeInTheDocument()
    expect(within(rows[2]).getByText('green')).toBeInTheDocument()
  })

  it('filters by status and by borrower', async () => {
    render(<PortfolioTable tests={tests} />)
    await userEvent.click(screen.getByRole('button', { name: /amber 1/i }))
    expect(screen.getAllByRole('row')).toHaveLength(2)
    await userEvent.click(screen.getByRole('button', { name: /all 3/i }))
    await userEvent.selectOptions(screen.getByLabelText('Borrower'), 'atomberg')
    expect(screen.getByText('interest cover')).toBeInTheDocument()
    expect(screen.queryByText('debt to equity')).not.toBeInTheDocument()
  })
})

const alert: Alert = {
  key: 'madhur_steel|covenant|debt_to_equity|FY2027-Q2', doc: 'madhur_steel', date: '2027-05-10', severity: 'high',
  kind: 'covenant_red', title: 'debt to equity breach', detail: '', evidence: '', status: 'open',
}

describe('AlertsPanel', () => {
  it('sends the analyst verdict for the right alert', async () => {
    const onVerdict = vi.fn().mockResolvedValue(undefined)
    render(<AlertsPanel alerts={[alert]} onVerdict={onVerdict} />)
    await userEvent.click(screen.getByRole('button', { name: 'False positive' }))
    expect(onVerdict).toHaveBeenCalledWith(alert.key, 'false_positive')
  })

  it('shows an error when saving fails', async () => {
    const onVerdict = vi.fn().mockRejectedValue(new Error('unknown alert'))
    render(<AlertsPanel alerts={[alert]} onVerdict={onVerdict} />)
    await userEvent.click(screen.getByRole('button', { name: 'Resolved' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('unknown alert')
  })
})
