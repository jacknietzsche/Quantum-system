import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center h-screen bg-slate-950">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 max-w-md text-center">
            <div className="text-4xl mb-4">⚠️</div>
            <h2 className="text-lg font-bold text-slate-200 mb-2">页面渲染出错</h2>
            <p className="text-sm text-slate-400 mb-4">
              {this.state.error?.message || '未知错误'}
            </p>
            <button
              onClick={this.handleReset}
              className="px-4 py-2 bg-sky-600 hover:bg-sky-500 rounded-lg text-sm font-medium"
            >
              重试
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
