import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { EmptyState } from '@/components/ui/EmptyState'
import { Button } from '@/components/ui/Button'

export function NotFoundPage() {
  return (
    <EmptyState
      icon={<Compass className="h-5 w-5" />}
      title="Page not found"
      description="That route doesn't exist in the dashboard."
      action={
        <Button asChild size="sm" variant="outline">
          <Link to="/">Back to overview</Link>
        </Button>
      }
    />
  )
}
