import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export default function AppShell({ children }: { children: ReactNode }) {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () =>
      api<{ status: string; components: Record<string, string> }>("/health"),
    refetchInterval: 15000,
  });
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <NavLink to="/documents" className="brand">
          <span className="brand-symbol" aria-hidden="true">
            E
          </span>
          <span>
            Evidence
            <br />
            Workbench
          </span>
        </NavLink>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          <NavLink to="/documents">Documents</NavLink>
          <NavLink to="/ask">Ask a question</NavLink>
          <NavLink to="/evaluation">Evaluation</NavLink>
        </nav>
        <div className="sidebar-note">
          Built around your sources.
          <br />
          Every answer has evidence.
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>Document intelligence</span>
          <span
            className={`status ${health.data?.status === "healthy" ? "ready" : "pending"}`}
            role="status"
          >
            {health.isPending
              ? "Connecting"
              : health.error
                ? "Service unavailable"
                : health.data?.status === "healthy"
                  ? "All systems ready"
                  : "Limited availability"}
          </span>
        </header>
        {health.error && (
          <div className="notice error" role="alert">
            {health.error.message}
          </div>
        )}
        {health.data?.components.generation === "degraded" && (
          <div className="notice">
            Document processing is available. Answer generation needs a
            server-side Google Gemini API key.
          </div>
        )}
        <main id="main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
