import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api/client'
import type { Metrics } from '../api/types'

const SERIES_COLORS = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)']

export function MetricsView() {
  const [metrics, setMetrics] = useState<Metrics | null>(null)

  useEffect(() => {
    api.getMetrics().then(setMetrics)
  }, [])

  if (!metrics) return <p className="empty-state">Loading metrics...</p>

  const sourceData = Object.entries(metrics.records_per_source).map(([source, count]) => ({
    source,
    count,
  }))

  const confidenceData = Object.entries(metrics.confidence_distribution).map(([band, count]) => ({
    band,
    count,
  }))

  return (
    <div>
      <h2>Resolution metrics</h2>
      <p className="page-subtitle">How well the resolver is doing across the whole dataset.</p>

      <div className="stat-row">
        <div className="stat-tile">
          <div className="label">Source records</div>
          <div className="value">{metrics.total_source_records.toLocaleString()}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Resolved entities</div>
          <div className="value">{metrics.total_entities.toLocaleString()}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Match rate</div>
          <div className="value">{(metrics.match_rate * 100).toFixed(1)}%</div>
        </div>
        <div className="stat-tile">
          <div className="label">Pending review</div>
          <div className="value">{metrics.pending_review_count.toLocaleString()}</div>
        </div>
      </div>

      <div className="card">
        <strong style={{ fontSize: 13.5 }}>Records per source</strong>
        <div style={{ height: 220, marginTop: 8 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={sourceData} layout="vertical" margin={{ left: 12 }}>
              <CartesianGrid horizontal={false} stroke="var(--gridline)" />
              <XAxis type="number" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
              <YAxis
                type="category"
                dataKey="source"
                width={130}
                tick={{ fill: 'var(--text-secondary)', fontSize: 12.5 }}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--surface-card)',
                  border: '1px solid var(--border)',
                  fontSize: 13,
                }}
              />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={28}>
                {sourceData.map((_, i) => (
                  <Cell key={i} fill={SERIES_COLORS[i % SERIES_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <strong style={{ fontSize: 13.5 }}>Review queue by confidence band</strong>
        <p style={{ fontSize: 12.5, color: 'var(--text-muted)', margin: '2px 0 0' }}>
          Composite similarity score for candidates awaiting a human decision.
        </p>
        <div style={{ height: 220, marginTop: 8 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={confidenceData} margin={{ left: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--gridline)" />
              <XAxis dataKey="band" tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} />
              <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  background: 'var(--surface-card)',
                  border: '1px solid var(--border)',
                  fontSize: 13,
                }}
              />
              <Bar dataKey="count" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={48} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
