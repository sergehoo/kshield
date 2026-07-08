import { Component, ErrorInfo, ReactNode } from "react";
import { AlertOctagon, RefreshCw, Home } from "lucide-react";

type Props = { children: ReactNode; fallback?: ReactNode };
type State = { hasError: boolean; error?: Error; info?: ErrorInfo };

/**
 * ErrorBoundary global — capture toute exception dans l'arbre React et
 * affiche un fallback lisible au lieu de casser toute l'app.
 *
 * En dev, on montre le message d'erreur et le component stack pour debug.
 * En prod, message générique + boutons Retry / Home.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", error, info);
    this.setState({ info });
  }

  reset = () => this.setState({ hasError: false, error: undefined, info: undefined });

  render() {
    if (!this.state.hasError) return this.props.children;
    if (this.props.fallback) return this.props.fallback;

    const isDev = import.meta.env.DEV;

    return (
      <div className="min-h-[70vh] flex items-center justify-center p-6">
        <div className="max-w-lg w-full rounded-2xl border border-danger/30 bg-danger/5 p-6 shadow-card">
          <div className="flex items-start gap-3">
            <AlertOctagon className="w-6 h-6 text-danger shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-semibold text-ink">Oups — une erreur est survenue</h2>
              <p className="mt-1 text-sm text-ink-muted">
                Cette page a rencontré un problème. Tu peux réessayer, ou revenir au dashboard.
              </p>

              {isDev && this.state.error && (
                <details className="mt-3" open>
                  <summary className="text-xs text-ink-soft cursor-pointer hover:text-ink">
                    Détails techniques (dev only)
                  </summary>
                  <pre className="mt-2 text-[11px] font-mono text-danger bg-surface p-3 rounded-lg overflow-auto max-h-64 whitespace-pre-wrap">
                    {this.state.error.message}
                    {"\n\n"}
                    {this.state.error.stack}
                  </pre>
                </details>
              )}

              <div className="mt-4 flex gap-2">
                <button
                  onClick={this.reset}
                  className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium"
                >
                  <RefreshCw className="w-4 h-4" /> Réessayer
                </button>
                <a
                  href="/"
                  className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg border border-surface-border text-ink hover:bg-surface-soft text-sm font-medium"
                >
                  <Home className="w-4 h-4" /> Dashboard
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
}
