import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Users,
  Heart,
  Globe,
  Sparkles,
  ScrollText,
  Clock,
  FileWarning,
  UploadCloud,
  BookOpen,
  Share2,
  Swords,
  TrendingUp,
} from 'lucide-react'
import { cn } from '@/lib/utils'

export const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/characters', label: 'Characters', icon: Users },
  { to: '/relationships', label: 'Relationships', icon: Heart },
  { to: '/world', label: 'World', icon: Globe },
  { to: '/themes', label: 'Themes & Motifs', icon: Sparkles },
  { to: '/promises', label: 'Promises & Mysteries', icon: ScrollText },
  { to: '/dynamics', label: 'Conflicts & Arcs', icon: Swords },
  { to: '/style', label: 'Style & Readability', icon: TrendingUp },
  { to: '/timeline', label: 'Timeline', icon: Clock },
  { to: '/graph', label: 'Story Graph', icon: Share2 },
  { to: '/reports', label: 'Editorial Reports', icon: FileWarning },
  { to: '/ingest', label: 'Ingest Chapter', icon: UploadCloud },
]

export function Sidebar() {
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-surface md:flex">
      <div className="flex h-14 items-center gap-2 border-b border-border px-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <BookOpen className="h-4 w-4" />
        </div>
        <span className="text-sm font-semibold tracking-tight text-foreground">Narrative Engine</span>
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={cn('h-4 w-4 shrink-0', isActive ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground')} />
                <span className="truncate">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-border p-3">
        <p className="px-2 text-xs leading-snug text-muted-foreground">
          Deterministic NLP evidence → versioned story memory → editorial critique.
        </p>
      </div>
    </aside>
  )
}
