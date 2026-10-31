import { Component, type ErrorInfo, type ReactNode } from "react";

/** A screen that crashes shows what happened and a way back, instead of a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("screen crashed", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="panel ob-card" role="alert" style={{ margin: "48px auto", maxWidth: 520 }}>
        <h2>Something went wrong on this screen</h2>
        <p>Nothing was lost. Reload the page to carry on. If it happens again, tell the team what you clicked.</p>
        <p className="muted" style={{ wordBreak: "break-word" }}>{this.state.error.message}</p>
        <div className="row-actions">
          <button className="btn primary" onClick={() => window.location.reload()}>Reload the page</button>
          <button className="btn" onClick={() => this.setState({ error: null })}>Try again</button>
        </div>
      </div>
    );
  }
}
