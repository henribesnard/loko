import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  resetKeys?: Array<string | number>;
  name?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  errorCount: number;
}

/**
 * Error Boundary component
 * Implements X1 from PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md
 *
 * Catches React errors in child components and displays a fallback UI
 * instead of crashing the entire application.
 */
class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorCount: 0,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log error to console
    console.error(`[ErrorBoundary${this.props.name ? ` ${this.props.name}` : ''}]:`, error, errorInfo);

    // Update state with error details
    this.setState((prevState) => ({
      errorInfo,
      errorCount: prevState.errorCount + 1,
    }));

    // Call optional error handler
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }

    // Optional: Send to error tracking service
    // this.reportErrorToService(error, errorInfo);
  }

  componentDidUpdate(prevProps: Props) {
    // Reset error state if resetKeys change
    if (this.state.hasError && this.props.resetKeys) {
      const prevKeys = prevProps.resetKeys || [];
      const currentKeys = this.props.resetKeys;

      if (prevKeys.length !== currentKeys.length ||
          prevKeys.some((key, index) => key !== currentKeys[index])) {
        this.reset();
      }
    }
  }

  reset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  render() {
    if (this.state.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default fallback UI
      return (
        <div className="min-h-[200px] flex items-center justify-center p-6">
          <div className="max-w-md w-full bg-red-50 border border-red-200 rounded-lg p-6">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg
                  className="h-6 w-6 text-red-600"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
              </div>
              <div className="ml-3 flex-1">
                <h3 className="text-sm font-medium text-red-800">
                  {this.props.name ? `Error in ${this.props.name}` : 'Something went wrong'}
                </h3>
                <div className="mt-2 text-sm text-red-700">
                  <p>An unexpected error occurred. Please try again.</p>
                  {import.meta.env.DEV && this.state.error && (
                    <details className="mt-2">
                      <summary className="cursor-pointer font-medium">
                        Error details (dev only)
                      </summary>
                      <pre className="mt-2 text-xs overflow-auto max-h-40 bg-red-100 p-2 rounded">
                        {this.state.error.toString()}
                        {this.state.errorInfo && (
                          <>
                            {'\n\n'}
                            {this.state.errorInfo.componentStack}
                          </>
                        )}
                      </pre>
                    </details>
                  )}
                </div>
                <div className="mt-4">
                  <button
                    onClick={this.reset}
                    className="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-red-700 bg-red-100 hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                  >
                    Try again
                  </button>
                  {this.state.errorCount > 2 && (
                    <p className="mt-2 text-xs text-red-600">
                      This error has occurred {this.state.errorCount} times. Consider refreshing the page.
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
