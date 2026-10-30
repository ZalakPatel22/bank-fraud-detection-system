import { useEffect, useMemo, useState } from 'react';
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import './App.css';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function fetchJson(url, options = {}) {
  const response = await fetch(`${API_URL}${url}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
      'Content-Type': 'application/json',
    },
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || 'Request failed');
  }
  return payload;
}

function StatCard({ label, value, tone = 'blue', helper = '' }) {
  return (
    <div className={`stat-card tone-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {helper ? <small>{helper}</small> : null}
    </div>
  );
}

function DashboardPage() {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const data = await fetchJson('/api/dashboard');
        setDashboard(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadDashboard();
  }, []);

  if (loading) return <div className="panel">Loading dashboard…</div>;
  if (error) return <div className="panel error-panel">{error}</div>;
  if (!dashboard) return <div className="panel empty-state">No dashboard data yet.</div>;

  const stats = dashboard.stats || {};
  const volumeData = dashboard.volume_over_time || [];
  const distributionData = dashboard.fraud_distribution_by_type || [];
  const customerData = dashboard.customer_type_comparison || [];
  const recent = dashboard.recent_suspicious_transactions || [];

  return (
    <>
      <div className="page-header">
        <div>
          <p className="eyebrow">Overview</p>
          <h1>Bank fraud monitoring dashboard</h1>
        </div>
        <span className="pill success">{dashboard.blockchain_integrity_status}</span>
      </div>

      <div className="stats-grid">
        <StatCard label="Total transactions" value={stats.total_transactions ?? 0} tone="blue" />
        <StatCard label="Genuine transactions" value={stats.genuine_transactions ?? 0} tone="green" />
        <StatCard label="Flagged for review" value={stats.flagged_for_review ?? 0} tone="amber" />
        <StatCard label="Confirmed fraud" value={stats.confirmed_fraud_cases ?? 0} tone="red" />
        <StatCard label="Anomalous transactions" value={stats.anomalous_transactions ?? 0} tone="purple" />
        <StatCard label="Risk rate" value={`${stats.fraud_detection_rate ?? 0}%`} tone="orange" helper="Model-based observed rate" />
      </div>

      <div className="panel-grid two-up">
        <div className="panel">
          <h3>Transaction volume over time</h3>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={volumeData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="amount" stroke="#7c3aed" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="panel">
          <h3>Fraud distribution by type</h3>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={distributionData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="type" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill="#2563eb" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="panel-grid two-up">
        <div className="panel">
          <h3>Customer-type comparison</h3>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={customerData} dataKey="count" nameKey="type" innerRadius={40} outerRadius={80} paddingAngle={2}>
                  {customerData.map((entry, index) => (
                    <Cell key={`${entry.type}-${index}`} fill={['#2563eb', '#10b981', '#f59e0b', '#ef4444'][index % 4]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="panel">
          <h3>Recent suspicious transactions</h3>
          <div className="list-stack">
            {recent.length ? recent.map((item) => (
              <div key={item.transaction_id} className="mini-row">
                <div>
                  <strong>{item.transaction_id}</strong>
                  <small>{item.customer_id}</small>
                </div>
                <span className="risk-badge">{item.risk_score}</span>
              </div>
            )) : <p className="empty-micro">No suspicious transactions recorded yet.</p>}
          </div>
        </div>
      </div>
    </>
  );
}

function TransactionsPage() {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState('');

  const loadTransactions = async () => {
    try {
      const data = await fetchJson(`/api/transactions?search=${encodeURIComponent(search)}`);
      setTransactions(data);
      if (data[0]) setSelected(data[0]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTransactions();
  }, [search]);

  const exportCsv = () => {
    if (!transactions.length) return;
    const header = ['transaction_id', 'customer_id', 'customer_type', 'transaction_type', 'amount', 'risk_score', 'model_result'];
    const lines = [header.join(',')];
    transactions.forEach((row) => {
      lines.push([
        row.transaction_id,
        row.customer_id,
        row.customer_type,
        row.transaction_type,
        row.amount,
        row.risk_score,
        row.model_result,
      ].map((value) => `"${String(value ?? '').replace(/"/g, '""')}"`).join(','));
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'authorized_records.csv';
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="page-header">
        <div>
          <p className="eyebrow">Operations</p>
          <h1>Transaction management</h1>
        </div>
        <button className="primary-button" onClick={exportCsv}>Export authorized records</button>
      </div>

      <div className="panel">
        <div className="toolbar">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by ID, customer, or category"
          />
        </div>
        {loading ? <p>Loading transactions…</p> : null}
        {error ? <p className="error-panel">{error}</p> : null}
        {!loading && !error ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Transaction ID</th>
                  <th>Customer</th>
                  <th>Type</th>
                  <th>Amount</th>
                  <th>Risk</th>
                  <th>Result</th>
                  <th>Verification</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((row) => (
                  <tr key={row.transaction_id} onClick={() => setSelected(row)} className={selected?.transaction_id === row.transaction_id ? 'selected-row' : ''}>
                    <td>{row.transaction_id}</td>
                    <td>{row.customer_id}</td>
                    <td>{row.transaction_type}</td>
                    <td>{row.amount}</td>
                    <td>{row.risk_score}</td>
                    <td>{row.model_result}</td>
                    <td>{row.audit_verified ? 'Verified' : 'Pending'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      {selected ? (
        <div className="panel detail-panel">
          <h3>Transaction detail</h3>
          <div className="detail-grid">
            <div><strong>ID</strong><span>{selected.transaction_id}</span></div>
            <div><strong>Customer</strong><span>{selected.customer_id}</span></div>
            <div><strong>Customer type</strong><span>{selected.customer_type}</span></div>
            <div><strong>Amount</strong><span>{selected.amount}</span></div>
            <div><strong>Transaction type</strong><span>{selected.transaction_type}</span></div>
            <div><strong>Risk score</strong><span>{selected.risk_score}</span></div>
            <div><strong>Model result</strong><span>{selected.model_result}</span></div>
            <div><strong>Hash</strong><span>{selected.record_hash}</span></div>
            <div><strong>Block</strong><span>{selected.block_number}</span></div>
            <div><strong>Audit</strong><span>{selected.audit_verified ? 'Verified' : 'Pending'}</span></div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function AddTransactionPage() {
  const [form, setForm] = useState({
    transaction_id: '',
    customer_id: 'CUST-1001',
    customer_type: 'Retail',
    transaction_type: 'payment',
    amount: 150,
    currency: 'USD',
    merchant_category: 'retail',
    country: 'US',
    city: 'New York',
    timestamp: new Date().toISOString().slice(0, 16),
    card_id: 'CARD-101',
    device_id: 'DEV-55',
    merchant_id: 'MERCH-44',
  });
  const [result, setResult] = useState(null);
  const [fileStatus, setFileStatus] = useState('');
  const [error, setError] = useState('');

  const handleChange = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    try {
      const payload = {
        ...form,
        amount: Number(form.amount),
        timestamp: new Date(form.timestamp).toISOString(),
      };
      const data = await fetchJson('/api/transactions', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setResult(data);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleCsvUpload = async (event) => {
    const uploaded = event.target.files?.[0];
    if (!uploaded) return;
    const formData = new FormData();
    formData.append('file', uploaded);
    try {
      const data = await fetch(`${API_URL}/api/transactions/upload`, {
        method: 'POST',
        body: formData,
      }).then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || 'Upload failed');
        return payload;
      });
      setFileStatus(`${data.message}`);
    } catch (err) {
      setFileStatus(err.message);
    }
  };

  return (
    <div className="panel-grid two-up">
      <form className="panel form-panel" onSubmit={handleSubmit}>
        <h3>Add transaction</h3>
        <div className="form-grid">
          <label>Transaction ID<input value={form.transaction_id} onChange={(e) => handleChange('transaction_id', e.target.value)} /></label>
          <label>Customer ID<input value={form.customer_id} onChange={(e) => handleChange('customer_id', e.target.value)} /></label>
          <label>Customer type<select value={form.customer_type} onChange={(e) => handleChange('customer_type', e.target.value)}>
            <option>Retail</option>
            <option>Business</option>
          </select></label>
          <label>Transaction type<select value={form.transaction_type} onChange={(e) => handleChange('transaction_type', e.target.value)}>
            <option value="payment">payment</option>
            <option value="transfer">transfer</option>
            <option value="cash-out">cash-out</option>
            <option value="deposit">deposit</option>
          </select></label>
          <label>Amount<input type="number" step="0.01" value={form.amount} onChange={(e) => handleChange('amount', e.target.value)} /></label>
          <label>Currency<input value={form.currency} onChange={(e) => handleChange('currency', e.target.value)} /></label>
          <label>Country<input value={form.country} onChange={(e) => handleChange('country', e.target.value)} /></label>
          <label>City<input value={form.city} onChange={(e) => handleChange('city', e.target.value)} /></label>
          <label>Merchant category<input value={form.merchant_category} onChange={(e) => handleChange('merchant_category', e.target.value)} /></label>
          <label>Timestamp<input type="datetime-local" value={form.timestamp} onChange={(e) => handleChange('timestamp', e.target.value)} /></label>
          <label>Card ID<input value={form.card_id} onChange={(e) => handleChange('card_id', e.target.value)} /></label>
          <label>Device ID<input value={form.device_id} onChange={(e) => handleChange('device_id', e.target.value)} /></label>
        </div>
        {error ? <div className="error-panel">{error}</div> : null}
        <button className="primary-button" type="submit">Analyze and store</button>
      </form>

      <div className="panel form-panel">
        <h3>CSV import</h3>
        <input type="file" accept=".csv" onChange={handleCsvUpload} />
        {fileStatus ? <p className="status-box">{fileStatus}</p> : null}

        {result ? (
          <div className="result-box">
            <h4>Prediction result</h4>
            <p><strong>Decision:</strong> {result.prediction.model_result}</p>
            <p><strong>Risk score:</strong> {result.prediction.risk_score}</p>
            <p><strong>Anomaly score:</strong> {result.prediction.anomaly_score}</p>
            <p><strong>Explanation:</strong> {result.prediction.explanation}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function AlertsPage() {
  const [alerts, setAlerts] = useState([]);
  useEffect(() => {
    fetchJson('/api/alerts')
      .then((data) => setAlerts(data))
      .catch(() => setAlerts([]));
  }, []);

  return (
    <div className="panel">
      <div className="page-header">
        <div>
          <p className="eyebrow">Cases</p>
          <h1>Fraud and anomaly alerts</h1>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Transaction</th>
            <th>Severity</th>
            <th>Risk</th>
            <th>Prediction</th>
            <th>Reason</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => (
            <tr key={alert.id}>
              <td>{alert.transaction_id}</td>
              <td>{alert.severity}</td>
              <td>{alert.risk_score}</td>
              <td>{alert.model_result}</td>
              <td>{alert.reason}</td>
              <td>{alert.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CustomerAnalysisPage() {
  const [customers, setCustomers] = useState([]);
  useEffect(() => {
    fetchJson('/api/customers').then((data) => setCustomers(data)).catch(() => setCustomers([]));
  }, []);

  return (
    <div className="panel">
      <div className="page-header">
        <div>
          <p className="eyebrow">Accounts</p>
          <h1>Customer analysis</h1>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Customer</th>
            <th>Type</th>
            <th>Transactions</th>
            <th>Total Amount</th>
            <th>Average</th>
            <th>Previous alerts</th>
            <th>Risk</th>
          </tr>
        </thead>
        <tbody>
          {customers.map((customer) => (
            <tr key={customer.customer_id}>
              <td>{customer.customer_id}</td>
              <td>{customer.customer_type}</td>
              <td>{customer.transaction_count}</td>
              <td>{customer.total_amount}</td>
              <td>{customer.average_amount}</td>
              <td>{customer.previous_alerts}</td>
              <td>{customer.risk_indicator}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ModelComparisonPage() {
  const [metrics, setMetrics] = useState({});
  useEffect(() => {
    fetchJson('/api/models').then((data) => setMetrics(data.models || {})).catch(() => setMetrics({}));
  }, []);

  const modelCards = useMemo(() => Object.entries(metrics), [metrics]);

  return (
    <div className="panel">
      <div className="page-header">
        <div>
          <p className="eyebrow">Research</p>
          <h1>Machine learning model comparison</h1>
        </div>
      </div>
      <div className="metrics-grid">
        {modelCards.map(([name, values]) => (
          <div key={name} className="metric-box">
            <h3>{name.replace(/_/g, ' ')}</h3>
            <ul>
              <li>Precision: {values.precision}</li>
              <li>Recall: {values.recall}</li>
              <li>F1-score: {values.f1_score}</li>
              <li>PR-AUC: {values.pr_auc}</li>
              <li>ROC-AUC: {values.roc_auc}</li>
              <li>False-positive rate: {values.false_positive_rate}</li>
              <li>Accuracy: {values.accuracy}</li>
            </ul>
          </div>
        ))}
      </div>
      <p className="note-box">Isolation Forest produces anomaly scores rather than supervised fraud probabilities; those scores are not directly comparable to binary-classification probabilities for the same decision boundary.</p>
    </div>
  );
}

function BlockchainAuditPage() {
  const [history, setHistory] = useState([]);
  useEffect(() => {
    fetchJson('/api/blockchain').then((data) => setHistory(data)).catch(() => setHistory([]));
  }, []);

  const runTamperDemo = async () => {
    if (!history.length) return;
    const first = history[0]?.transaction_id;
    if (!first) return;
    const data = await fetchJson(`/api/blockchain/tamper-demo/${first}`, { method: 'POST' });
    alert(`${data.verification_passed ? 'Verification still passed unexpectedly.' : 'Tampering detected correctly.'}`);
    const refreshed = await fetchJson('/api/blockchain');
    setHistory(refreshed);
  };

  return (
    <div className="panel">
      <div className="page-header">
        <div>
          <p className="eyebrow">Integrity</p>
          <h1>Blockchain audit trail</h1>
        </div>
        <button className="primary-button" onClick={runTamperDemo}>Run tamper demo</button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Transaction</th>
            <th>Record Hash</th>
            <th>Previous Hash</th>
            <th>Block</th>
            <th>Verification</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>
          {history.map((row) => (
            <tr key={row.id}>
              <td>{row.transaction_id}</td>
              <td>{row.record_hash}</td>
              <td>{row.previous_hash}</td>
              <td>{row.block_number}</td>
              <td>{row.verification_passed ? 'Passed' : 'Failed'}</td>
              <td>{row.summary}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DatasetPage() {
  const [dataset, setDataset] = useState(null);
  useEffect(() => {
    fetchJson('/api/dataset').then((data) => setDataset(data)).catch(() => setDataset(null));
  }, []);

  if (!dataset) return <div className="panel">Loading dataset details…</div>;
  return (
    <div className="panel">
      <div className="page-header">
        <div>
          <p className="eyebrow">Data</p>
          <h1>Dataset and research profile</h1>
        </div>
      </div>
      <div className="detail-grid">
        <div><strong>Dataset name</strong><span>{dataset.name}</span></div>
        <div><strong>Source URL</strong><span>{dataset.source_url}</span></div>
        <div><strong>License / restrictions</strong><span>{dataset.license}</span></div>
        <div><strong>Dataset size</strong><span>{dataset.rows} rows</span></div>
        <div><strong>Feature names</strong><span>{dataset.columns.join(', ')}</span></div>
        <div><strong>Class distribution</strong><span>{JSON.stringify(dataset.class_distribution)}</span></div>
      </div>
    </div>
  );
}

function AppLayout() {
  const navItems = [
    { to: '/', label: 'Dashboard' },
    { to: '/transactions', label: 'Transactions' },
    { to: '/add-transaction', label: 'Add & Analyse' },
    { to: '/alerts', label: 'Alerts' },
    { to: '/customers', label: 'Customer Analysis' },
    { to: '/models', label: 'ML Comparison' },
    { to: '/blockchain', label: 'Blockchain Audit' },
    { to: '/dataset', label: 'Dataset & Research' },
  ];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-box">
          <h2>Bank Fraud Desk</h2>
          <p>Blockchain + ML monitoring</p>
        </div>
        <nav>
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === '/'} className={({ isActive }) => (isActive ? 'nav-item active' : 'nav-item')}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="content-area">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
          <Route path="/add-transaction" element={<AddTransactionPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/customers" element={<CustomerAnalysisPage />} />
          <Route path="/models" element={<ModelComparisonPage />} />
          <Route path="/blockchain" element={<BlockchainAuditPage />} />
          <Route path="/dataset" element={<DatasetPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  );
}
