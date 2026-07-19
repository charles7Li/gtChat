import { useEffect, useMemo, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { HomePage } from "./pages/HomePage";
import { ReportsPage } from "./pages/ReportsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { UploadPage } from "./pages/UploadPage";
import type { ThemeId } from "./types";

export type Page = "chat" | "uploads" | "reports" | "settings";

const pageMeta: Record<Page, { title: string; eyebrow: string; action: string }> = {
  chat: { title: "工作台", eyebrow: "首页", action: "双模式" },
  uploads: { title: "素材", eyebrow: "素材库", action: "本地导入" },
  reports: { title: "报告", eyebrow: "阅读器", action: "查看证据" },
  settings: { title: "设置", eyebrow: "运行", action: "本地优先" },
};

const themeIds: ThemeId[] = ["ragdoll", "siamese", "calico", "tabby"];

function readTheme(): ThemeId {
  const saved = window.localStorage.getItem("mochi-theme");
  return themeIds.includes(saved as ThemeId) ? saved as ThemeId : "ragdoll";
}

export default function App() {
  const [page, setPage] = useState<Page>("chat");
  const [apiBase, setApiBase] = useState("local");
  const [theme, setTheme] = useState<ThemeId>(readTheme);
  const meta = useMemo(() => pageMeta[page], [page]);

  useEffect(() => {
    document.title = `${meta.title} - Mochi Scout`;
  }, [meta.title]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("mochi-theme", theme);
  }, [theme]);

  return (
    <div className="app-shell">
      <Sidebar page={page} onChange={setPage} />
      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="section-kicker">{meta.eyebrow}</p>
            <h1>{meta.title}</h1>
          </div>
          <div className="topbar-actions" aria-label="运行状态">
            <span className="signal-dot" aria-hidden="true" />
            <span>{meta.action}</span>
            <span className="env-pill">{apiBase}</span>
          </div>
        </header>
        <div className="page-surface" key={page}>
          {page === "chat" && <HomePage onOpenReports={() => setPage("reports")} onOpenSettings={() => setPage("settings")} />}
          {page === "uploads" && <UploadPage onOpenReports={() => setPage("reports")} />}
          {page === "reports" && <ReportsPage />}
          {page === "settings" && (
            <SettingsPage
              apiBase={apiBase}
              theme={theme}
              onApiBaseChange={setApiBase}
              onThemeChange={setTheme}
            />
          )}
        </div>
      </main>
    </div>
  );
}
