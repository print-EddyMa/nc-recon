import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** shown in the fallback; helps locate which surface failed */
  label?: string;
}
interface State {
  error: Error | null;
}

/** Keeps one screen crashing from taking down the whole app. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[NCResQ] render error", this.props.label ?? "", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto grid h-full max-w-md place-items-center px-6 text-center">
          <div>
            <div className="section-title mb-2">
              {this.props.label ? `${this.props.label} hit an error` : "Something broke"}
            </div>
            <p className="text-sm text-ink-dim">
              This view failed to render. The rest of the app is still usable, switch
              screens, or reload.
            </p>
            <pre className="mt-3 overflow-x-auto rounded bg-surface-2 px-2.5 py-2 text-left text-2xs text-ink-faint">
              {String(this.state.error.message || this.state.error)}
            </pre>
            <button
              onClick={() => this.setState({ error: null })}
              className="pressable mt-4 rounded-md border border-line px-3 py-1.5 text-xs text-ink-dim hover:border-accent hover:text-ink"
            >
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
