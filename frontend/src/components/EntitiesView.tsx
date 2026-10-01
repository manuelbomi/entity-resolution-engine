import { Fragment, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { EntityDetail, EntitySummary } from '../api/types'

const PAGE_SIZE = 25

export function EntitiesView() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [total, setTotal] = useState(0)
  const [items, setItems] = useState<EntitySummary[]>([])
  const [expanded, setExpanded] = useState<string | null>(null)
  const [detail, setDetail] = useState<EntityDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.listEntities(page, PAGE_SIZE, search || undefined).then((res) => {
      if (cancelled) return
      setItems(res.items)
      setTotal(res.total)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [page, search])

  async function toggleExpand(entityId: string) {
    if (expanded === entityId) {
      setExpanded(null)
      setDetail(null)
      return
    }
    setExpanded(entityId)
    const detail = await api.getEntity(entityId)
    setDetail(detail)
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div>
      <h2>Resolved entities</h2>
      <p className="page-subtitle">
        One row per real host, built by merging matching records from cmdb, cloud_inventory, and
        monitoring_agent. Expand a row to see which source contributed each field.
      </p>

      <div className="card" style={{ marginBottom: 16 }}>
        <input
          type="search"
          placeholder="Search by hostname..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
        />
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Hostname</th>
              <th>IP address</th>
              <th>Owner</th>
              <th>Environment</th>
              <th>Sources merged</th>
            </tr>
          </thead>
          <tbody>
            {items.map((entity) => (
              <Fragment key={entity.entity_id}>
                <tr
                  onClick={() => toggleExpand(entity.entity_id)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>{entity.fields.hostname?.value ?? '—'}</td>
                  <td>{entity.fields.ip_address?.value ?? '—'}</td>
                  <td>{entity.fields.owner?.value ?? '—'}</td>
                  <td>{entity.fields.environment?.value ?? '—'}</td>
                  <td>
                    {entity.member_keys.map((key) => {
                      const sourceName = key.split(':')[0]
                      return (
                        <span key={key} className={`badge source-${sourceName}`} style={{ marginRight: 4 }}>
                          {sourceName}
                        </span>
                      )
                    })}
                  </td>
                </tr>
                {expanded === entity.entity_id && detail && (
                  <tr>
                    <td colSpan={5} style={{ background: 'var(--surface-page)' }}>
                      <strong style={{ fontSize: 13 }}>Field provenance</strong>
                      <table style={{ marginTop: 8 }}>
                        <thead>
                          <tr>
                            <th>Field</th>
                            <th>Value kept</th>
                            <th>Came from</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(detail.fields).map(([field, prov]) => (
                            <tr key={field}>
                              <td>{field}</td>
                              <td>{prov.value}</td>
                              <td>
                                <span className={`badge source-${prov.source_name}`}>
                                  {prov.source_name}:{prov.source_id}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <strong style={{ fontSize: 13, display: 'block', marginTop: 14 }}>Audit log</strong>
                      <ul style={{ margin: '6px 0 0', paddingLeft: 18, fontSize: 13, color: 'var(--text-secondary)' }}>
                        {detail.audit_log.map((event, i) => (
                          <li key={i}>
                            [{event.action}] {event.detail}
                          </li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={5} className="empty-state">
                  No entities match that search.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          Previous
        </button>
        <span>
          Page {page} of {totalPages} ({total} entities)
        </span>
        <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
          Next
        </button>
      </div>
    </div>
  )
}
