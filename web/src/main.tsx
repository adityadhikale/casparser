import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from 'next-themes'
import { TooltipProvider } from '@/components/ui/tooltip'
import '@fontsource-variable/plus-jakarta-sans'
import './index.css'
import App from './App'
import { ErrorBoundary } from './ErrorBoundary'

window.addEventListener('error', (e) => {
  console.error('Global window error:', e.error || e.message)
})

window.addEventListener('unhandledrejection', (e) => {
  console.error('Unhandled rejection:', e.reason)
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <ThemeProvider attribute={["class", "data-theme"]} defaultTheme="light" enableSystem={false}>
        <TooltipProvider>
          <App />
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
)
