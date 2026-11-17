import { useEffect, useRef, useState } from 'react'
import { useTheme } from 'next-themes'
import { AnimatePresence, motion } from 'motion/react'
import { toast } from 'sonner'
import { Bar, BarChart, Cell, LabelList, Pie, PieChart, XAxis, YAxis } from 'recharts'
import { AlertCircle, CheckCircle2, FileJson, FileSpreadsheet, FileText, Loader2, Moon, RotateCcw, Sun, UploadCloud } from 'lucide-react'

import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart'
import { Toaster } from '@/components/ui/sonner'

import { ErrorBoundary } from './ErrorBoundary'
import DataTable, { ViewBadge, type Col } from './DataTable'
import { CountUp, ease } from './motion'
import { b64ToBytes, compact, download, rupee, units } from './format'
import type { Result, Row } from './types'
import { MarketStrip, MarketTab, pct, signCls, signed, useMarket } from './Market'

const VIEWS = ['BUY', 'ADD', 'HOLD', 'TRIM', 'SELL', 'Not Covered']
const VIEW_COLOR: Record<string, string> = {
  BUY: '#15803d', ADD: '#0f766e', HOLD: '#d9a406', TRIM: '#c2410c', SELL: '#b91c1c', 'Not Covered': '#94a3b8',
}

const Wordmark = () => <span className="wordmark">CREST</span>

const Kpi = ({ label, value, sub, num, fmt, tone }: { label: string; value: string; sub?: string; num?: number; fmt?: (n: number) => string; tone?: string }) => (
  <div className="kpi">
    <div className="l">{label}</div>
    <div className={`v ${tone ?? ''}`}>{num != null && fmt ? <CountUp value={num} format={fmt} /> : value}</div>
    {sub && <div className="s">{sub}</div>}
  </div>
)

export default function App() {
  const { theme, setTheme } = useTheme()
  const [file, setFile] = useState<File | null>(null)
  const [adv, setAdv] = useState<File | null>(null)
  const [password, setPassword] = useState('')
  const [needsPw, setNeedsPw] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [res, setRes] = useState<Result | null>(null)
  const [over, setOver] = useState(false)
  const [status, setStatus] = useState<{ loaded: boolean; count: number } | null>(null)
  const pdfRef = useRef<HTMLInputElement>(null)
  const advRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetch('/api/advisory/status').then((r) => r.json()).then(setStatus).catch(() => setStatus(null))
  }, [])

  async function parse() {
    if (!file) return
    setBusy(true); setError('')
    const fd = new FormData()
    fd.append('pdf', file); fd.append('password', password)
    if (adv) fd.append('advisory', adv)
    try {
      const r = await fetch('/api/parse', { method: 'POST', body: fd })
      const body = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(body.detail || `Request failed (${r.status})`)
      setRes(body); toast.success('Statement parsed')
    } catch (e) {
      const m = e instanceof Error ? e.message : 'Something went wrong.'
      setError(m); toast.error(m)
    } finally { setBusy(false) }
  }

  const advStatus = res?.advisory_status ?? status
  const dark = theme === 'dark'

  return (
    <>
      <header className="topbar">
        <div className="topbar-in">
          <Wordmark />
          <span className="tag">CAS Parser &amp; Equity Advisory</span>
          <span className="spacer" />
          <button className="icon-btn" onClick={() => setTheme(dark ? 'light' : 'dark')} aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`}>
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>
      <Toaster position="bottom-right" />

      <main>
        <AnimatePresence mode="wait">
          {!res ? (
            <motion.div key="up" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} transition={{ duration: 0.35, ease }}>
              <h1 className="hero">Parse a statement</h1>
              <p className="muted lead">Upload a CDSL, NSDL, CAMS or KFintech CAS PDF. Holdings are cross-checked against the CREST equity advisory list. Nothing is stored on the server.</p>
              <div className="upload-grid">
                <motion.div
                  whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }} transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  className={`drop ${over ? 'over' : ''}`}
                  role="button" tabIndex={0}
                  onClick={() => pdfRef.current?.click()}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && pdfRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setOver(true) }}
                  onDragLeave={() => setOver(false)}
                  onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) setFile(f) }}
                >
                  <UploadCloud size={32} strokeWidth={1.5} color="var(--brand)" />
                  <div className="big">{file ? file.name : 'Drop your CAS PDF here, or click to browse'}</div>
                  <div className="muted">{file ? `${(file.size / 1024).toFixed(0)} KB` : 'PDF up to 25 MB'}</div>
                  <input ref={pdfRef} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                </motion.div>
                <div className="card">
                  <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer' }}>
                    <input type="checkbox" checked={needsPw} onChange={(e) => { setNeedsPw(e.target.checked); if (!e.target.checked) setPassword('') }} />
                    PDF is password protected
                  </label>
                  {needsPw && (
                    <div style={{ marginTop: 10 }}>
                      <label className="field" htmlFor="pw">PDF password</label>
                      <input id="pw" type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && parse()} />
                    </div>
                  )}
                  <div style={{ margin: '16px 0 8px' }}>
                    <label className="field">Advisory database</label>
                    <span className={`chip ${advStatus?.loaded || adv ? 'ok' : ''}`}>
                      {adv ? adv.name : advStatus?.loaded ? `${advStatus.count} stocks loaded` : 'Not loaded'}
                    </span>{' '}
                    <button className="btn" style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => advRef.current?.click()}>Replace</button>
                    <input ref={advRef} type="file" accept=".xlsx" hidden onChange={(e) => setAdv(e.target.files?.[0] ?? null)} />
                  </div>
                  <motion.button whileTap={{ scale: 0.97 }} className={`btn primary ${busy ? 'shimmer' : ''}`} disabled={!file || busy} onClick={parse}>
                    {busy ? <><Loader2 size={16} className="spin" /> Parsing…</> : 'Parse statement'}
                  </motion.button>
                </div>
              </div>
              {error && <div className="alert" role="alert"><AlertCircle size={16} style={{ verticalAlign: -3 }} /> {error}</div>}
            </motion.div>
          ) : (
            <motion.div key="dash" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
              <ErrorBoundary>
                <Dashboard res={res} onReset={() => { setRes(null); setFile(null); setPassword('') }} />
              </ErrorBoundary>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </>
  )
}

function Dashboard({ res, onReset }: { res: Result; onReset: () => void }) {
  const [tab, setTab] = useState('advisory')
  const m = useMarket(res)
  const [filter, setFilter] = useState('All')
  const t = res.totals
  const rest = t.total_portfolio_value - t.demat_value - t.mf_value
  const other = rest > 1 ? rest : 0
  const alloc = [
    { name: 'Demat', value: t.demat_value, fill: '#1e3a8a' },
    { name: 'Mutual Funds', value: t.mf_value, fill: '#60a5fa' },
    ...(other > 0 ? [{ name: 'Other', value: other, fill: '#cbd5e1' }] : []),
  ].filter((d) => d.value > 0)
  const allocConfig = { value: { label: 'Value' } } satisfies ChartConfig
  const distConfig = { count: { label: 'Stocks' } } satisfies ChartConfig
  const period = res.statement_period.from ? `${res.statement_period.from} to ${res.statement_period.to}` : ''
  const holdings = res.advisory.holdings
  const summary = res.advisory.summary
  const dist = VIEWS.map((v) => ({ name: v, count: summary[v]?.count ?? 0, value: Number(summary[v]?.value ?? 0) }))
  const allocTotal = alloc.reduce((a, d) => a + d.value, 0) || 1
  const top = [...res.demat]
    .filter((d) => typeof d.value === 'number' && d.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)
    .map((d) => ({ name: String(d.name ?? '').split('#')[0].trim().replace(/ (LIMITED|LTD\.?)$/i, ''), value: d.value as number, view: d.advisory_view as string }))
  const topConfig = { value: { label: 'Value' } } satisfies ChartConfig
  const withLive: Row[] = (holdings || []).map((h) => ({ ...h, ltp: m.quotes?.[h.isin]?.price ?? null, change_pct: m.quotes?.[h.isin]?.change_pct ?? null }))
  const shown = filter === 'All' ? withLive : withLive.filter((h) => h.advisory_view === filter)

  const view = (v: string) => <ViewBadge v={v} />
  const secName = (v: string) => <span title={v}>{String(v ?? '—').split('#')[0].trim()}</span>

  const advCols: Col[] = [
    { key: 'demat_stock_name', label: 'Security (demat)', render: secName },
    { key: 'advisory_view', label: 'View', render: view },
    { key: 'advisory_ticker', label: 'Ticker' },
    { key: 'advisory_stock_name', label: 'Advisory security' },
    { key: 'units', label: 'Units', numeric: true, render: units },
    { key: 'ltp', label: 'LTP', numeric: true, render: rupee },
    { key: 'change_pct', label: 'Day %', numeric: true, render: (v) => <span className={signCls(v)}>{pct(v)}</span> },
    { key: 'value', label: 'Value', numeric: true, render: rupee },
    { key: 'isin', label: 'ISIN' },
    { key: 'match_type', label: 'Match' },
  ]
  const dematCols: Col[] = [
    { key: 'name', label: 'Security', render: secName },
    { key: 'advisory_view', label: 'View', render: view },
    { key: 'advisory_ticker', label: 'Ticker' },
    { key: 'units', label: 'Units', numeric: true, render: units },
    { key: 'value', label: 'Value', numeric: true, render: rupee },
    { key: 'category', label: 'Category' },
    { key: 'isin', label: 'ISIN' },
    { key: 'dp_name', label: 'DP' },
  ]
  const mfCols: Col[] = [
    { key: 'scheme_name', label: 'Scheme' },
    { key: 'amc', label: 'AMC' },
    { key: 'units', label: 'Units', numeric: true, render: units },
    { key: 'nav', label: 'NAV', numeric: true, render: rupee },
    { key: 'value', label: 'Value', numeric: true, render: rupee },
    { key: 'cost', label: 'Cost', numeric: true, render: rupee },
    { key: 'folio_number', label: 'Folio' },
  ]
  const txCols: Col[] = res.transactions[0]
    ? Object.keys(res.transactions[0]).map((k) => ({
        key: k, label: k.replace(/_/g, ' '),
        numeric: ['amount', 'nav', 'units', 'balance'].includes(k),
        render: k === 'amount' || k === 'nav' ? rupee : k === 'units' || k === 'balance' ? units : undefined,
      }))
    : []

  const base = res.filename || 'CAS_Report'
  const save = (label: string, name: string, mime: string, data: BlobPart) => { toast.success(`${label} downloaded`); download(name, mime, data) }
  const tabs = [
    ['advisory', 'Equity advisory'], ['market', 'Live market'], ['demat', 'Demat'], ['mf', 'Mutual funds'],
    ['txn', 'Transactions'], ['inv', 'Investor & summary'],
  ]

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h1>Portfolio overview</h1>
          <span className="chip ok"><CheckCircle2 size={14} /> Parsed {period && `· ${period}`}</span>{' '}
          <span className="chip">{res.investor.name} · PAN {res.investor.pan}</span>
        </div>
        <span className="spacer" />
        <button className="btn" onClick={onReset}><RotateCcw size={15} /> New statement</button>
      </div>

      <div className="kpis">
        <Kpi label="Total portfolio value" value="" num={t.total_portfolio_value} fmt={rupee} sub={compact(t.total_portfolio_value)} />
        <Kpi label="Demat holdings" value="" num={t.demat_value} fmt={rupee} sub={`${res.demat.length} items`} />
        <Kpi label="Mutual funds" value="" num={t.mf_value} fmt={rupee} sub={`${res.mf.length} schemes`} />
        <Kpi label="Today's change" value={m.loading ? '…' : m.dayPnl ? signed(m.dayPnl) : '—'} tone={signCls(m.dayPnl)} sub={m.dayPnlPct != null ? `${pct(m.dayPnlPct)} on live demat equities` : m.loading ? 'Fetching live prices' : 'Live prices unavailable'} />
      </div>

      <MarketStrip m={m} />

      <div className="row">
        <div className="card">
          <h2>Allocation</h2>
          <div className="chart-split">
            <ChartContainer config={allocConfig} className="h-[220px] w-[220px]">
              <PieChart>
                <ChartTooltip content={<ChartTooltipContent hideLabel nameKey="name" formatter={(v, n) => <span style={{ display: 'flex', width: '100%', justifyContent: 'space-between', gap: 16 }}><span>{n}</span><b className="tnum">{rupee(Number(v))}</b></span>} />} />
                <Pie data={alloc} dataKey="value" nameKey="name" innerRadius={72} outerRadius={104} cornerRadius={8} paddingAngle={4} stroke="none" startAngle={90} endAngle={-270}>
                  {alloc.map((d) => <Cell key={d.name} fill={d.fill} />)}
                </Pie>
                <text x="50%" y="46%" textAnchor="middle" dominantBaseline="middle" fill="var(--subtle)" style={{ fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase' }}>Total</text>
                <text x="50%" y="57%" textAnchor="middle" dominantBaseline="middle" fill="var(--text)" style={{ fontSize: 22, fontWeight: 700 }}>{compact(t.total_portfolio_value)}</text>
              </PieChart>
            </ChartContainer>
            <div className="legend">
              {alloc.map((d) => (
                <div className="legend-item" key={d.name}>
                  <span className="legend-dot" style={{ background: d.fill }} />
                  <span className="legend-name">{d.name}</span>
                  <span className="legend-pct tnum">{((d.value / allocTotal) * 100).toFixed(1)}%</span>
                  <span className="legend-val tnum">{rupee(d.value)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="card">
          <h2>Advisory view (stocks)</h2>
          <ChartContainer config={distConfig} className="h-[240px] w-full">
            <BarChart data={dist} layout="vertical" margin={{ left: 4, right: 36, top: 4, bottom: 4 }} barCategoryGap={10}>
              <YAxis dataKey="name" type="category" tickLine={false} axisLine={false} width={86} tick={{ fontSize: 12, fontWeight: 600 }} />
              <XAxis dataKey="count" type="number" hide domain={[0, 'dataMax']} />
              <ChartTooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltipContent hideLabel formatter={(v, _n, item) => <span style={{ display: 'flex', width: '100%', justifyContent: 'space-between', gap: 16 }}><span>{(item?.payload as any)?.name}: {String(v)}</span><b className="tnum">{rupee((item?.payload as any)?.value)}</b></span>} />} />
              <Bar dataKey="count" radius={[0, 8, 8, 0]} barSize={20} background={{ fill: 'var(--surface-2)', radius: 8 }}>
                {dist.map((d) => <Cell key={d.name} fill={VIEW_COLOR[d.name]} />)}
                <LabelList dataKey="count" position="right" style={{ fontSize: 12, fontWeight: 700, fill: 'var(--text)' }} />
              </Bar>
            </BarChart>
          </ChartContainer>
        </div>
      </div>

      {top.length > 0 && (
        <div className="row single">
          <div className="card">
            <h2>Top holdings by value</h2>
            <ChartContainer config={topConfig} className="w-full" style={{ height: top.length * 34 + 16 }}>
              <BarChart data={top} layout="vertical" margin={{ left: 4, right: 96, top: 4, bottom: 4 }} barCategoryGap={8}>
                <YAxis dataKey="name" type="category" tickLine={false} axisLine={false} width={190} tick={{ fontSize: 12 }} tickFormatter={(v: any) => { const s = String(v ?? ''); return s.length > 26 ? s.slice(0, 25) + '…' : s }} />
                <XAxis dataKey="value" type="number" hide />
                <ChartTooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltipContent hideLabel formatter={(v, _n, item) => <span style={{ display: 'flex', width: '100%', justifyContent: 'space-between', gap: 16 }}><span>{(item?.payload as any)?.name}</span><b className="tnum">{rupee(Number(v))}</b></span>} />} />
                <Bar dataKey="value" radius={[0, 8, 8, 0]} barSize={18} background={{ fill: 'var(--surface-2)', radius: 8 }}>
                  {top.map((d, i) => <Cell key={i} fill={VIEW_COLOR[d.view] ?? '#1e3a8a'} />)}
                  <LabelList dataKey="value" position="right" formatter={(v: any) => compact(Number(v))} style={{ fontSize: 12, fontWeight: 600, fill: 'var(--text)' }} />
                </Bar>
              </BarChart>
            </ChartContainer>
            <p className="muted" style={{ fontSize: 12, margin: '8px 0 0' }}>Bar color shows the CREST advisory view for each stock; blue means not covered or not an equity.</p>
          </div>
        </div>
      )}

      <div className="exports">
        <strong>Download</strong>
        <button className="btn" onClick={() => save('Excel', `${base}_with_advisory.xlsx`, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', b64ToBytes(res.exports.xlsx))}><FileSpreadsheet size={16} /> Excel</button>
        <button className="btn" onClick={() => save('CSV', `${base}_formatted.csv`, 'text/csv', b64ToBytes(res.exports.csv))}><FileText size={16} /> CSV</button>
        <button className="btn" onClick={() => save('JSON', `${base}_parsed.json`, 'application/json', JSON.stringify(res.enriched_json, null, 2))}><FileJson size={16} /> JSON</button>
      </div>

      <div className="tabs" role="tablist">
        {tabs.map(([k, l]) => (
          <button key={k} role="tab" className="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
            {l}
            {tab === k && <motion.span layoutId="tab-underline" className="tab-ul" transition={{ type: 'spring', stiffness: 500, damping: 40 }} />}
          </button>
        ))}
      </div>

      <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, ease }}>
        {tab === 'advisory' && (
          <>
            <div className="sumgrid">
              {VIEWS.map((v) => (
                <div className="sum" key={v}>
                  <ViewBadge v={v} />
                  <div className="c">{summary[v]?.count ?? 0}</div>
                  <div className="m">{rupee(summary[v]?.value ?? 0)}</div>
                </div>
              ))}
            </div>
            <div className="filters">
              {['All', ...VIEWS].map((v) => (
                <button key={v} className="fbtn" aria-pressed={filter === v} onClick={() => setFilter(v)}>{v}</button>
              ))}
            </div>
            <DataTable rows={shown} cols={advCols} empty="No equity holdings found to cross-reference." />
          </>
        )}
        {tab === 'market' && <MarketTab res={res} m={m} />}
        {tab === 'demat' && <DataTable rows={res.demat} cols={dematCols} empty="No demat holdings in this statement." />}
        {tab === 'mf' && <DataTable rows={res.mf} cols={mfCols} empty="No mutual fund holdings in this statement." />}
        {tab === 'txn' && <DataTable rows={res.transactions} cols={txCols} empty="No transactions in this statement period." />}
        {tab === 'inv' && (
          <div className="row">
            <div className="card">
              <h2>Investor details</h2>
              <div className="inv-grid">
                {res.investor.details.map(([f, v]) => (
                  <div className="inv-item" key={f}>
                    <span className="inv-lbl">{f}</span>
                    <span className="inv-val">{v || <span className="muted">—</span>}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="card">
              <h2>Portfolio breakdown</h2>
              <div className="breakdown-list">
                {res.categories.map(([c, v, n]) => {
                  const isTotal = c.toLowerCase().includes('total')
                  return (
                    <div className={`breakdown-row ${isTotal ? 'total' : ''}`} key={c}>
                      <span className="breakdown-name">{c}</span>
                      <span className="breakdown-count">{n !== '' && n != null ? `${n} ${n === 1 ? 'item' : 'items'}` : '—'}</span>
                      <span className="breakdown-val tnum">{rupee(v)}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </motion.div>
    </>
  )
}
