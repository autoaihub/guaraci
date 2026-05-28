import { useState } from "react";
import { DownloadPage } from "./pages/DownloadPage";
import { DashboardPage } from "./pages/DashboardPage";

type View = "download" | "dashboard";

export function App() {
  const [view, setView] = useState<View>("download");

  return (
    <div className="app">
      <nav className="app-nav" aria-label="Seções">
        <button
          type="button"
          className={view === "download" ? "is-active" : ""}
          onClick={() => setView("download")}
        >
          Coleta
        </button>
        <button
          type="button"
          className={view === "dashboard" ? "is-active" : ""}
          onClick={() => setView("dashboard")}
        >
          Visualização
        </button>
      </nav>
      {view === "download" ? <DownloadPage /> : <DashboardPage />}
    </div>
  );
}
