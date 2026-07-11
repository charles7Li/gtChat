import { useEffect, useMemo, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChatPage } from "./pages/ChatPage";
import { MonitorPage } from "./pages/MonitorPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { UploadPage } from "./pages/UploadPage";

export type Page = "chat" | "monitor" | "uploads" | "reports" | "settings";

const pageMeta: Record<Page, { title: string; eyebrow: string; action: string }> = {
  chat: { title: "灵感简报", eyebrow: "智能体", action: "新建任务" },
  uploads: { title: "素材", eyebrow: "素材库", action: "本地导入" },
  reports: { title: "报告", eyebrow: "阅读器", action: "查看证据" },
  monitor: { title: "信号", eyebrow: "监控", action: "手动检查" },
  settings: { title: "设置", eyebrow: "运行", action: "本地优先" },
};

export default function App() {
  const [page, setPage] = useState<Page>("chat");
  const [apiBase, setApiBase] = useState("local");
  const meta = useMemo(() => pageMeta[page], [page]);

  useEffect(() => {
    document.title = `${meta.title} - Mochi Scout`;
  }, [meta.title]);

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
          {page === "chat" && <ChatPage onOpenReports={() => setPage("reports")} />}
          {page === "monitor" && <MonitorPage />}
          {page === "uploads" && <UploadPage onOpenReports={() => setPage("reports")} />}
          {page === "reports" && <ReportsPage />}
          {page === "settings" && <SettingsPage apiBase={apiBase} onApiBaseChange={setApiBase} />}
        </div>
      </main>
    </div>
  );
}
