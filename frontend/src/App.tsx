import { useState } from 'react'
import { EntitiesView } from './components/EntitiesView'
import { Layout, type Page } from './components/Layout'
import { MetricsView } from './components/MetricsView'
import { ReviewQueueView } from './components/ReviewQueueView'

export default function App() {
  const [page, setPage] = useState<Page>('entities')

  return (
    <Layout active={page} onNavigate={setPage}>
      {page === 'entities' && <EntitiesView />}
      {page === 'review' && <ReviewQueueView />}
      {page === 'metrics' && <MetricsView />}
    </Layout>
  )
}
