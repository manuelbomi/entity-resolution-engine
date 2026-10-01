import type {
  CandidateMatch,
  EntityDetail,
  EntityListResponse,
  Metrics,
  SourceSummary,
} from './types'

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`${path} failed with status ${response.status}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  listSources: () => get<SourceSummary[]>('/api/sources'),

  listEntities: (page: number, pageSize: number, search?: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (search) params.set('search', search)
    return get<EntityListResponse>(`/api/entities?${params.toString()}`)
  },

  getEntity: (entityId: string) => get<EntityDetail>(`/api/entities/${entityId}`),

  getReviewQueue: () => get<CandidateMatch[]>('/api/review-queue'),

  decide: async (candidateId: string, approve: boolean) => {
    const response = await fetch(`/api/review-queue/${candidateId}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approve }),
    })
    if (!response.ok) {
      throw new Error(`decision failed with status ${response.status}`)
    }
    return response.json() as Promise<{ candidate_id: string; status: string }>
  },

  getMetrics: () => get<Metrics>('/api/metrics'),
}
