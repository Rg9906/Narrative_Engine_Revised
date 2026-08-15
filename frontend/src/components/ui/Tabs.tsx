import * as TabsPrimitive from '@radix-ui/react-tabs'
import { cn } from '@/lib/utils'

export const Tabs = TabsPrimitive.Root

export function TabsList({ className, ...props }: TabsPrimitive.TabsListProps) {
  return (
    <TabsPrimitive.List
      className={cn(
        'inline-flex h-9 items-center gap-1 rounded-lg bg-muted p-1 text-muted-foreground',
        className,
      )}
      {...props}
    />
  )
}

export function TabsTrigger({ className, ...props }: TabsPrimitive.TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        'inline-flex h-7 items-center justify-center whitespace-nowrap rounded-md px-3 text-sm font-medium',
        'transition-colors duration-150',
        'data-[state=active]:bg-surface data-[state=active]:text-foreground data-[state=active]:shadow-soft',
        'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-1',
        className,
      )}
      {...props}
    />
  )
}

export function TabsContent({ className, ...props }: TabsPrimitive.TabsContentProps) {
  return (
    <TabsPrimitive.Content
      className={cn('mt-4 outline-none animate-in fade-in-0 duration-200', className)}
      {...props}
    />
  )
}
