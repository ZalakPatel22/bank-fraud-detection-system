import { useCallback, useEffect, useState } from 'react'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import './App.css'

const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

async function request(path, options) {
  let response
  try {
    response = await fetch(`${API_URL}${path}`, options)
  } catch {
    throw new Error('Cannot reach the API. Start the backend on port 8000, or set VITE_API_URL to the deployed API URL.')
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(body?.detail || body?.message || `Request failed (${response.status})`)
  }
  return body
}

function useApi(path) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setData(await request(path))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [path])
  useEffect(() => { refresh() }, [refresh])
  return { data, error, loading, refresh }
}

function Page({ eyebrow, title, children }) {
  return <><header className="page-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div></header>{children}</>
}

function ApiState({ loading, error, empty = false }) {
  if (loading) return <div className="panel" role="status">Loading…</div>
  if (error) return <div className="panel error-panel" role="alert"><strong>Unable to load data</strong><p>{error}</p><p>For local development, run the backend from the repository root with <code>uvicorn backend.main:app --reload</code>.</p></div>
  if (empty) return <div className="panel empty-state">No records to display yet.</div>
  return null
}

function Dashboard() {
  const { data, error, loading } = useApi('/api/dashboard')
  if (loading || error) return <Page eyebrow="Overview" title="Bank fraud monitoring dashboard"><ApiState loading={loading} error={error} /></Page>
  if (!data) return <Page eyebrow="Overview" title="Bank fraud monitoring dashboard"><ApiState empty /></Page>
  const stats = data.stats || {}
  const cards = [
    ['Total transactions', stats.total_transactions],
    ['Genuine transactions', stats.genuine_transactions],
    ['Flagged for review', stats.flagged_for_review],
    ['Confirmed fraud', stats.confirmed_fraud_cases],
    ['Anomalous transactions', stats.anomalous_transactions],
    ['Risk rate', `${stats.fraud_detection_rate ?? 0}%`],
  ]
  return <Page eyebrow="Overview" title="Bank fraud monitoring dashboard">
    <div className="stats-grid">{cards.map(([label, value]) => <div className="stat-card" key={label}><span>{label}</span><strong>{value ?? 0}</strong></div>)}</div>
    <div className="panel-grid two-up">
      <section className="panel"><h3>Transaction volume over time</h3><DataTable rows={data.volume_over_time || []} /></section>
      <section className="panel"><h3>Transaction types</h3><DataTable rows={data.fraud_distribution_by_type || []} /></section>
      <section className="panel"><h3>Customer types</h3><DataTable rows={data.customer_type_comparison || []} /></section>
      <section className="panel"><h3>Recent suspicious transactions</h3><DataTable rows={data.recent_suspicious_transactions || []} /></section>
    </div>
    <p className="status-box">Blockchain integrity: <strong>{data.blockchain_integrity_status || 'Unknown'}</strong></p>
  </Page>
}

function DataTable({ rows }) {
  if (!Array.isArray(rows) || rows.length === 0) return <p className="empty-micro">No records to display.</p>
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row || {})))].slice(0, 8)
  return <div className="table-wrap"><table><thead><tr>{columns.map((key) => <th key={key}>{key.replaceAll('_', ' ')}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={row.id ?? row.transaction_id ?? row.customer_id ?? index}>{columns.map((key) => <td key={key}>{formatValue(row[key])}</td>)}</tr>)}</tbody></table></div>
}

function formatValue(value) {
  if (value == null) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function RecordsPage({ title, eyebrow, endpoint }) {
  const { data, error, loading, refresh } = useApi(endpoint)
  const rows = Array.isArray(data) ? data : data?.models ? Object.entries(data.models).map(([name, values]) => ({ name, ...values })) : []
  return <Page eyebrow={eyebrow} title={title}>
    <div className="panel"><div className="toolbar"><button className="primary-button" onClick={refresh}>Refresh</button></div><ApiState loading={loading} error={error} />{!loading && !error && <DataTable rows={rows} />}</div>
  </Page>
}

function DatasetPage() {
  const { data, error, loading } = useApi('/api/dataset')
  return <Page eyebrow="Data" title="Dataset and research profile"><ApiState loading={loading} error={error} />{data && <div className="panel detail-grid">{Object.entries(data).map(([key, value]) => <div key={key}><strong>{key.replaceAll('_', ' ')}</strong><span>{formatValue(value)}</span></div>)}</div>}</Page>
}

function AddTransactionPage() {
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({ customer_id: '', customer_type: 'Retail', transaction_type: 'payment', amount: '', currency: 'USD', merchant_category: 'retail', country: 'US', city: '', card_id: '', device_id: '', merchant_id: '' })
  const change = (event) => setForm((current) => ({ ...current, [event.target.name]: event.target.value }))
  async function submit(event) {
    event.preventDefault()
    setBusy(true); setError(''); setResult(null)
    try {
      const payload = { ...form, amount: Number(form.amount), timestamp: new Date().toISOString() }
      setResult(await request('/api/transactions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }))
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const fields = [['customer_id', 'Customer ID'], ['customer_type', 'Customer type'], ['transaction_type', 'Transaction type'], ['amount', 'Amount'], ['currency', 'Currency'], ['merchant_category', 'Merchant category'], ['country', 'Country'], ['city', 'City'], ['card_id', 'Card ID'], ['device_id', 'Device ID'], ['merchant_id', 'Merchant ID']]
  return <Page eyebrow="Operations" title="Analyze a transaction"><div className="panel form-panel"><form onSubmit={submit}><div className="form-grid">{fields.map(([name, label]) => <label key={name}>{label}<input name={name} value={form[name]} onChange={change} required={name === 'amount' || name === 'customer_id'} type={name === 'amount' ? 'number' : 'text'} min={name === 'amount' ? '0.01' : undefined} step={name === 'amount' ? '0.01' : undefined} /></label>)}</div>{error && <p className="error-panel" role="alert">{error}</p>}<button className="primary-button" type="submit" disabled={busy}>{busy ? 'Analyzing…' : 'Analyze and store'}</button></form>{result && <section className="result-box"><h3>Prediction result</h3><DataTable rows={[result.prediction || result]} /></section>}</div></Page>
}

const navItems = [
  ['/', 'Dashboard'], ['/transactions', 'Transactions'], ['/add-transaction', 'Add & Analyze'],
  ['/alerts', 'Alerts'], ['/customers', 'Customer Analysis'], ['/models', 'ML Comparison'],
  ['/blockchain', 'Blockchain Audit'], ['/dataset', 'Dataset & Research'],
]

function Layout() {
  return <div className="app-shell"><aside className="sidebar"><div className="brand-box"><h2>Bank Fraud Desk</h2><p>Blockchain + ML monitoring</p></div><nav>{navItems.map(([to, label]) => <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>{label}</NavLink>)}</nav></aside><main className="content-area"><Routes>
    <Route path="/" element={<Dashboard />} />
    <Route path="/transactions" element={<RecordsPage eyebrow="Operations" title="Transaction management" endpoint="/api/transactions" />} />
    <Route path="/add-transaction" element={<AddTransactionPage />} />
    <Route path="/alerts" element={<RecordsPage eyebrow="Cases" title="Fraud and anomaly alerts" endpoint="/api/alerts" />} />
    <Route path="/customers" element={<RecordsPage eyebrow="Accounts" title="Customer analysis" endpoint="/api/customers" />} />
    <Route path="/models" element={<RecordsPage eyebrow="Research" title="Machine learning model comparison" endpoint="/api/models" />} />
    <Route path="/blockchain" element={<RecordsPage eyebrow="Integrity" title="Blockchain audit trail" endpoint="/api/blockchain" />} />
    <Route path="/dataset" element={<DatasetPage />} />
    <Route path="*" element={<Page eyebrow="Not found" title="Page not found"><div className="panel">Choose a page from the navigation menu.</div></Page>} />
  </Routes></main></div>
}

export default function App() {
  return <BrowserRouter basename={import.meta.env.BASE_URL}><Layout /></BrowserRouter>
}
