import { useCallback, useEffect, useState, type ReactNode } from "react";
import { HomePage } from "./components/HomePage";
import App from "./App";

function navigate(path: string) {
  if (window.location.pathname === path) {
    window.scrollTo({ top: 0, behavior: "smooth" });
    return;
  }
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo(0, 0);
}

function Router({ children }: { children: (path: string) => ReactNode }) {
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  return <>{children(path)}</>;
}

export function Root() {
  const onNavigate = useCallback((p: string) => navigate(p), []);

  return (
    <Router>
      {(path) => {
        if (path === "/app" || path.startsWith("/app/") || path === "/demo" || path.startsWith("/demo/")) {
          return <App onNavigate={onNavigate} />;
        }
        return <HomePage onNavigate={onNavigate} />;
      }}
    </Router>
  );
}
