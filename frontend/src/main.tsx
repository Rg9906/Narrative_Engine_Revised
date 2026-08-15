import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { ThemeProvider } from '@/lib/theme'
import { TooltipProvider } from '@/components/ui/Tooltip'
import App from './App.tsx'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
      refetchOnWindowFocus: false,
      // This dashboard only ever talks to a local API server, so the browser's
      // online/offline detection (which networkMode: 'online' relies on) is the wrong
      // signal — it's meant for internet connectivity and is unreliable in embedded/
      // automated browser contexts, where it can desync and leave queries paused
      // forever with no error and no UI feedback. Let the fetch itself be the source of
      // truth for reachability instead.
      networkMode: 'always',
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={200}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
          <Toaster
            position="bottom-right"
            toastOptions={{
              className: '!bg-surface-raised !text-foreground !border !border-border !shadow-elevated',
            }}
          />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
