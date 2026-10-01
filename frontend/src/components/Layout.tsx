import type { ReactNode } from 'react'

export type Page = 'entities' | 'review' | 'metrics'

interface LayoutProps {
  active: Page
  onNavigate: (page: Page) => void
  children: ReactNode
}

const NAV_ITEMS: { page: Page; label: string }[] = [
  { page: 'entities', label: 'Entities' },
  { page: 'review', label: 'Review queue' },
  { page: 'metrics', label: 'Metrics' },
]

export function Layout({ active, onNavigate, children }: LayoutProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>Entity Resolution</h1>
        <nav>
          {NAV_ITEMS.map((item) => (
            <a
              key={item.page}
              className={item.page === active ? 'active' : undefined}
              href={`#${item.page}`}
              onClick={(e) => {
                e.preventDefault()
                onNavigate(item.page)
              }}
            >
              {item.label}
            </a>
          ))}
        </nav>
      </aside>
      <main className="main">{children}</main>
    </div>
  )
}
