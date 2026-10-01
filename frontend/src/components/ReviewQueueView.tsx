import { Fragment, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { CandidateMatch } from '../api/types'

const FIELD_ORDER = ['hostname', 'ip_address', 'owner', 'environment', 'last_seen']

function formatScore(score: number | null): string {
  if (score === null) return 'n/a'
  return score.toFixed(2)
}

export function ReviewQueueView() {
  const [queue, setQueue] = useState<CandidateMatch[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  function reload() {
    setLoading(true)
    api.getReviewQueue().then((data) => {
      setQueue(data)
      setLoading(false)
      setSelectedId((current) => current ?? data[0]?.candidate_id ?? null)
    })
  }

  useEffect(() => {
    reload()
  }, [])

  async function decide(approve: boolean) {
    if (!selectedId) return
    await api.decide(selectedId, approve)
    setSelectedId(null)
    reload()
  }

  const selected = queue.find((c) => c.candidate_id === selectedId) ?? null

  return (
    <div>
      <h2>Review queue</h2>
      <p className="page-subtitle">
        These record pairs scored between 0.65 and 0.90 - plausible enough to flag, not confident
        enough to merge automatically. Pick one and decide.
      </p>

      <div className="review-layout">
        <div className="candidate-list">
          {queue.map((candidate) => (
            <button
              key={candidate.candidate_id}
              className={candidate.candidate_id === selectedId ? 'selected' : undefined}
              onClick={() => setSelectedId(candidate.candidate_id)}
            >
              <span>
                {candidate.record_a.hostname} vs {candidate.record_b.hostname}
              </span>
              <span className="score-pill">{candidate.composite_score.toFixed(2)}</span>
            </button>
          ))}
          {!loading && queue.length === 0 && <p className="empty-state">Review queue is empty.</p>}
        </div>

        <div>
          {selected ? (
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong>
                  Composite score: {selected.composite_score.toFixed(2)}
                </strong>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="primary" onClick={() => decide(true)}>
                    Approve match
                  </button>
                  <button className="danger" onClick={() => decide(false)}>
                    Reject
                  </button>
                </div>
              </div>

              <div className="compare-grid" style={{ marginTop: 16 }}>
                <div className="field-label">Field</div>
                <div>
                  <span className={`badge source-${selected.record_a.source_name}`}>
                    {selected.record_a.source_name}
                  </span>
                </div>
                <div>
                  <span className={`badge source-${selected.record_b.source_name}`}>
                    {selected.record_b.source_name}
                  </span>
                </div>

                {FIELD_ORDER.map((field) => (
                  <Fragment key={field}>
                    <div className="field-label">
                      {field}
                      <span className="score-pill">{formatScore(selected.field_scores[field])}</span>
                    </div>
                    <div>{(selected.record_a as unknown as Record<string, string>)[field] ?? '—'}</div>
                    <div>{(selected.record_b as unknown as Record<string, string>)[field] ?? '—'}</div>
                  </Fragment>
                ))}
              </div>
            </div>
          ) : (
            <p className="empty-state">Select a candidate from the list.</p>
          )}
        </div>
      </div>
    </div>
  )
}
