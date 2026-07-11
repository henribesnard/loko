import React from 'react';
import { useNavigate } from 'react-router-dom';
import ErrorBoundary from './ErrorBoundary';

interface PageErrorBoundaryProps {
  children: React.ReactNode;
  name?: string;
}

/**
 * Page-level Error Boundary with navigation fallback
 * Implements X1 from PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md
 */
export default function PageErrorBoundary({ children, name }: PageErrorBoundaryProps) {
  const navigate = useNavigate();

  const handleError = (error: Error) => {
    // Log to console in development
    if (import.meta.env.DEV) {
      console.error('[PageErrorBoundary]', name, error);
    }

    // Optional: Send to error tracking service
    // reportToErrorService({ error, page: name });
  };

  const fallback = (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full">
        <div className="bg-white shadow-lg rounded-lg p-8">
          <div className="flex items-center justify-center w-12 h-12 mx-auto bg-red-100 rounded-full">
            <svg
              className="w-6 h-6 text-red-600"
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

          <h2 className="mt-4 text-center text-2xl font-bold text-gray-900">
            Page Error
          </h2>

          <p className="mt-2 text-center text-sm text-gray-600">
            {name ? `An error occurred in ${name}.` : 'An unexpected error occurred on this page.'}
          </p>

          <div className="mt-6 flex flex-col space-y-3">
            <button
              onClick={() => window.location.reload()}
              className="w-full inline-flex justify-center items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              Reload page
            </button>

            <button
              onClick={() => navigate('/')}
              className="w-full inline-flex justify-center items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              Go to home
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <ErrorBoundary name={name} fallback={fallback} onError={handleError}>
      {children}
    </ErrorBoundary>
  );
}
