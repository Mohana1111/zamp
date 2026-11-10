import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught React render error:', error, errorInfo);
    this.setState({ errorInfo });
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-white text-[#111111] flex items-center justify-center p-6 font-sans">
          <div className="max-w-xl w-full border border-[#E5E5E5] rounded-2xl p-8 space-y-6 shadow-sm bg-[#FAFAFA]">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-amber-50 border border-amber-200 flex items-center justify-center text-[#D97706] shrink-0">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-[#111111]">
                  ClearPay AP Interface Alert
                </h1>
                <p className="text-xs font-mono text-[#6B6B6B]">
                  A view rendering error was caught safely without data loss.
                </p>
              </div>
            </div>

            {this.state.error && (
              <div className="bg-[#111111] text-[#E5E5E5] p-4 rounded-xl font-mono text-xs overflow-x-auto space-y-2">
                <p className="text-red-400 font-bold">{this.state.error.name}: {this.state.error.message}</p>
                {this.state.errorInfo?.componentStack && (
                  <pre className="text-[10px] text-[#A3A3A3] whitespace-pre-wrap leading-relaxed max-h-40 overflow-y-auto">
                    {this.state.errorInfo.componentStack}
                  </pre>
                )}
              </div>
            )}

            <div className="flex items-center gap-3 pt-2">
              <button
                type="button"
                onClick={this.handleReset}
                className="inline-flex items-center gap-2 rounded-full bg-[#111111] hover:bg-black text-white px-5 py-2.5 text-xs font-mono tracking-tight transition-colors cursor-pointer"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                <span>Reload Application</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  window.location.href = '/';
                }}
                className="inline-flex items-center gap-2 rounded-full border border-[#E5E5E5] bg-white hover:border-[#111111] text-[#111111] px-5 py-2.5 text-xs font-mono tracking-tight transition-colors cursor-pointer"
              >
                <Home className="h-3.5 w-3.5" />
                <span>Return to Home</span>
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
