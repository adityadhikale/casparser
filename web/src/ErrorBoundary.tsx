import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
    this.setState({ error, errorInfo })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 24, margin: 20, background: '#fee2e2', border: '1px solid #ef4444', borderRadius: 8, color: '#991b1b', fontFamily: 'monospace' }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 12px' }}>React Render Error</h2>
          <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 13, marginBottom: 16 }}>
            {this.state.error?.toString()}
          </pre>
          <details style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>
            <summary style={{ cursor: 'pointer', fontWeight: 600 }}>Component Stack</summary>
            {this.state.errorInfo?.componentStack}
          </details>
          <button
            onClick={() => this.setState({ hasError: false, error: null, errorInfo: null })}
            style={{ marginTop: 16, padding: '8px 16px', background: '#dc2626', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}
          >
            Try Again
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
